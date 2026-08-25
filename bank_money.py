"""The bank's money WRITES, in one transaction each, callable from both processes.

Why this module exists
----------------------
`bank_main` guards every money path with `_user_lock(user_id)` -- an in-memory
`dict[str, asyncio.Lock]`. That was enough while the Bank bot was the only writer of
`bank.db`. It is not enough now: `run_all.py` runs core and bank as separate
PROCESSES, so a website write would take core's lock and a Discord write would take
the bank's, and the two would not exclude each other at all.

Single atomic statements survive that (`claim_bond` is one conditional UPDATE and
exactly one caller wins). What does not survive is a read-decide-act sequence spanning
an await -- which is precisely what `bond_redeem`'s own comment says the lock is for:
"without the lock, a collections pass or a /loan repay landing in that window could
clear the debt, leaving the garnished share applied to nothing and simply destroyed."

The fix is better than the lock it replaces. The wallet has always been in
`restocker.db`; the bank's books moved there too. So a deposit can debit the wallet and
credit `bank_savings` inside ONE `BEGIN IMMEDIATE`, which SQLite serialises across
processes -- a lock the database holds, not one an interpreter holds. Either both
halves land or neither does; there is no window.

Rules for anything added here
-----------------------------
1. **One `ledger_v2._tx()` per operation, and never a nested one.** `_tx()` is not
   re-entrant, and `ledger_v2.adjust()` opens its own -- so call `wallet_move()`
   inside our transaction, never `adjust()`.
2. **Bank-table SQL goes on THAT SAME `conn`.** `bank_db`'s helpers each open their
   own connection; calling one in here would sit outside the transaction and block on
   the write lock the transaction is holding, until `busy_timeout` gives up.
3. **No policy.** Rates, limits and penalties come from `bank_policy`, which the bot
   imports too.
4. **Idempotency is the caller's key**, claimed before the transaction and completed
   inside it, through `ledger_v2`'s existing machinery -- not a second one.
"""
from __future__ import annotations

import logging
import math
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

log = logging.getLogger("bank.money")

_ROOT = Path(__file__).resolve().parent
_BANK_DIR = _ROOT / "bank"
if str(_BANK_DIR) not in sys.path:
    sys.path.append(str(_BANK_DIR))   # appended: bank/main.py must not shadow core's

import ledger_v2 as lv           # noqa: E402
import bank_policy as pol        # noqa: E402

#: The bank's ledger identity. Same string `LEDGER_TOKEN_OSENTAR` scopes.
SERVICE = "osentar"


class BankRefused(Exception):
    """The bank declined, and the reason is safe to show the player.

    Distinct from `ledger_v2.LedgerError` (a wallet-side refusal) and from any
    unexpected exception: this one is an ANSWER, not a failure.
    """


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _savings_balance(conn, uid: str) -> float:
    row = conn.execute("SELECT balance FROM bank_savings WHERE user_id=?", (uid,)).fetchone()
    return float(row[0]) if row else 0.0


def _require_account(conn, uid: str) -> None:
    row = conn.execute(
        "SELECT opted_in, frozen, frozen_reason FROM bank_accounts WHERE user_id=?",
        (uid,)).fetchone()
    if row is None or not row[0]:
        raise BankRefused("You do not have a bank account. Open one with /bank open.")
    if row[1]:
        why = row[2] or "no reason recorded"
        raise BankRefused(f"This account is frozen ({why}).")


def _log(conn, uid: str, kind: str, amount: float, meta: str = "") -> None:
    """Append to bank_ledger on the CALLER'S connection, inside their transaction."""
    conn.execute(
        "INSERT INTO bank_ledger (user_id, kind, amount, meta, ts) VALUES (?,?,?,?,?)",
        (uid, kind, float(amount), meta, _now()))


def _claim(key: str, endpoint: str, uid: str, amount: int,
           *, fingerprint: Optional[str] = None, subject: Optional[str] = None):
    """Claim the caller's idempotency key, or let `Replay` propagate to the caller.

    `fingerprint` overrides the default `uid:amount` for the operations whose
    identity is not (a person, a number of coins): a bond purchase is also its
    TERM, a staff decision is a request id and a verdict. The fingerprint is what
    `_claim_idempotency` compares when the same key comes back, so an operation
    whose fingerprint omits a field that changes the money is an operation whose
    key silently accepts a different request.
    """
    fp = fingerprint if fingerprint is not None else f"{uid}:{int(amount)}"
    ts = lv._claim_idempotency(key, SERVICE, endpoint, fp, subject=subject or uid)
    return lv._Idem(key=key, claim_ts=ts, endpoint=endpoint)


#: Wallet-side codes that are an ANSWER to the player rather than a failure. A claim
#: taken for one of these is released, exactly as a BankRefused is.
_WALLET_REFUSALS = frozenset({"insufficient", "frozen", "bad_amount", "missing_reason"})


def _hand_the_key_back(idem, why: str) -> None:
    """Release a claim whose transaction rolled back with nothing moved."""
    try:
        lv._release_idempotency(idem.key, idem.claim_ts)
    except Exception:          # pragma: no cover - the refusal is still the answer
        log.warning("could not release idempotency key %s after a %s", idem.key, why)


