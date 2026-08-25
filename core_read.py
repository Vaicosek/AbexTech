"""Core's read-only bank API, served in-process instead of over HTTP.

The Bank bot reaches core through `restocker_client` at `/api/v1/bank/*`, handled by
`bank_api.py` in core's web process. Now that both run in one container against one
`restocker.db`, the READ half of that API has nothing to cross: `h_stocks`,
`h_portfolio` and `h_balance` all reach `Restocker_db` and nothing else.

This module mirrors those three handlers exactly -- same fields, same names, same
coercions -- so `bank_main`'s call sites and everything downstream of them are
unchanged. It is the `bank_local.py` pattern pointed the other way.

WHAT IS DELIBERATELY NOT HERE: buying and selling
-------------------------------------------------
`h_stock_buy` and `h_stock_sell` do NOT reach `Restocker_db`. They do:

    r = await _m.run_on_bot_loop(_m.exec_stock_trade, "buy", ...)

`run_on_bot_loop` awaits a synchronous, state-mutating function ON CORE'S OWN EVENT
LOOP -- that is how core serialises trades against its in-memory state, and it is a
property of the running bot, not of the database. The Bank is a SEPARATE OS PROCESS
(see run_all.py), so there is no way to reach that loop except by asking core over
HTTP. Trades therefore stay on `client_rs`, and that is correct rather than unfinished:
a direct-DB trade would bypass the serialisation the trade engine is built on, and
would also bypass the slippage bounds `_trade_bounds` forwards.

`loyalty_tier` is the one field dropped. `bank_api._balance_payload` computes it via
`Restocker_main._loyalty_tier`, and importing `Restocker_main` from this process would
construct a second bot. Nothing in `bank_main` reads that field -- both `get_balance`
call sites use `["coins"]` -- so it is reported as None rather than faked.
"""
from __future__ import annotations

import logging
import os.path
import sys
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("bank.core_read")

_ROOT = Path(__file__).resolve().parent
_db: Any = None
_import_error: str = ""
_state: Optional[bool] = None


def _load() -> bool:
    global _db, _import_error
    if _db is not None:
        return True
    if _import_error:
        return False
    try:
        p = str(_ROOT)
        if p not in sys.path:
            sys.path.append(p)
        import Restocker_db as db
        _db = db
        return True
    except Exception as e:
        _import_error = f"{type(e).__name__}: {e}"
        log.warning("[core_read] unavailable: %s", _import_error)
        return False


def available() -> bool:
    """True when core's tables are readable in the database this process opened.

    Probes for the `markets` TABLE, not just the import: `Restocker_db` imports fine
    against a database that has never been created, and answering "core is up" there
    would turn a missing schema into an empty market list -- which reads as "no markets
    exist" rather than as an error.
    """
    global _state
    if _state is not None:
        return _state
    _state = False
    if not _load():
        return False
    try:
        import ledger_v2 as lv
        if os.path.realpath(str(_db.DB_PATH)) != os.path.realpath(str(lv._db_path())):
            log.error("[core_read] refusing: reads would come from %s while the ledger "
                      "writes %s", _db.DB_PATH, lv._db_path())
            return False
        with _db.db() as c:
            row = c.execute("SELECT name FROM sqlite_master WHERE type='table' "
                            "AND name='markets'").fetchone()
        _state = row is not None
    except Exception as e:
        log.warning("[core_read] probe failed: %s", e)
        _state = False
    return _state


# ── the three read handlers, mirrored ────────────────────────────────────────

def get_balance(user_id) -> dict:
    """`bank_api._balance_payload`, minus the tier. See the module docstring."""
    b = _db.get_balance(str(user_id)) or {}
    points = 0.0
    try:
        points = float((_db.get_loyalty(str(user_id)) or {}).get("points") or 0)
    except Exception:
        log.debug("[core_read] loyalty lookup failed for %s", user_id, exc_info=True)
    return {
        "user_id": str(user_id),
        "coins": int(b.get("coins") or 0),
        "principal": float(b.get("principal") or 0),
        "loyalty_points": points,
        "loyalty_tier": None,
        "lp": points,
    }


def list_stocks() -> list[dict]:
    """`bank_api.h_stocks`. Only markets whose share listing is ACTIVE."""
    out = []
    try:
        markets = _db.get_markets() if hasattr(_db, "get_markets") else {}
    except Exception:
        markets = {}

    # get_markets() returns a DICT KEYED BY market_id, not a list. bank_api.h_stocks
    # iterates it as a list, so `mk` is the key STRING, `isinstance(mk, dict)` is False,
    # and every market is skipped -- which is why /invest list returned zero markets
    # against a database holding two active listings. Handle both shapes.
    if isinstance(markets, dict):
        pairs = list(markets.items())
    else:
        pairs = [((m.get("market_id") or m.get("id")) if isinstance(m, dict) else None, m)
                 for m in (markets or [])]

    for key, mk in pairs:
        mid = key or ((mk.get("market_id") or mk.get("id")) if isinstance(mk, dict) else None)
        if not mid:
            continue
        listing = _db.get_market_shares(mid)
        if not listing or not listing.get("active"):
            continue
        out.append({
            "market_id": mid,
            "name": (mk.get("name") if isinstance(mk, dict) else None) or mid,
            "price": float(listing.get("share_price") or 0),
            "shares_outstanding": float(listing.get("shares_outstanding") or 0),
            "pe": float(listing.get("pe_multiplier") or 0),
        })
    return out


def portfolio(user_id) -> list[dict]:
    """`bank_api.h_portfolio`. Valuation is shares x the STORED share_price.

    The price is read, never derived. Core computes it from the trailing three-report
    mean, the growth P/E and the book-value floor, and recomputing that here would be a
    second implementation of the number the whole exchange is priced on.
    """
    uid = str(user_id)
    out = []
    for h in _db.get_portfolio(uid):
        mid = h.get("market_id")
        listing = _db.get_market_shares(mid) or {}
        price = float(listing.get("share_price") or 0)
        shares = float(h.get("shares") or 0)
        out.append({
            "market_id": mid,
            "shares": shares,
            "price": price,
            "value": shares * price,
            "cost_basis": float(h.get("cost_basis") or 0),
        })
    return out
