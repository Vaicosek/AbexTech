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
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

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


def _claim(key: str, endpoint: str, uid: str, amount: int):
    """Claim the caller's idempotency key, or let `Replay` propagate to the caller."""
    fingerprint = f"{uid}:{int(amount)}"
    ts = lv._claim_idempotency(key, SERVICE, endpoint, fingerprint, subject=uid)
    return lv._Idem(key=key, claim_ts=ts, endpoint=endpoint)


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
    with lv._tx() as conn:
        _require_account(conn, uid)
        # Wallet first: if the player cannot cover it, nothing has happened yet.
        after = lv.wallet_move(conn, SERVICE, uid, -amt, "savings deposit", key)
        conn.execute(
            "INSERT INTO bank_savings (user_id, balance, last_accrued) VALUES (?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET balance = bank_savings.balance + ?",
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
    with lv._tx() as conn:
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