@contextmanager
def _money_tx(idem) -> Iterator[sqlite3.Connection]:
    """`lv._tx()`, plus: a REFUSAL hands the idempotency key back.

    A `BankRefused` raised inside the transaction rolls the whole transaction
    back, so nothing moved -- but the claim was taken in its own transaction
    before this one and would otherwise sit `in_progress` for the full 30-day
    TTL. That matters because the website re-offers a stuck key rather than
    minting a fresh one: a staff collection refused today for being inside the
    grace period would come back with the same key after the grace expired and
    be told `409 idempotency_in_progress` instead of collecting.

    `_release_idempotency` is scoped to `state='in_progress'`, `applied_unknown=0`
    and THIS attempt's `created_at`, so it can neither delete a claim another
    attempt took over nor one whose money committed. It opens its own
    transaction, which is why it runs after this one has unwound rather than
    inside it (`_tx()` is not re-entrant).

    Only refusals. An unexpected exception is NOT a refusal: the transaction
    rolled back either way, but "we do not know what happened" must not hand the
    key back to a retry.
    """
    try:
        with lv._tx() as conn:
            yield conn
    except BankRefused:
        _hand_the_key_back(idem, "bank refusal")
        raise
    except lv.LedgerError as e:
        # A WALLET refusal is an answer too. `insufficient` means the player typed a
        # number bigger than their wallet -- nothing moved, and the key must not stay
        # claimed. It used to: a 240s soak left **57 stuck banking:deposit claims**,
        # one per user who overspent, and because the web panel re-offers an in-flight
        # key rather than minting a fresh one, each of those users would see
        # "in flight - awaiting the bank" and get a 409 on a CORRECTED amount for the
        # full 900s stale window.
        #
        # Only refusals. `idempotency_*` codes are NOT released -- those mean another
        # attempt owns the claim, and handing it back is how one payment becomes two.
        if str(getattr(e, "code", "")) in _WALLET_REFUSALS:
            _hand_the_key_back(idem, f"wallet refusal ({e.code})")
        raise


# ══════════════════════════════════════════════════════════════════════════
# Savings
# ══════════════════════════════════════════════════════════════════════════

def deposit(user_id: str, amount: int, key: str) -> dict[str, Any]:
    """Move coins from the wallet into savings. One transaction, both halves.

    The debit is capped by AVAILABLE, not by balance: coins held against a live
    auction bid are not the player's to put in a savings account, and `_debit`'s
    `respect_holds` is what enforces that. Depositing held coins is how a bid gets
    orphaned.
    """
    uid = str(user_id)
    amt = int(amount)
    if amt <= 0:
        raise BankRefused("A deposit has to be a positive number of coins.")
    idem = _claim(key, "banking:deposit", uid, amt)
    with _money_tx(idem) as conn:
        _require_account(conn, uid)
        # Wallet first: if the player cannot cover it, nothing has happened yet.
        after = lv.wallet_move(conn, SERVICE, uid, -amt, "savings deposit", key)
        conn.execute(
            "INSERT INTO bank_savings (user_id, balance, last_accrued) VALUES (?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET balance = bank_savings.balance + ?, "
            # A row at zero is skipped by all_savings(), so its last_accrued FREEZES.
            # Deposit into an account emptied a year ago and the next hourly pass
            # charges a year of interest on money that arrived a moment ago -- measured
            # at 51,267 coins minted from one deposit. Restart the clock on the way in.
            "  last_accrued = CASE WHEN bank_savings.balance = 0 "
            "                 THEN excluded.last_accrued ELSE bank_savings.last_accrued END",
            (uid, float(amt), _now(), float(amt)))
        _log(conn, uid, "deposit", amt, "from website or Discord")
        _bal = lv._read_balance(conn, uid)
        result = {"ok": True, "applied": amt,
                  "balance": {"available": _bal["available"], "wallet": _bal["balance"],
                              "savings": int(round(_savings_balance(conn, uid)))}}
        lv._finalize_idempotency(conn, idem, result)
        return result


def withdraw(user_id: str, amount: int, key: str) -> dict[str, Any]:
    """Move coins from savings back to the wallet. One transaction, both halves.

    The savings debit is a CONDITIONAL update rather than a read-then-write: two
    concurrent withdrawals that both read the same balance before either deducts is
    the classic way a player withdraws more than they hold. `rowcount` decides.
    """
    uid = str(user_id)
    amt = int(amount)
    if amt <= 0:
        raise BankRefused("A withdrawal has to be a positive number of coins.")
    idem = _claim(key, "banking:withdraw", uid, amt)
    with _money_tx(idem) as conn:
        _require_account(conn, uid)
        cur = conn.execute(
            "UPDATE bank_savings SET balance = balance - ? "
            "WHERE user_id=? AND balance >= ?", (float(amt), uid, float(amt)))
        if cur.rowcount != 1:
            have = int(round(_savings_balance(conn, uid)))
            raise BankRefused(f"Not enough in savings — you have {have:,}.")
        after = lv.wallet_move(conn, SERVICE, uid, amt, "savings withdrawal", key)
        _log(conn, uid, "withdraw", -amt, "from website or Discord")
        _bal = lv._read_balance(conn, uid)
        result = {"ok": True, "applied": amt,
                  "balance": {"available": _bal["available"], "wallet": _bal["balance"],
                              "savings": int(round(_savings_balance(conn, uid)))}}
        lv._finalize_idempotency(conn, idem, result)
        return result


# ══════════════════════════════════════════════════════════════════════════
# Shared reads and writes over the bank's tables, all on the CALLER'S conn
#
# Every one of these was a `bank_db` helper with its own connection. Inside a
# `BEGIN IMMEDIATE` that is not merely "outside the transaction": it blocks on
# the write lock this transaction is holding until `timeout=30` runs out, and
# then raises. So each is re-expressed here as SQL on the caller's `conn`, and
# `bank_main` imports these instead of keeping a second copy.
# ══════════════════════════════════════════════════════════════════════════

#: The loan columns every money path here reads. Named rather than `*` so a
#: column added to `bank_loans` cannot silently change what a row means.
_LOAN_COLS = ("id, user_id, principal, balance, apr, status, issued_at, due_at, "
              "last_accrued, term_days, decided_by, decided_at, overdue_notified, "
              "collected")


