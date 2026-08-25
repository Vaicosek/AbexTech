"""Serve Stakes' land-listing READ from the local database instead of over HTTP.

Why this exists
---------------
`run_all.py` starts core, bank and Stakes as three PROCESSES sharing one filesystem
and one `restocker.db`. `land_listings` is core's table, and it is sitting in the same
file the Stakes process can already open. Rendering the auction board therefore does
not need a network round trip to `/api/network/land/listings` — it needs a `SELECT`.
This module is that `SELECT`, answering the same path with the same
`{"ok": true, "listings": [...]}` shape, so `_build_land_board`, `_land_cache` and
every failure path in `stakes/app.py` stay exactly as they are.

It is modelled on `bank_local.py`, which did the same thing for `banking_web`.

Scope: ONE endpoint. Deliberately.
----------------------------------
**Only `GET /api/network/land/listings` is implemented, and nothing else may be.**

* **The land WRITES stay on HTTP** — bid, buy, create, cancel, close. Each one takes a
  hold, captures one, or releases one, and `ledger_v2.place_hold` / `capture_hold` /
  `release_hold` each open their OWN `_tx()`, which is not re-entrant. There is no
  `hold_move(conn, ...)` counterpart to `wallet_move(conn, ...)`, so a bid — place the
  new hold, release the outbid one, move `current_bid`, insert `land_bids` — cannot be
  composed into the one transaction `bank_money` gets to use. Running it as three
  transactions is exactly the multi-step window that `land_bids.status / attempts /
  refusals / last_error` and `land_listings.settle_stage / fee_stage` exist to survive,
  and that state machine already exists once, in core. A second one here, writing the
  same rows from a second process, is the "two implementations of one policy" failure
  the house rules name — with coins on the other end of it.
* **The token is not just transport auth.** `ledger_v2._resolve_service` maps
  `X-Service-Token` to a service name, and that name selects
  `SERVICE_SCOPES["estates"] = {read, transfer, hold}` — pointedly no `wallet.mint`.
  A direct-DB write path has no such gate: it would pass `service="estates"` as a
  string nothing verifies. Reads carry no scope, so converting the read costs nothing;
  converting a write would trade an enforced scope for an honour-system one.
* **The ORDERS board is not here either.** `orders` has no `qty` and no `pay` column
  (`coin_per_piece` is NULL on all 29 rows); `pay` is computed by core's
  `_coin_rates_for_order` from `items.coin` / `worker_cost` and the per-piece /
  per-stack / per-barrel unit dance. Recomputing that here would be a second
  implementation of order pricing — the exact bug that once printed "345,600c per
  stack" for a per-barrel rate. It converts when that helper is extracted into an
  import-safe module the way `bank_policy` and `ledger_v2` already are. Until then
  Stakes keeps calling core for orders.

What it will not invent
-----------------------
**`min_next_bid` is omitted.** It is the one field the board renders that is neither a
column nor a format conversion: it is derived from the current bid, the reserve and
`min_increment_pct` by a rule that lives in core's land module — which is not in this
tree and cannot be imported from this process. Deriving it here would be a second
implementation of a money figure, and the harmful direction is cheap to reach: show a
minimum a coin under core's and every player who types it gets refused. So the key is
left out. `BidModal` already treats a missing hint as "no hint", the modal still
accepts a blank amount, and core still picks the true minimum — which is the one
implementation, staying the only one. It comes back the moment core's minimum-bid rule
is extracted somewhere both processes can import.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger("stakes.local")

#: Version reported alongside the provider choice, so an operator reading the startup
#: line can tell which side answered the board.
PROVIDER_VERSION = "local-1"

_import_error: str = ""


def _db_path() -> Optional[str]:
    """Where core keeps `land_listings`, asked of the module that owns the answer.

    `ledger_v2._db_path()` reads `Restocker_db.DB_PATH`, which is the one place the
    path is decided. Hardcoding it here, or reading an env var of our own, is how a
    satellite ends up reading a different file from the bot it is mirroring.

    The import is lazy, and it is deliberately `ledger_v2` (which pulls
    `Restocker_db`) and nothing above it. The bank process already imports exactly
    this pair — see `bank_money` — so it is a known-safe module body. `Restocker_main`
    is the one that must never be imported here, for the reason `bank_local._load()`
    records about `bank_main`: a module body that calls `logging.basicConfig()` and
    constructs a `commands.Bot` would hand this process a second Discord bot as a
    side effect of drawing a board.
    """
    global _import_error
    try:
        import ledger_v2 as lv
        return lv._db_path()
    except Exception as e:                       # pragma: no cover - misconfigured tree
        _import_error = f"{type(e).__name__}: {e}"
        log.warning("[stakes] local provider unavailable: %s", _import_error)
        return None


def _connect() -> sqlite3.Connection:
    """A short-lived, read-only connection of our own — NOT `ledger_v2._conn()`.

    Two reasons it is not the ledger's:
      * that one is thread-local and shared, and this read is dispatched with
        `asyncio.to_thread`, so it would be touched from arbitrary worker threads;
      * it is a read-write handle in autocommit mode, and this module has no business
        holding one.

    `PRAGMA query_only=1` makes the refusal structural rather than a promise: if
    anything in here ever tries to write, SQLite refuses it. A plain connection is
    opened rather than `file:...?mode=ro` because a read-only handle cannot create the
    `-shm` file a WAL database needs, and Stakes may well open this file before core
    has.
    """
    path = _db_path()
    if not path:
        raise RuntimeError(_import_error or "no database path")
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=1")
    except sqlite3.Error:                        # pragma: no cover - ancient sqlite
        pass
    return conn


def available() -> bool:
    """True when the land table is reachable in the database core is using.

    Checks the TABLE, not just the path: a database that has never had core's schema
    applied opens perfectly well, and answering "the board is live" against it would
    turn a missing table into a permanently empty auction board — which reads as
    "every listing closed", not as "this bot is misconfigured".
    """
    try:
        with _closing(_connect()) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='land_listings'"
            ).fetchone()
            return row is not None
    except Exception as e:
        log.warning("[stakes] local land table check failed: %s", e)
        return False


class _closing:
    """`contextlib.closing`, spelled out to keep the import list short."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, *exc: Any) -> None:
        try:
            self.conn.close()
        except Exception:                        # pragma: no cover
            pass


