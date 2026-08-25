"""Serve `banking_web`'s Osentar API from the local database instead of over HTTP.

Why this exists
---------------
`banking_web` was written against a bank that answered HTTP on `OSENTAR_BASE_URL`.
That bank never existed: the Bank bot has no `web.Application` and no routes, its only
aiohttp use is a `ClientSession` making outbound calls *to* core. There was never a URL
to set, which is why the site's banking section has always rendered its "bank not
answering" state and why the Savings and Net segments of the header strip are
em-dashes on every page.

Now that both bots run in one container against one `restocker.db`, the HTTP call has
nothing to cross. This module answers the same paths with the same payload shapes,
reading `bank_*` tables directly, so `banking_web`'s twelve call sites and all of their
error handling stay exactly as they are.

What it will not do
-------------------
**It does not compute policy.** Credit limits, bond payouts and redemption values come
from `bank_policy`, which the Bank bot itself imports. `banking_web`'s own contract is
explicit that two implementations of one policy is how a FAQ says 7.5% while the embed
says 10%, and being in-process makes recomputing things locally *easier*, not more
correct.

**It does not invent figures the bank never recorded.** A repayment `schedule` and a
savings `ladder` are part of the HTTP contract, but the bank never implemented that API
and so has never built either. They are omitted, and the contract already says the panel
should report their absence rather than derive one from the terms. The same applies to
the principal/interest split of past repayments: `bank_ledger` records the total moved,
not how it was apportioned, so this returns what was recorded and nothing more.

**It does not implement money.** All seven write paths (deposit, withdraw, repay, bond
buy and redeem, staff decide and collect) move coins in core's ledger AND write the
bank's own books, and both halves belong in one transaction. That transaction lives in
`bank_money`, which the Bank bot calls too -- so this module maps a web body onto its
arguments and translates its outcomes, and there is one money path rather than two.
What it does NOT do is decide anything: no amount, no penalty, no limit and no
ordering is computed in this file.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("banking.local")

_ROOT = Path(__file__).resolve().parent
_BANK_DIR = _ROOT / "bank"

#: Version reported by /api/v1/health. Distinct from the bot's own, on purpose: this
#: is the in-process provider, and an operator reading the health line should be able
#: to tell which one answered.
PROVIDER_VERSION = "local-1"

_bdb: Any = None
_pol: Any = None
_import_error: str = ""


def _load() -> bool:
    """Import `bank_db` and `bank_policy` out of `bank/`, once.

    `bank/` is appended to the END of sys.path, never prepended: `bank/main.py` and
    the repo root's `main.py` share a name, and core's must keep winning.

    `bank_main` is deliberately NOT imported -- its module body calls
    `logging.basicConfig()` and constructs a `commands.Bot`, so importing it would give
    the web process a second Discord bot and reconfigure its logging as a side effect
    of rendering a page.
    """
    global _bdb, _pol, _import_error
    if _bdb is not None and _pol is not None:
        return True
    if _import_error:
        return False
    try:
        p = str(_BANK_DIR)
        if p not in sys.path:
            sys.path.append(p)
        import bank_db as bdb
        import bank_policy as pol
        _bdb, _pol = bdb, pol
        return True
    except Exception as e:
        _import_error = f"{type(e).__name__}: {e}"
        log.warning("[banking] local provider unavailable: %s", _import_error)
        return False


def available() -> bool:
    """True when the bank's tables are reachable in the database core is using.

    Checks for the TABLE, not just the import: `bank_db` imports fine against a
    database that has never had `init_db()` run on it, and answering "the bank is up"
    in that state would turn a missing schema into a page full of zeroes.
    """
    if not _load():
        return False
    try:
        # The bank's books and the ledger's coins MUST be the same file. When they
        # were not, this probe passed against a stale bank/bank.db and every read was
        # served from it while every write went to restocker.db -- deposits appeared
        # to vanish. A split brain is not "available"; it is the most dangerous state
        # available, because it looks healthy.
        import ledger_v2 as _lv
        import os.path as _p
        if _p.realpath(str(_bdb.DB_PATH)) != _p.realpath(str(_lv._db_path())):
            log.error("[banking] REFUSING to serve: the bank reads %s but the ledger "
                      "writes %s. Set BANK_DB_PATH to the ledger's file, or unset it "
                      "so it defaults there.", _bdb.DB_PATH, _lv._db_path())
            return False
        with _bdb.db() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='bank_accounts'"
            ).fetchone()
            return row is not None
    except Exception as e:
        log.warning("[banking] local provider table check failed: %s", e)
        return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _month_start() -> str:
    n = datetime.now(timezone.utc)
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def _ledger_sum(conn, user_id: str, kind: str, since: Optional[str] = None) -> float:
    sql = "SELECT COALESCE(SUM(amount),0) FROM bank_ledger WHERE user_id=? AND kind=?"
    args: list = [str(user_id), kind]
    if since:
        sql += " AND ts >= ?"
        args.append(since)
    return float(conn.execute(sql, args).fetchone()[0] or 0)


# ══════════════════════════════════════════════════════════════════════════
# GET /api/v1/account
# ══════════════════════════════════════════════════════════════════════════

def _account(user_id: str) -> dict:
    uid = str(user_id)
    acct = _bdb.get_account(uid)
    sav = _bdb.get_savings(uid)
    loans = _bdb.get_active_loans(uid)
    bonds = _bdb.get_bonds(uid, "active")
    now = _now()

    with _bdb.db() as conn:
        accrued_lifetime = _ledger_sum(conn, uid, "interest_savings")
        accrued_month = _ledger_sum(conn, uid, "interest_savings", _month_start())
        last_paid = sav.get("last_accrued")
        accrued_since = (_ledger_sum(conn, uid, "interest_savings", last_paid)
                         if last_paid else accrued_lifetime)
        rep = conn.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(amount),0) t, MAX(ts) m "
            "FROM bank_ledger WHERE user_id=? AND kind='loan_repay'", (uid,)).fetchone()

    savings = {
        "balance": int(round(float(sav.get("balance") or 0))),
        "apr": _pol.SAVINGS_APR,
        "opened": (acct or {}).get("created_at"),
        "last_paid": last_paid,
        "accrued_this_month": int(round(accrued_month)),
        "accrued_since_last_paid": int(round(accrued_since)),
        "accrued_lifetime": int(round(accrued_lifetime)),
        # `ladder` and `avg90` need a balance history the bank has never kept.
        # Omitted rather than derived -- see the module docstring.
    }

    loan = None
    if loans:
        l = loans[0]   # one open loan per player, per the API contract
        loan = {
            "id": l["id"],
            "principal": int(round(float(l["principal"]))),
            "apr": float(l["apr"]),
            "terms": l.get("term_days"),
            "disbursed": l.get("issued_at"),
            "due": l.get("due_at"),
            "outstanding": int(round(float(l["balance"]))),
            # Interest is accrued INTO the balance by the bank's accrual loop, so the
            # outstanding figure is already current -- payoff today is simply that.
            "payoff_today": int(round(float(l["balance"]))),
            "paid_count": int(rep["c"] or 0),
            "paid_total": int(round(float(rep["t"] or 0))),
            "last_paid_on": rep["m"],
            "collected": int(round(float(l.get("collected") or 0))),
            "closed": False,
            # `schedule`, and the principal/interest split of past payments, are not
            # recorded anywhere. Omitted rather than invented.
        }

    bond_rows = []
    for b in bonds:
        rv = _pol.bond_redeem_value(b, now)
        bond_rows.append({
            "id": b["id"],
            "face": int(round(float(b["principal"]))),
            "apr": float(b["apr"]),
            "term_days": b.get("term_days"),
            "bought": b.get("issued_at"),
            "matures": b.get("matures_at"),
            "interest_at_maturity": rv["interest_at_maturity"],
            "earned_so_far": rv["earned_so_far"],
            "redeem_value_today": rv["amount"],
            "early_redemption_penalty": rv["penalty"],
            "matured": rv["matured"],
        })

    h = _bdb.loan_history(uid)
    limit_amount = _pol.credit_limit_for(uid)
    debt = float(_bdb.total_debt(uid))

    return {
        "ok": True,
        "savings": savings,
        "loan": loan,
        "bonds": bond_rows,
        "bond_terms": [{"term_days": d, "apr": r} for d, r in _pol.BOND_TERMS.items()],
        "record": {
            "repaid_clean": h["repaid_count"],
            "late": h["late_count"],
            "defaults": h["written_off_count"],
            "since": (acct or {}).get("created_at"),
        },
        "limit": {
            "amount": limit_amount,
            "cap": _pol.MAX_LOAN,
            "headroom": max(0, limit_amount - int(round(debt))),
            "components": [[label, value]
                           for label, value in _pol.credit_limit_components(uid)],
        },
        "frozen": bool((acct or {}).get("frozen")),
        "account_open": bool(acct and acct.get("opted_in")),
    }


# ══════════════════════════════════════════════════════════════════════════
# Staff reads
# ══════════════════════════════════════════════════════════════════════════

def _staff_queue() -> dict:
    out = []
    for l in _bdb.get_pending_loans():
        uid = str(l["user_id"])
        acct = _bdb.get_account(uid) or {}
        h = _bdb.loan_history(uid)
        out.append({
            "id": l["id"],
            "user_id": uid,
            "name": acct.get("name") or uid,
            "requested": int(round(float(l["principal"]))),
            "terms": l.get("term_days"),
            "asked": l.get("requested_at"),
            "outstanding_debt": int(round(float(_bdb.total_debt(uid)))),
            "limit": _pol.credit_limit_for(uid),
            "repaid_clean": h["repaid_count"],
            "late": h["late_count"],
            "frozen": bool(acct.get("frozen")),
            # `purpose` is part of the HTTP contract but the bank never stored it.
        })
    return {"ok": True, "requests": out}


def _staff_collections() -> dict:
    now = datetime.now(timezone.utc)
    # From bank_policy, not from os.getenv here: this page's "reachable" figure and
    # the amount a collection actually takes must come from ONE reading of the
    # setting. Two readings is how a staff page offers a collection the collector
    # then refuses to make.
    reachable = _pol.COLLECT_FROM_SAVINGS
    out = []
    for l in _bdb.overdue_loans(now.isoformat()):
        uid = str(l["user_id"])
        acct = _bdb.get_account(uid) or {}
        days_late = None
        try:
            due = datetime.fromisoformat(str(l["due_at"]))
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            days_late = max(0, (now - due).days)
        except (TypeError, ValueError):
            pass
        sav = float(_bdb.get_savings(uid).get("balance") or 0)
        # ASK THE POLICY. This used to report the raw savings balance, which got two
        # things wrong at once: it ignored COLLECT_GRACE_DAYS entirely, so the page
        # offered collections `staff_collect` then refused with "still inside its grace
        # period"; and it ignored min(owed, savings) and the floor, so 900 was shown
        # against a ceiling of 500. savings_collectable's own docstring claims this
        # page asks it -- now it does.
        take, why = _pol.savings_collectable(
            float(l["balance"]), sav, l.get("due_at"), now.isoformat())
        out.append({
            "loan_id": l["id"],
            "user_id": uid,
            "name": acct.get("name") or uid,
            "days_late": days_late,
            "owed": int(round(float(l["balance"]))),
            # floor, to match the policy sitting next to it: int(round(0.6)) rendered
            # "1 in savings, 0 reachable", which reads as a bug rather than a rule.
            "savings_balance": int(sav) if reachable else 0,
            # What a collection would ACTUALLY take, right now.
            "savings_reachable": int(take),
            # Why it is zero, so the row explains itself instead of looking broken:
            # in_grace / no_savings / settled / collection_off / below_one_coin.
            "blocked": None if take > 0 else why,
        })
    return {"ok": True, "overdue": out}


# ══════════════════════════════════════════════════════════════════════════
# Dispatch
# ══════════════════════════════════════════════════════════════════════════

#: Implemented locally, in one transaction each -- see bank_money.py.
_LIVE_WRITES = {
    "/api/v1/savings/deposit": "deposit",
    "/api/v1/savings/withdraw": "withdraw",
    "/api/v1/loan/repay": "repay",
    "/api/v1/bond/buy": "bond_buy",
    "/api/v1/bond/redeem": "bond_redeem",
    "/api/v1/staff/loan/decide": "staff_loan_decide",
    "/api/v1/staff/collect": "staff_collect",
}

#: Nothing is Discord-only any more. The set stays, empty, because `handle` still
#: reads it: a path added to the HTTP contract before it has an implementation
#: belongs HERE, answering "the bank declines" -- not in the fall-through, which
#: answers "unknown endpoint" and reads on a banking page as the bank being lost.
_WRITE_PATHS: set[str] = set()

#: A refusal, NOT a transport failure. banking_web renders {"ok": false, "error": ...}
#: as the bank declining -- which is the truth -- rather than as the bank being down.
_WRITE_REFUSAL = ("This action is not available from the website yet — "
                  "use the bank's Discord commands. (Reading is live.)")


class _BadField(Exception):
    """A field the page sent that the bank cannot read. Its own message is shown."""


def _need_int(body: dict, name: str, what: str) -> int:
    try:
        return int(str(body.get(name)).strip())
    except (TypeError, ValueError, AttributeError):
        raise _BadField(f"{what} was not sent as a whole number.")


def _coins(body: dict, name: str = "amount") -> int:
    try:
        return int(body.get(name) or 0)
    except (TypeError, ValueError):
        raise _BadField("That amount is not a whole number of coins.")


def _uid(body: dict) -> str:
    uid = str(body.get("user_id") or "").strip()
    if not uid:
        raise _BadField("No user id was supplied.")
    return uid


def _actor(body: dict) -> str:
    a = str(body.get("actor_id") or "").strip()
    if not a:
        raise _BadField("No staff member was named on that decision.")
    return a


#: op -> how to turn ONE web body into that function's arguments.
#:
#: Each of the seven takes a different shape, and the mapping is here rather than
#: in `_write` because the bodies are `banking_web`'s, not ours: `bond_buy` sends
#: `face` (not `amount`), the two staff paths send no `user_id` at all, and
#: `repay` sends a `loan_id` the bank used to accept and silently discard.
#: Getting one of these wrong is a TypeError at the worst moment, so they sit in
#: one table next to the paths they serve.
_WRITE_ARGS = {
    "deposit":     lambda b, k: ((_uid(b), _coins(b), k), {}),
    "withdraw":    lambda b, k: ((_uid(b), _coins(b), k), {}),
    "repay":       lambda b, k: ((_uid(b), _coins(b), k),
                                 {"loan_id": (_need_int(b, "loan_id", "The loan")
                                              if b.get("loan_id") not in (None, "") else None)}),
    "bond_buy":    lambda b, k: ((_uid(b), _coins(b, "face"),
                                  _need_int(b, "term_days", "The bond term"), k), {}),
    "bond_redeem": lambda b, k: ((_uid(b), _need_int(b, "bond_id", "The bond"), k), {}),
    "staff_loan_decide": lambda b, k: ((_need_int(b, "request_id", "The request"),
                                        str(b.get("decision") or ""), _actor(b), k),
                                       {"note": str(b.get("note") or "")}),
    "staff_collect":     lambda b, k: ((_need_int(b, "loan_id", "The loan"),
                                        _coins(b), _actor(b), k), {}),
}


def _write(op: str, body: dict) -> dict:
    """Run one money write, translating its outcomes into the API's own shapes.

    Three outcomes, three shapes, and the difference matters on a banking page:
      - a REPLAY returns the stored response verbatim with `deduped: true`. The key
        was minted by the page and is the same end to end, so a double-click or a
        retry anywhere in the chain collapses onto one movement of coins.
      - a REFUSAL (not enough saved, frozen, no account, insufficient wallet) is the
        bank answering. It is `{"ok": false, "error": ...}` -- never "the bank is
        down", because "unavailable" on a banking page reads as "your money is gone".
      - anything else is a real failure and says so without leaking internals.
    """
    try:
        import bank_money as bmoney
    except Exception as e:
        log.exception("[banking] bank_money unavailable: %s", e)
        return {"ok": False, "error": "The bank's write path is not available."}

    key = str(body.get("idempotency_key") or "").strip()
    if not key:
        # Never mint one here: the caller mints it, per the house rule, so that a
        # retry carries the SAME key. A key invented at this layer would be new on
        # every attempt, which is idempotency theatre -- it would dedupe nothing.
        return {"ok": False, "error": "This action was submitted without an "
                                      "idempotency key; reload the page and retry."}
    try:
        args, kwargs = _WRITE_ARGS[op](body, key)
    except _BadField as e:
        return {"ok": False, "error": str(e)}
    except KeyError:
        log.error("[banking] no argument mapping for write op %r", op)
        return {"ok": False, "error": "The bank's write path is not available."}

    try:
        return getattr(bmoney, op)(*args, **kwargs)
    except bmoney.BankRefused as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        # Replay and LedgerError both live in ledger_v2; import lazily so this module
        # still loads in a process where the ledger is absent.
        import ledger_v2 as lv
        if isinstance(e, lv.Replay):
            stored = dict(e.body or {})
            stored["deduped"] = True
            return stored
        if isinstance(e, lv.LedgerError):
            return {"ok": False, "error": _ledger_reason(e), "code": getattr(e, "code", None)}
        log.exception("[banking] %s failed: %s", op, e)
        return {"ok": False, "error": f"The bank could not complete that "
                                      f"({type(e).__name__})."}


def _ledger_reason(e: Any) -> str:
    """A wallet refusal, said in the player's terms rather than the ledger's."""
    code = str(getattr(e, "code", "") or "")
    return {
        "insufficient": "You do not have enough available coins — coins held against "
                        "a live bid or auction cannot be moved.",
        "frozen": "This wallet is frozen.",
        "bad_amount": "That amount is not something the bank can move.",
    }.get(code, f"The bank declined that ({code or 'no reason given'}).")


def handle(method: str, path: str, params: Optional[dict] = None,
           body: Optional[dict] = None) -> dict:
    """Answer one Osentar API call locally. Never raises: returns the API's own
    `{"ok": false, "error": ...}` shape so the caller's existing handling applies."""
    params = params or {}
    body = body or {}
    try:
        # Every path below dereferences _bdb / _pol, which are None until _load()
        # runs. In production _local_available() gets there first, but nothing
        # GUARANTEED that -- a direct call raised AttributeError on NoneType and was
        # caught below as "the bank's local read failed", which names the wrong cause.
        if not _load():
            return {"ok": False,
                    "error": "The bank is not available in this process "
                             f"({_import_error or 'not loaded'})."}

        if path == "/api/v1/health":
            return {"ok": True, "service": "osentar-bank", "provider": "local",
                    "version": PROVIDER_VERSION, "ts": _now()}

        if path == "/api/v1/account":
            uid = str(params.get("user_id") or body.get("user_id") or "").strip()
            if not uid:
                return {"ok": False, "error": "No user id was supplied."}
            return _account(uid)

        if path == "/api/v1/staff/queue":
            return _staff_queue()

        if path == "/api/v1/staff/collections":
            return _staff_collections()

        if path in _LIVE_WRITES:
            return _write(_LIVE_WRITES[path], body)

        if path in _WRITE_PATHS:
            return {"ok": False, "error": _WRITE_REFUSAL, "code": "not_implemented_locally"}

        return {"ok": False, "error": f"Unknown bank endpoint {path}."}
    except Exception as e:
        log.exception("[banking] local provider failed on %s: %s", path, e)
        return {"ok": False, "error": f"The bank's local read failed ({type(e).__name__})."}