def _loan(conn, loan_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(f"SELECT {_LOAN_COLS} FROM bank_loans WHERE id=?",
                        (int(loan_id),)).fetchone()


def active_loans(conn, uid: str) -> list[sqlite3.Row]:
    """This user's open loans, in SETTLEMENT ORDER (bank_policy).

    Not `issued_at` order, which is what `bdb.get_active_loans` used and what
    `/loan repay` therefore settled by. See `bank_policy.SETTLEMENT_ORDER_SQL`.
    """
    return conn.execute(
        f"SELECT {_LOAN_COLS} FROM bank_loans "
        f"WHERE user_id=? AND status='active' AND balance > 0 "
        f"ORDER BY {pol.SETTLEMENT_ORDER_SQL}", (str(uid),)).fetchall()


def _overdue_loans(conn, uid: str, now_iso: str) -> list[sqlite3.Row]:
    """This user's loans past their due date, worst first.

    `bdb.overdue_loans` read EVERY borrower's overdue loans and filtered in
    Python — an O(all borrowers) read for one user's arrears, run once per
    garnishment. The WHERE clause does it here.
    """
    return conn.execute(
        f"SELECT {_LOAN_COLS} FROM bank_loans "
        f"WHERE user_id=? AND status='active' AND due_at IS NOT NULL "
        f"AND due_at < ? AND balance > 0 ORDER BY {pol.SETTLEMENT_ORDER_SQL}",
        (str(uid), now_iso)).fetchall()


def overdue_debt(conn, uid: str, now_iso: str) -> float:
    """Balance across this user's loans that are past due right now.

    Only OVERDUE debt, deliberately: a loan that is merely outstanding is left
    alone. This is what a bond payout is garnished against.
    """
    return sum(float(r["balance"]) for r in _overdue_loans(conn, uid, now_iso))


def total_debt(conn, uid: str) -> float:
    """Every active loan's balance. A 'pending' request is not debt."""
    return float(conn.execute(
        "SELECT COALESCE(SUM(balance),0) FROM bank_loans "
        "WHERE user_id=? AND status='active'", (str(uid),)).fetchone()[0] or 0.0)


def loan_history(conn, uid: str) -> dict[str, Any]:
    """`bdb.loan_history` on the caller's connection. Same three counts."""
    rows = conn.execute(
        "SELECT status, principal, overdue_notified FROM bank_loans WHERE user_id=?",
        (str(uid),)).fetchall()
    repaid = [r for r in rows if r["status"] == "paid"]
    return {
        "repaid_count": len(repaid),
        "repaid_total": sum(float(r["principal"]) for r in repaid),
        "written_off_count": sum(1 for r in rows if r["status"] == "written_off"),
        "denied_count": sum(1 for r in rows if r["status"] == "denied"),
        # a loan that ever went overdue is a black mark even once repaid
        "late_count": sum(1 for r in rows if r["overdue_notified"]),
    }


def _account_row(conn, uid: str) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM bank_accounts WHERE user_id=?",
                       (str(uid),)).fetchone()
    return dict(row) if row else None


def _add_savings(conn, uid: str, delta: float) -> None:
    """Credit savings. For DEBITS use the conditional UPDATE — see `withdraw`."""
    conn.execute(
        "INSERT INTO bank_savings (user_id, balance, last_accrued) VALUES (?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET balance = bank_savings.balance + ?",
        (str(uid), max(0.0, float(delta)), _now(), float(delta)))


def _pay_loan(conn, row: sqlite3.Row, chunk: float, *, collected: bool) -> float:
    """Reduce one loan by `chunk`; mark it paid at zero. Returns the new balance.

    `balance`, `collected` and `status` move in ONE statement. `bdb` did the
    first two as separate connections and the third by read-modify-write, so a
    crash between them left a loan whose balance said one thing and whose
    collection record said another.

    `collected` is the SEIZED total — savings taken and bond payouts garnished.
    A voluntary repayment passes False: it is not a collection, and counting it
    as one would overstate what the bank had to take by force.
    """
    before = float(row["balance"])
    after = max(0.0, before - float(chunk))
    conn.execute(
        "UPDATE bank_loans SET balance = ?, collected = collected + ?, "
        "       status = CASE WHEN ? <= 1e-9 THEN 'paid' ELSE 'active' END "
        " WHERE id=? AND status='active'",
        (after, float(chunk) if collected else 0.0, after, int(row["id"])))
    return after


def apply_to_overdue(conn, uid: str, amount: float, meta: str, now_iso: str) -> float:
    """Pay `amount` against this user's OVERDUE loans, oldest due first.

    Returns how much was actually applied, which can be LESS than `amount` when
    there was less overdue debt than the caller withheld. Every caller must do
    something with the shortfall — see `bond_redeem`, which credits it to savings
    rather than letting it evaporate.

    Inside `BEGIN IMMEDIATE` the rows read here cannot change underneath the
    updates, which is what makes reading a balance and writing it back safe in a
    way it never was through `bdb`.
    """
    remaining = float(amount)
    applied = 0.0
    for row in _overdue_loans(conn, uid, now_iso):
        if remaining <= 1e-9:
            break
        chunk = min(remaining, float(row["balance"]))
        if chunk <= 0:
            continue
        _pay_loan(conn, row, chunk, collected=True)
        _log(conn, uid, "loan_collect", chunk, f"loan #{row['id']} {meta}")
        remaining -= chunk
        applied += chunk
    return applied


def sync_gambling_block(conn, uid: str, reason: str) -> bool:
    """FAIRNESS.md §12.4: the wallet's block is a function of the BOOKS.

    Called after every write that can reduce debt to nothing — a repayment, a
    garnished bond, a savings seizure. It recomputes the debt from `bank_loans`
    rather than decrementing a counter, so partially repaying one of two loans
    cannot clear the other one's block, and it clears rather than sets, because
    only a disbursement sets it.

    `clear_wallet_flag` is a no-op that still records the attempt when there was
    nothing to clear, and that is a 200 by design — the second call in a retry
    must not fail. Returns True when a flag actually came off.
    """
    if total_debt(conn, uid) > 1e-9:
        return False
    out = lv.clear_wallet_flag(SERVICE, str(uid), "gambling_blocked", reason, conn=conn)
    return bool(out.get("changed"))