# ══════════════════════════════════════════════════════════════════════════
# GET /api/network/land/listings
# ══════════════════════════════════════════════════════════════════════════

def _epoch(value: Any) -> Optional[int]:
    """`ends_at` as a unix timestamp, or None if it cannot be read as one.

    A format conversion of a stored value, not a computation: the row already says
    when the auction ends, this only restates it in the form Discord's `<t:...>`
    wants. SQLite's own `datetime('now')` — the column default — writes naive UTC,
    and a naive string is therefore read as UTC. Getting that wrong would not raise;
    it would silently move every countdown on the board by hours.
    """
    if value in (None, ""):
        return None
    raw = str(value).strip().replace(" ", "T")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        log.warning("[stakes] unreadable ends_at %r — the listing is returned without "
                    "a closing time rather than with a guessed one", value)
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _photos(raw: Any) -> list:
    """The photo list as stored. A JSON array is the shape core writes.

    Anything else that is plainly a single URL is wrapped; anything else again is
    dropped, and `_build_listing_embed` falls back to `image_url` on its own. A
    mangled value is not turned into a picture nobody uploaded.
    """
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(p) for p in raw if p]
    text = str(raw).strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, list):
            return [str(p) for p in parsed if p]
    if text.startswith("http"):
        return [text]
    return []


def _num(value: Any) -> Optional[float]:
    """A stored REAL, or None. None and 0 are different answers on this board:
    `buy_now` of None means no buy-it-now button, and `current_bid` of None means
    'No bids yet' rather than a bid of nothing."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_to_listing(r: sqlite3.Row) -> dict:
    """One `land_listings` row in the shape the board already reads.

    Every key here is either a column or a restatement of one. `min_next_bid` is
    absent on purpose — see the module docstring.
    """
    out = {
        "id": int(r["id"]),
        "title": r["title"],
        "kind": r["kind"],
        "mode": r["mode"],
        "category": r["category"],
        "description": r["description"],
        "image_url": r["image_url"],
        "chunks": _num(r["chunks"]),
        "coords": r["coords"],
        "reserve": _num(r["reserve"]),
        "buy_now": _num(r["buy_now"]),
        "current_bid": _num(r["current_bid"]),
    }
    photos = _photos(r["photos"])
    if photos:
        out["photos"] = photos
    ends = _epoch(r["ends_at"])
    if ends is not None:
        out["ends_at_epoch"] = ends
    return out


#: Soonest-closing first, because that is the order an auction board is read in, and
#: the board renders at most 25 rows — so the ordering decides which 25 those are.
#: Listings with no end time sort last; ties break on id so the order is stable
#: between refreshes and a board does not reshuffle itself for no reason.
_LISTINGS_SQL = """
    SELECT id, title, kind, mode, category, description, photos, image_url,
           chunks, coords, reserve, buy_now, current_bid, ends_at
      FROM land_listings
     WHERE status = 'active'
     ORDER BY (ends_at IS NULL), ends_at ASC, id ASC
"""


def _listings() -> dict:
    with _closing(_connect()) as conn:
        rows = conn.execute(_LISTINGS_SQL).fetchall()
    return {"ok": True, "listings": [_row_to_listing(r) for r in rows]}


# ══════════════════════════════════════════════════════════════════════════
# Dispatch
# ══════════════════════════════════════════════════════════════════════════

#: Read-only, and one entry. If you are here to add `/api/network/land/bid`,
#: `/buy`, `/create`, `/cancel` or `/close` — read the module docstring first: those
#: move coins through holds, core owns the only state machine for them, and this
#: process has no scoped identity to move money under.
_READS = {
    "/api/network/land/listings": _listings,
}


def handle(method: str, path: str, params: Optional[dict] = None,
           body: Optional[dict] = None) -> dict:
    """Answer one network API read locally. NEVER raises.

    The caller turns `ok: false` into "leave the last board up", so a failure has to
    come back as a value. A raise out of here would propagate into the refresh loop
    and take the board down with it — worse than a stale board, because a stale board
    is at least still showing real listings.
    """
    try:
        fn = _READS.get(path)
        if fn is None:
            return {"ok": False,
                    "error": f"{path} has no local implementation — it stays on core's "
                             f"HTTP API.",
                    "code": "not_implemented_locally"}
        if str(method or "GET").upper() != "GET":
            return {"ok": False, "error": f"{path} is a read; {method} is not served "
                                          f"locally.", "code": "method_not_allowed"}
        return fn()
    except Exception as e:
        log.warning("[stakes] local read failed on %s: %s", path, e)
        return {"ok": False, "error": f"The local land read failed ({type(e).__name__})."}