def collect_one(conn, loan_id: int, now_iso: str, *, cap: Optional[int] = None,
                meta: str = "seized from savings") -> tuple[int, str]:
    """Seize what is reachable from ONE borrower's savings against ONE loan.

    Returns `(coins_taken, reason_if_zero)`. The decision — reachable at all,
    past the grace period, how much, rounded which way — is
    `bank_policy.savings_collectable` and nothing here; this function is the
    WRITES. The hourly pass and the staff page both call it, so the two can never
    take different amounts for the same arrears.

    The savings debit stays a CONDITIONAL update even inside the transaction.
    It costs nothing, and it is the statement that made the old racing version
    safe against a simultaneous withdrawal; a debit that can silently overdraw is
    not something to leave lying around for the next caller who copies this.
    """
    row = _loan(conn, loan_id)
    if row is None or row["status"] != "active" or float(row["balance"]) <= 0:
        return 0, "settled"
    uid = str(row["user_id"])
    savings = _savings_balance(conn, uid)
    take, why = pol.savings_collectable(float(row["balance"]), savings,
                                        row["due_at"], now_iso, cap=cap)
    if take < 1:
        return 0, why
    cur = conn.execute(
        "UPDATE bank_savings SET balance = balance - ? "
        "WHERE user_id=? AND balance >= ?", (float(take), uid, float(take)))
    if cur.rowcount != 1:      # pragma: no cover - impossible inside BEGIN IMMEDIATE
        return 0, "no_savings"
    _pay_loan(conn, row, float(take), collected=True)
    _log(conn, uid, "loan_collect", take, f"loan #{row['id']} {meta}")
    return int(take), ""


def _balance_block(conn, uid: str) -> dict[str, Any]:
    """The `balance` object every one of these returns. One shape, one place."""
    bal = lv._read_balance(conn, uid)
    return {"available": bal["available"], "wallet": bal["balance"],
            "savings": int(round(_savings_balance(conn, uid)))}


# ══════════════════════════════════════════════════════════════════════════
# Loans
# ══════════════════════════════════════════════════════════════════════════

def repay(user_id: str, amount: int, key: str, *,
          loan_id: Optional[int] = None) -> dict[str, Any]:
    """Repay loans from the wallet, oldest DUE first. One transaction.

    What this closes, beyond the windows
    ------------------------------------
    **The vanishing coins.** The old path debited `min(amount, ceil(debt))` and
    then allocated `min(pay, debt)`. Interest accrues in floats, so `debt` is
    fractional almost always, and the up-to-0.999 coins between `debt` and its
    ceiling were taken out of the wallet and applied to nothing at all. They are
    now credited to savings with their own `deposit` row, exactly as a bond
    garnishment's shortfall is — the remainder never evaporates.

    **The order.** Oldest due first, not oldest issued first. See
    `bank_policy.SETTLEMENT_ORDER_SQL` for why one order rather than two.

    **The key.** There was none: `client_rs.adjust` was called without one, so
    `_v1_adjust` synthesised a fingerprint of the whole body — `{user_id,
    amount, reason:"loan repayment"}` — which is IDENTICAL for two genuine
    repayments of the same amount by the same player. Inside the 30-day TTL the
    second replayed `deduped:true` at 200, `bank_main` never read `deduped`, and
    the allocation loop ran anyway: the balance fell twice for one debit. The
    caller's key is now required and carried end to end.
    """
    uid = str(user_id)
    amt = int(amount)
    if amt <= 0:
        raise BankRefused("A repayment has to be a positive number of coins.")
    # loan_id is caller-supplied and decides WHICH debt the coins settle, so it
    # belongs in the fingerprint. Without it, "repay 500 on loan 2" and "repay 500 on
    # loan 1" share a key: the second replays as success and the overdue loan is never
    # touched. None is spelled explicitly so "auto, settlement order" and "loan 0"
    # cannot collide.
    idem = _claim(key, "banking:repay", uid, amt,
                  fingerprint=f"{uid}:{amt}:{'auto' if loan_id is None else int(loan_id)}")
    with _money_tx(idem) as conn:
        _require_account(conn, uid)
        loans = list(active_loans(conn, uid))
        if not loans:
            raise BankRefused("You have no active loans.")
        if loan_id is not None:
            # The website's form names a loan. Honour it — settle that one first,
            # then spill into the rest in policy order. A field the bank accepts
            # and silently discards is worse than one it refuses.
            named = [r for r in loans if int(r["id"]) == int(loan_id)]
            if not named:
                raise BankRefused(f"Loan #{int(loan_id)} is not one of your open loans.")
            loans = named + [r for r in loans if int(r["id"]) != int(loan_id)]

        debt = sum(float(r["balance"]) for r in loans)
        # `ceil` so a whole number of coins can settle a fractional debt in full.
        pay = min(amt, int(math.ceil(debt)))
        if pay <= 0:                       # pragma: no cover - debt > 0 by the query
            raise BankRefused("There is nothing outstanding to repay.")

        # Wallet first: an insufficient wallet refuses here, before a single
        # bank row has moved.
        lv.wallet_move(conn, SERVICE, uid, -pay, "loan repayment", key)

        remaining = float(pay)
        applied = 0.0
        parts: list[str] = []
        for row in loans:
            if remaining <= 1e-9:
                break
            chunk = min(remaining, float(row["balance"]))
            if chunk <= 0:
                continue
            _pay_loan(conn, row, chunk, collected=False)
            parts.append(f"#{row['id']} {chunk:,.2f}".rstrip("0").rstrip("."))
            remaining -= chunk
            applied += chunk

        # ONE `loan_repay` row, for what actually reached the loans. The website
        # sums this kind for `paid_total`, so a second per-loan row of the same
        # kind would double every repayment it displays; the split rides in the
        # meta instead, where it is readable and counted once.
        _log(conn, uid, "loan_repay", applied,
             "repayment — " + (", ".join(parts) or "nothing outstanding"))

        residue = round(float(pay) - applied, 6)
        if residue > 0:
            _add_savings(conn, uid, residue)
            _log(conn, uid, "deposit", residue,
                 "rounding remainder from a repayment -> savings")

        outstanding = total_debt(conn, uid)
        sync_gambling_block(conn, uid, "loans repaid")
        result = {"ok": True, "applied": pay, "to_loans": int(round(applied)),
                  "to_savings": residue,
                  "outstanding": int(round(outstanding)),
                  "loans_settled": [int(r["id"]) for r in loans
                                    if float(_loan(conn, r["id"])["balance"]) <= 1e-9],
                  "balance": _balance_block(conn, uid)}
        lv._finalize_idempotency(conn, idem, result)
        return result


# ══════════════════════════════════════════════════════════════════════════
# Bonds
# ══════════════════════════════════════════════════════════════════════════

def bond_buy(user_id: str, face: int, term_days: int, key: str) -> dict[str, Any]:
    """Lock coins into a fixed-term bond. One transaction, both halves.

    The rate and the payout are computed ONCE, here, from the table in force at
    the sale, and stored on the row. Nothing downstream re-derives them: the rate
    a bond was bought at is the rate it pays, whatever `BOND_TERMS` says later.

    The old path had the same synthesised-key collision as `repay`, and a worse
    consequence: two identical bonds bought within thirty days replayed one
    debit, and the second bond was created for free.
    """
    uid = str(user_id)
    amt = int(face)
    term = int(term_days)
    if amt <= 0:
        raise BankRefused("A bond has to be a positive number of coins.")
    if term not in pol.BOND_TERMS:
        avail = ", ".join(f"{d} days" for d in pol.BOND_TERMS) or "none"
        raise BankRefused(f"{term} isn't an available term. Available: {avail}.")
    apr = pol.BOND_TERMS[term]
    payout = pol.bond_payout(amt, apr, term)
    idem = _claim(key, "banking:bond_buy", uid, amt,
                  fingerprint=f"{uid}:{amt}:{term}")
    with _money_tx(idem) as conn:
        _require_account(conn, uid)
        now = _now()
        matures = (datetime.now(timezone.utc) + timedelta(days=term)).isoformat()
        lv.wallet_move(conn, SERVICE, uid, -amt, f"bond {term}d", key)
        cur = conn.execute(
            "INSERT INTO bank_bonds (user_id, principal, apr, term_days, payout, "
            "status, issued_at, matures_at) VALUES (?,?,?,?,?,'active',?,?)",
            (uid, float(amt), float(apr), term, float(payout), now, matures))
        bond_id = int(cur.lastrowid)
        _log(conn, uid, "bond_buy", amt, f"bond #{bond_id} {term}d")
        result = {"ok": True, "bond_id": bond_id, "face": amt, "term_days": term,
                  "apr": apr, "matures": matures, "repaid_at_maturity": payout,
                  "interest_at_maturity": payout - amt,
                  "balance": _balance_block(conn, uid)}
        lv._finalize_idempotency(conn, idem, result)
        return result


def bond_redeem(user_id: str, bond_id: int, key: str) -> dict[str, Any]:
    """Redeem a bond, settling overdue debt out of the payout first.

    THE PATH WITH THE MOST WINDOWS, all of them now closed by one transaction:
    the split was decided on a debt figure read before an HTTP round trip; the
    bond was marked redeemed before the payout was attempted; the wallet was
    credited before the garnished share was applied to anything. A crash in the
    third window withheld coins from the wallet, applied them to no debt, and
    destroyed them.

    `claim_bond`/`unclaim_bond` are what that shape needed and are now dead: the
    conditional UPDATE and the payout commit together, so there is no claim to
    compensate for. The `WHERE status='active'` stays — it is what makes two
    simultaneous redemptions of one bond resolve to one payout.

    The bond's own `status='redeemed'` is the second, durable guard behind the
    caller's key: even a key that somehow differed cannot pay a redeemed bond.
    """
    uid = str(user_id)
    bid = int(bond_id)
    idem = _claim(key, "banking:bond_redeem", uid, 0,
                  fingerprint=f"{uid}:bond:{bid}", subject=uid)
    with _money_tx(idem) as conn:
        _require_account(conn, uid)
        row = conn.execute(
            "SELECT * FROM bank_bonds WHERE id=? AND user_id=?", (bid, uid)).fetchone()
        if row is None:
            raise BankRefused("That bond isn't yours or doesn't exist.")
        if row["status"] != "active":
            raise BankRefused("That bond has already been redeemed.")

        now_iso = _now()
        rv = pol.bond_redeem_value(dict(row), now_iso)
        amount = int(rv["amount"])
        kind_note = ("matured payout" if rv["matured"] else
                     "early redemption, interest forfeited"
                     + (f", {rv['penalty']:,} penalty" if rv["penalty"] else ""))

        # A bond payout is money the bank is already holding, so overdue debt is
        # settled out of it before the rest reaches the wallet. Only OVERDUE debt,
        # and no grace period: the 3-day grace is a savings-only rule, because
        # these coins are passing through the bank's hands right now.
        # `floor` — a fractional arrear garnishes only whole coins, in the
        # borrower's favour.
        garnish = 0
        if pol.GARNISH_BOND_PAYOUTS:
            garnish = int(min(amount, math.floor(overdue_debt(conn, uid, now_iso))))
        to_wallet = amount - garnish

        cur = conn.execute(
            "UPDATE bank_bonds SET status='redeemed', redeemed_at=?, redeemed_amount=? "
            " WHERE id=? AND status='active'", (now_iso, float(amount), bid))
        if cur.rowcount != 1:              # pragma: no cover - re-read above holds
            raise BankRefused("That bond has already been redeemed.")

        if to_wallet > 0:
            lv.wallet_move(conn, SERVICE, uid, to_wallet, "bond redemption", key)

        applied = (apply_to_overdue(conn, uid, garnish, f"garnished from bond #{bid}",
                                    now_iso) if garnish else 0.0)
        # Belt and braces, kept from the original: if less debt was there than we
        # withheld, the remainder goes to savings rather than evaporating.
        #
        # Inside one transaction this is now UNREACHABLE, and that is the point:
        # `garnish` is floored from the same overdue rows `apply_to_overdue` then
        # settles, and nothing else can touch them in between. It used to fire
        # for real — a collections pass or a /loan repay landing between the two
        # was exactly what the user lock was there to prevent and could not,
        # across processes. It stays as the invariant's tripwire: if it ever runs
        # again, the transaction boundary has been broken and the log line says so.
        shortfall = round(garnish - applied, 6)
        if shortfall > 0:
            _add_savings(conn, uid, shortfall)
            _log(conn, uid, "deposit", shortfall,
                 f"bond #{bid} garnish remainder -> savings")
            log.warning("Bond #%s garnish shortfall of %s credited to savings for %s",
                        bid, shortfall, uid)

        _log(conn, uid, "bond_redeem", amount, f"bond #{bid} {kind_note}")
        outstanding = total_debt(conn, uid)
        sync_gambling_block(conn, uid, f"debt settled by bond #{bid}")
        result = {"ok": True, "bond_id": bid, "payout": amount,
                  "paid": to_wallet, "penalty": int(rv["penalty"]),
                  "garnished": int(round(applied)), "to_savings": shortfall,
                  "matured": bool(rv["matured"]), "note": kind_note,
                  "outstanding": int(round(outstanding)),
                  "balance": _balance_block(conn, uid)}
        lv._finalize_idempotency(conn, idem, result)
        return result


# ══════════════════════════════════════════════════════════════════════════
# Staff
# ══════════════════════════════════════════════════════════════════════════

#: The website says `decline`, Discord says `deny`, `bank_loans.status` says
#: `denied`. Three words for one verdict, mapped at the boundary so exactly one
#: of them is ever stored.
_DECISIONS = {"approve": "approve", "decline": "decline", "deny": "decline"}


def staff_loan_decide(request_id: int, decision: str, actor_id: str, key: str,
                      note: str = "") -> dict[str, Any]:
    """Approve or decline a pending loan request. One transaction.

    `'approving'` is gone. It existed because the disbursement was an HTTP call
    between two local writes, and something had to hold the loan while the coins
    were in flight — but a hard kill in that window never ran the compensator,
    and the loan stayed `'approving'` forever: invisible to `/loan status`, to
    `/admin loans` and to the collections pass alike, freeable only by hand.
    The transition is now `pending -> active` in one statement inside the same
    transaction as the disbursement. `claim_pending_loan` and
    `release_pending_loan` are dead code after this.

    The conditional `WHERE status='pending'` stays: it is what makes two bankers
    clicking Approve at the same instant resolve to one disbursement, and it
    costs nothing.

    FAIRNESS.md §12.4 is enforced here for the first time. The machinery existed
    on the ledger side and nothing in the bank ever called it, so the sentence
    "Osentar sets the block in the same transaction as the disbursement" was
    aspirational. `set_wallet_flag` takes this `conn`, so it is now literal.
    """
    rid = int(request_id)
    verdict = _DECISIONS.get(str(decision).strip().lower())
    if verdict is None:
        raise BankRefused("A decision must be approve or decline.")
    actor = str(actor_id)
    idem = _claim(key, "banking:staff_decide", str(rid), 0,
                  fingerprint=f"{rid}:{verdict}", subject=str(rid))
    with _money_tx(idem) as conn:
        row = _loan(conn, rid)
        if row is None:
            raise BankRefused(f"No such loan request (#{rid}).")
        if row["status"] != "pending":
            raise BankRefused(f"Loan #{rid} is already {row['status']} — "
                              f"nothing to decide.")
        borrower = str(row["user_id"])
        now_iso = _now()

        if verdict == "decline":
            # A denial moves no coins; it is a status flip and an audit line.
            # The line is new: there was none, and "who declined this and when"
            # was recoverable only from the loan row itself.
            cur = conn.execute(
                "UPDATE bank_loans SET status='denied', decided_by=?, decided_at=? "
                " WHERE id=? AND status='pending'", (actor, now_iso, rid))
            if cur.rowcount != 1:          # pragma: no cover - re-read above holds
                raise BankRefused("Someone else just decided that loan.")
            _log(conn, borrower, "loan_denied", 0,
                 f"loan #{rid} declined by {actor}" + (f" — {note}" if note else ""))
            result = {"ok": True, "decision": "decline", "loan_id": rid,
                      "user_id": borrower, "disbursed": 0}
            lv._finalize_idempotency(conn, idem, result)
            return result

        acct = _account_row(conn, borrower)
        if not acct or not acct.get("opted_in"):
            raise BankRefused(f"Loan #{rid}: the borrower's account is closed.")
        if acct.get("frozen"):
            raise BankRefused(f"Loan #{rid}: the borrower's account is frozen. "
                              f"Unfreeze it first.")

        # Re-checked at approval time, on THIS connection: debt can have grown
        # since the request was filed, and the figures behind the limit are read
        # inside the transaction that acts on them.
        principal = float(row["principal"])
        limit = pol.credit_limit_from(acct, loan_history(conn, borrower))
        debt = total_debt(conn, borrower)
        if debt + principal > limit:
            raise BankRefused(
                f"Loan #{rid} would put them at {int(round(debt + principal)):,} "
                f"against a {limit:,} limit. Raise it with /admin creditlimit or "
                f"decline.")

        days = int(row["term_days"] or pol.DEFAULT_LOAN_DAYS)
        due = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        # issued_at/last_accrued are reset to now so interest runs from
        # DISBURSEMENT, not from when the request was filed.
        cur = conn.execute(
            "UPDATE bank_loans SET status='active', decided_by=?, decided_at=?, "
            "       issued_at=?, last_accrued=?, due_at=? "
            " WHERE id=? AND status='pending'",
            (actor, now_iso, now_iso, now_iso, due, rid))
        if cur.rowcount != 1:              # pragma: no cover - re-read above holds
            raise BankRefused("Someone else just decided that loan.")

        # `counts_as_principal=False`: borrowed coins are not the borrower's own
        # capital. The HTTP path carried `count_principal=False` and losing it
        # here would quietly change what `balances.principal` means.
        lv.wallet_move(conn, SERVICE, borrower, int(principal),
                       f"loan #{rid} disbursement", key, counts_as_principal=False)
        lv.set_wallet_flag(SERVICE, borrower, "gambling_blocked",
                           f"outstanding loan #{rid}", conn=conn)
        _log(conn, borrower, "loan_out", principal,
             f"loan #{rid} {days}d approved by {actor}" + (f" — {note}" if note else ""))

        result = {"ok": True, "decision": "approve", "loan_id": rid,
                  "user_id": borrower, "disbursed": int(principal),
                  "term_days": days, "due_at": due,
                  "outstanding": int(round(total_debt(conn, borrower))),
                  "balance": _balance_block(conn, borrower)}
        lv._finalize_idempotency(conn, idem, result)
        return result


def staff_collect(loan_id: int, amount: int, actor_id: str, key: str) -> dict[str, Any]:
    """Collect arrears from a borrower's SAVINGS. One transaction.

    The wallet is never reached, and neither are escrow holds, stock or land.
    The bank can take back what it already holds; it cannot reach into a
    player's pocket. That boundary is enforced by never asking for anything else.

    The hourly pass is idempotent by construction — conditional flips and
    conditional debits — which is why it never needed a key. This path is a
    browser POST naming a loan and an amount, and a browser retries, so it takes
    a real one.

    The window this closes is the worst one in the old code: `try_debit_savings`
    succeeded and `apply_loan_payment` had not run yet. The borrower's savings
    were gone, the debt was unchanged, and the only record was a `bank_savings`
    row with nothing to explain it.
    """
    lid = int(loan_id)
    amt = int(amount)
    actor = str(actor_id)
    if amt <= 0:
        raise BankRefused("A collection has to be a positive number of coins.")
    idem = _claim(key, "banking:staff_collect", str(lid), amt,
                  fingerprint=f"{lid}:{amt}", subject=str(lid))
    with _money_tx(idem) as conn:
        row = _loan(conn, lid)
        if row is None:
            raise BankRefused(f"No such loan (#{lid}).")
        uid = str(row["user_id"])
        if row["status"] != "active" or float(row["balance"]) <= 0:
            raise BankRefused(f"Loan #{lid} is {row['status']} — nothing to collect.")

        now_iso = _now()
        took, why = collect_one(conn, lid, now_iso, cap=amt,
                                meta=f"seized from savings by {actor}")
        if took < 1:
            raise BankRefused(pol.COLLECT_REASONS.get(
                why, "There is nothing reachable to collect."))

        arrears = overdue_debt(conn, uid, now_iso)
        sync_gambling_block(conn, uid, f"debt settled by collection on loan #{lid}")
        result = {"ok": True, "loan_id": lid, "user_id": uid, "collected": took,
                  "arrears_after": int(round(arrears)),
                  "outstanding": int(round(total_debt(conn, uid))),
                  "savings_after": int(round(_savings_balance(conn, uid)))}
        lv._finalize_idempotency(conn, idem, result)
        return result


def run_collections_pass(now_iso: Optional[str] = None) -> list[dict[str, Any]]:
    """The bot's hourly sweep: announce once, then take what savings allow.

    ONE TRANSACTION PER LOAN, not one for the pass. A `BEGIN IMMEDIATE` held
    across every overdue loan in the bank would lock out both processes for the
    length of the sweep, and one bad row would roll back every good one. Per-loan
    transactions keep the loop's "next pass will retry" property and still close
    every window inside a loan.

    No idempotency key, deliberately: nothing here is a caller's request. The
    announcement is a conditional flip and the seizure is a conditional debit, so
    a second pass takes only what is still there.

    Returns one record per loan it touched, for the caller to ANNOUNCE. The
    Discord posts stay outside the money transactions — a failed post must never
    be able to roll back a collection.
    """
    if not (pol.COLLECT_FROM_SAVINGS or pol.OVERDUE_ANNOUNCE):
        return []
    now_iso = now_iso or _now()
    # The sweep's list is read WITHOUT a transaction -- a read needs no write
    # lock, and taking BEGIN IMMEDIATE to build a worklist would hold both
    # processes out of the database while we did. Each row is re-read inside its
    # own transaction below, which is where the decision is actually made, so a
    # loan that changed in between is simply skipped.
    due = lv._conn().execute(
        f"SELECT id, user_id FROM bank_loans "
        f"WHERE status='active' AND due_at IS NOT NULL AND due_at < ? "
        f"AND balance > 0 ORDER BY {pol.SETTLEMENT_ORDER_SQL}",
        (now_iso,)).fetchall()
    overdue = [(int(r["id"]), str(r["user_id"])) for r in due]

    out: list[dict[str, Any]] = []
    for lid, uid in overdue:
        try:
            with lv._tx() as conn:
                row = _loan(conn, lid)
                if row is None or row["status"] != "active" or float(row["balance"]) <= 0:
                    continue
                announced = False
                if pol.OVERDUE_ANNOUNCE:
                    # The same flag is `late_count` on the credit limit, so
                    # announcing and penalising are one write on purpose.
                    announced = conn.execute(
                        "UPDATE bank_loans SET overdue_notified=1 "
                        " WHERE id=? AND overdue_notified=0", (lid,)).rowcount == 1
                took, why = collect_one(conn, lid, now_iso)
                if took:
                    sync_gambling_block(
                        conn, uid, f"debt settled by collection on loan #{lid}")
                if not announced and not took:
                    continue
                out.append({"loan_id": lid, "user_id": uid, "announced": announced,
                            "collected": took, "skipped": why,
                            "owed_before": float(row["balance"]),
                            "due_at": row["due_at"], "term_days": row["term_days"],
                            "outstanding": int(round(total_debt(conn, uid)))})
        except Exception:
            # One borrower's row must not end the sweep for everyone else.
            log.exception("[collections] loan #%s failed; the next pass will retry", lid)
    return out


def clear_block_if_settled(user_id: str, reason: str) -> bool:
    """Recheck one borrower's debt and lift the gambling block if it is gone.

    For the paths that reduce debt WITHOUT moving coins — `/admin forgive` writes
    a loan off, and no wallet transaction rides along to carry the clear. That is
    the exact case `ledger_v2._v1_wallet_flag` was built for, said in its own
    docstring: without it "that borrower stays blocked until they happen to make a
    wallet transaction, which is a silent, indefinite punishment for having
    repaid" — and a write-off is the bank forgiving the debt, so being punished
    for it is worse still.

    Its own transaction, because there are no coins here to be atomic with. If it
    fails, the next repayment, collection or forgiveness recomputes the same
    answer from the same books.
    """
    with lv._tx() as conn:
        return sync_gambling_block(conn, str(user_id), reason)


# ══════════════════════════════════════════════════════════════════════════
# Interest accrual
# ══════════════════════════════════════════════════════════════════════════
# The hourly pass used to read a balance, compute the new one in Python, and write
# that ABSOLUTE value back on its own connection -- a read-decide-act spanning the
# whole loop. Anything committed in between was erased, and it was reproduced
# destroying and MINTING coins: a website withdrawal landing mid-pass left the coins
# in the wallet AND the savings row restored; a repayment left the borrower owing
# more than before paying. BEGIN IMMEDIATE could not help, because the accrual write
# was a later, perfectly valid transaction that clobbered the committed one.
#
# The fix is that interest is a DELTA, not a destination. `balance = balance + ?`
# composes with whatever else landed; the row is guarded on `last_accrued` so two
# overlapping passes cannot both apply the same period, and loans are guarded on
# `status='active'` so a loan settled mid-pass is not resurrected with a balance.
#
# Interest is computed from the balance as it was READ. If a deposit lands in the
# window the depositor earns nothing on it this hour, which is correct -- the money
# was not there for the period being charged for.

def accrue_savings_row(uid: str, interest: float, expect_last: Optional[str],
                       now_iso: str, meta: str) -> bool:
    """Add `interest` to one savings row. False if another writer got there first.

    Takes an AMOUNT computed by the caller from the balance it READ, and adds it:
    `balance = balance + ?`. Interest is earned by the balance HELD ACROSS THE PERIOD,
    and the read is the best evidence of that balance the pass has.

    This was briefly `balance = balance * ?` instead, to stop interest being paid on
    money that had since been withdrawn. That traded a small error for a much larger
    one: a factor applies the whole period to whatever is in the row at COMMIT, so a
    deposit landing between the pass's read and its write earned a full period on money
    held for zero seconds -- measured at **1000x overcredit**, and drivable on purpose,
    because the window for row N is however long the pass takes to reach row N.

    The residual in this direction is bounded and benign by comparison: withdraw at the
    very end of a period you held the money through, and you are still paid for having
    held it. That is not a mint; it is the period being measured at its end.

    Guarded on `last_accrued` so two overlapping passes cannot both apply one period.
    When the guard misses, `last_accrued` is LEFT ALONE, so the period is not lost --
    the next pass sees the same starting point and covers it in full.
    """
    with lv._tx() as conn:
        cur = conn.execute(
            "UPDATE bank_savings SET balance = balance + ?, last_accrued = ? "
            "WHERE user_id = ? AND last_accrued IS ?",
            (float(interest), now_iso, str(uid), expect_last))
        if cur.rowcount != 1:
            return False
        if interest:
            _log(conn, str(uid), "interest_savings", float(interest), meta)
        return True


def accrue_loan_row(loan_id: int, uid: str, interest: float,
                    expect_last: Optional[str], now_iso: str, meta: str) -> bool:
    """Add `interest` to one ACTIVE loan. False if another writer got there first.

    An AMOUNT, for the same reason as savings: interest is owed by the balance carried
    across the period. The multiplicative form let a borrower who repaid inside the
    pass's window escape interest they had genuinely accrued -- 12,402c on a 1,000,000
    loan -- which is a transfer from the bank to whoever times a repayment against a
    fixed hourly schedule.

    The `status='active'` guard stops a loan repaid to zero mid-pass being written back
    with a balance, which left rows `status='paid'` carrying an unrepayable debt that
    `active_loans` could not even see. It costs the bank one period on a loan settled in
    that window, which is the right side to err on.
    """
    with lv._tx() as conn:
        cur = conn.execute(
            "UPDATE bank_loans SET balance = balance + ?, last_accrued = ? "
            "WHERE id = ? AND status = 'active' AND last_accrued IS ?",
            (float(interest), now_iso, int(loan_id), expect_last))
        if cur.rowcount != 1:
            return False
        if interest:
            _log(conn, str(uid), "interest_loan", float(interest), meta)
        return True


def close_account(user_id: str, key: str) -> dict[str, Any]:
    """Cash savings out to the wallet and deactivate the account. ONE transaction.

    `/bank close` used to read the savings balance, `await` a Discord confirm button,
    and only THEN mint the coins and subtract the savings -- two transactions with a
    human-length gap, no idempotency key and no floor on the subtraction. Reproduced:
    start a close, withdraw the same savings on the website before clicking Confirm,
    and the wallet gains the money TWICE while `bank_savings.balance` goes NEGATIVE.
    A negative savings row is also permanently uncollectable, so the debt behind it
    can never be recovered.

    The balance is therefore read INSIDE this transaction, never before the button.
    Whatever the row holds at commit time is what moves, and a concurrent withdrawal
    either happens before (and there is less to cash out) or after (and there is
    nothing left) -- but never both.

    The account is soft-closed: rows and history stay, `/bank open` reopens the same
    row. Deleting would break the FK from loans and bonds and destroy the audit trail.
    A sub-coin remainder is left on the row rather than confiscated -- coins are whole,
    so it cannot be paid out -- and `bank_db.all_savings()` skips closed accounts so it
    does not compound in the meantime.
    """
    uid = str(user_id)
    idem = _claim(key, "banking:close", uid, 0, fingerprint=f"{uid}:close")
    with _money_tx(idem) as conn:
        _require_account(conn, uid)
        debt = total_debt(conn, uid)
        if debt > 0:
            raise BankRefused(
                f"You still owe {int(round(debt)):,}c. Settle it before closing.")
        row = conn.execute(
            "SELECT COUNT(*) FROM bank_bonds WHERE user_id=? AND status='active'",
            (uid,)).fetchone()
        if row and row[0]:
            raise BankRefused(f"You have {row[0]} active bond(s). Redeem them first.")

        # Read INSIDE the transaction -- this is the whole fix.
        sav = _savings_balance(conn, uid)
        cashed = int(sav)               # floor: never mint a fraction of a coin
        if cashed > 0:
            cur = conn.execute(
                "UPDATE bank_savings SET balance = balance - ? "
                "WHERE user_id = ? AND balance >= ?", (float(cashed), uid, float(cashed)))
            if cur.rowcount != 1:
                raise BankRefused("Your savings balance changed — try again.")
            lv.wallet_move(conn, SERVICE, uid, cashed,
                           "bank account closed — savings cashed out", key)
            _log(conn, uid, "withdraw", -cashed, "savings->wallet (account closed)")
        conn.execute("UPDATE bank_accounts SET opted_in=0 WHERE user_id=?", (uid,))
        _log(conn, uid, "account_closed", 0, "")
        result = {"ok": True, "cashed_out": cashed, **_balance_block(conn, uid)}
        lv._finalize_idempotency(conn, idem, result)
        return result
