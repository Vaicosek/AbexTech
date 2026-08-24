"""
core_profile.py — the CROSS-LINKED customer view: wallet + loyalty + IGNs + stocks.

WHY THIS MODULE EXISTS
    `ledger_v2` centralised money and did it well. But loyalty, IGNs and the
    per-market point ledgers were never exposed on any API, so the bank bot and the
    estates bot physically could not read them — which is why "one company, one
    customer identity" did not hold in practice.

    Everything is already keyed on the Discord user id, in one database. So this is a
    read-aggregation problem, not a data-model problem: nothing has to move.

WHAT IT ADDS  (mounts next to ledger_v2, same host, same auth header)
    GET  /api/v2/profile          the whole customer in one call — wallet, loyalty,
                                  tier, per-market points, IGNs, stock positions
    GET  /api/v2/loyalty          points, total_earned, tier, per-market breakdown
    POST /api/v2/loyalty/award    award points          (scope loyalty.write)
    POST /api/v2/loyalty/redeem   spend points          (scope loyalty.write)
    GET  /api/v2/igns             igns for a user, or the user behind an ign

DELIBERATELY NOT DONE HERE
    * It does not touch a single money path. Coins remain ledger_v2's, exclusively.
    * It does not re-implement tiers. `LOYALTY_TIERS` / `_loyalty_tier` are imported
      from Restocker_main so there is exactly one definition of what "Veteran" means.
    * It does not read bank.db. Savings/loans/bonds belong to the bank service; this
      returns the core-owned half and the bank joins on the same user_id.

REDEEM IS CLAIM-FIRST, ON PURPOSE
    `Restocker_db.add_loyalty_points(uid, -n)` is `points = points + (-n)` with NO floor,
    so redeeming 100 points from a 50-point balance leaves −50. Every redeem here is one
    conditional UPDATE carrying the whole precondition:

        UPDATE loyalty SET points = points - :n
         WHERE user_id = :u AND points >= :n

    and a `rowcount == 1` check. Insufficient points FAIL; they never go negative.
    Same shape ledger_v2 uses for coins.

MOUNT IT
    # in Restocker_web.start_webserver(), right after ledger_v2:
    try:
        import core_profile
        core_profile.register_profile_routes(app)
    except Exception as _e:
        print(f"⚠️  core profile not registered: {_e}")
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from typing import Any, Optional

try:
    from aiohttp import web
except Exception:                                    # pragma: no cover
    web = None

import ledger_v2

log = logging.getLogger("core_profile")

API_VERSION = "1.0"

# ── scopes ───────────────────────────────────────────────────────────────────
# Kept in THIS module rather than mutating ledger_v2.SERVICE_SCOPES: the ledger's
# scope map governs money, and a loyalty feature has no business editing it.
SCOPE_LOYALTY_READ = "loyalty.read"
SCOPE_LOYALTY_WRITE = "loyalty.write"
SCOPE_IDENTITY_READ = "identity.read"

#: estates awards points today (cogs/land_exchange.py calls add_loyalty_points on a
#: settled lot), so it needs write. The bank only READS, to price a tier — it must not
#: be able to mint loyalty any more than it should be able to mint someone else's coins.
PROFILE_SCOPES: dict[str, frozenset[str]] = {
    "osentar": frozenset({SCOPE_LOYALTY_READ, SCOPE_IDENTITY_READ}),
    "estates": frozenset({SCOPE_LOYALTY_READ, SCOPE_LOYALTY_WRITE, SCOPE_IDENTITY_READ}),
    "games":   frozenset({SCOPE_LOYALTY_READ, SCOPE_IDENTITY_READ}),
}

MAX_AWARD = 1_000_000          # a sane ceiling; a bug should fail, not award a million
IDEM_TTL = 24 * 3600

_local = threading.local()


# ── db ───────────────────────────────────────────────────────────────────────
def _conn() -> sqlite3.Connection:
    """Own connection, autocommit, so we can BEGIN IMMEDIATE — same reasoning as
    ledger_v2._conn(): never change isolation on Restocker's shared connection."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        import Restocker_db as db
        conn = sqlite3.connect(str(db.DB_PATH), check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        _local.conn = conn
        _ensure_tables(conn)
    return conn


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS loyalty_idem (
            key         TEXT PRIMARY KEY,
            service     TEXT NOT NULL,
            response    TEXT NOT NULL,
            created_at  REAL NOT NULL
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS loyalty_audit (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT NOT NULL DEFAULT (datetime('now')),
            service     TEXT NOT NULL,
            action      TEXT NOT NULL,
            user_id     TEXT NOT NULL,
            points      REAL NOT NULL,
            market_id   TEXT,
            reason      TEXT
        )""")


def _audit(conn, service: str, action: str, uid: str, pts: float,
           market_id: Optional[str], reason: str) -> None:
    try:
        conn.execute("INSERT INTO loyalty_audit (service, action, user_id, points, "
                     "market_id, reason) VALUES (?,?,?,?,?,?)",
                     (service, action, str(uid), float(pts), market_id, reason[:300]))
    except Exception:
        log.exception("loyalty audit write failed")


# ── auth ─────────────────────────────────────────────────────────────────────
def _err(msg: str, status: int = 400, code: str = ""):
    body = {"ok": False, "error": msg}
    if code:
        body["code"] = code
    return web.json_response(body, status=status)


def _auth(request, scope: str) -> tuple[Optional[str], Any]:
    """Reuse the ledger's constant-time service resolution — one token per service,
    one place that knows how to check it. Returns (service, error_response)."""
    service = ledger_v2._resolve_service(request)
    if not service:
        return None, _err("Bad or missing X-Service-Token.", 401, "unauthorized")
    if scope not in PROFILE_SCOPES.get(service, frozenset()):
        return None, _err(f"Service '{service}' lacks scope '{scope}'.", 403, "forbidden")
    return service, None


def _uid(request) -> str:
    return str(request.query.get("user_id") or "").strip()


async def _body(request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


# ── tiers: imported, never redefined ─────────────────────────────────────────
def _tier_for(points: float) -> dict:
    """One definition of a tier, and it lives in Restocker_main."""
    try:
        import Restocker_main as _m
        t = dict(_m._loyalty_tier(float(points)))
        nxt = None
        for row in _m.LOYALTY_TIERS:
            if row["min_pts"] > float(points):
                nxt = row
                break
        t["next_tier"] = ({"name": nxt["name"], "min_pts": nxt["min_pts"],
                           "points_needed": nxt["min_pts"] - float(points)} if nxt else None)
        return t
    except Exception as e:
        log.warning("tier lookup unavailable: %s", e)
        return {"tier": 0, "name": "unknown", "interest_weekly_pct": 0,
                "payout_bonus_pct": 0, "next_tier": None}


# ── reads ────────────────────────────────────────────────────────────────────
def _loyalty_payload(user_id: str) -> dict:
    import Restocker_db as db
    rec = db.get_loyalty(str(user_id)) or {}
    pts = float(rec.get("points") or 0)
    markets: dict[str, float] = {}
    try:
        for r in _conn().execute(
                "SELECT market_id, points FROM market_loyalty_ledger "
                "WHERE user_id=? AND points <> 0 ORDER BY points DESC", (str(user_id),)):
            markets[str(r["market_id"])] = float(r["points"] or 0)
    except Exception:
        log.exception("per-market loyalty read failed")
    return {
        "user_id": str(user_id),
        "points": pts,
        "total_earned": float(rec.get("total_earned") or 0),
        "last_activity": rec.get("last_activity"),
        "tier": _tier_for(pts),
        "markets": markets,
    }


def _igns_payload(user_id: str) -> dict:
    import Restocker_db as db
    try:
        igns = list(db.get_igns(str(user_id)) or [])
    except Exception:
        igns = []
    return {"user_id": str(user_id), "igns": igns, "primary": (igns[0] if igns else None)}


# ── handlers ─────────────────────────────────────────────────────────────────
async def h_profile(request):
    """Everything about one customer, in one call. This is the endpoint that makes
    'one company' true for a bot that owns none of this data."""
    service, err = _auth(request, SCOPE_IDENTITY_READ)
    if err:
        return err
    uid = _uid(request)
    if not uid:
        return _err("Missing user_id.")
    out: dict[str, Any] = {"ok": True, "user_id": uid, "service": service}
    # wallet — ledger_v2 stays the only thing that reads money
    try:
        out["wallet"] = ledger_v2.get_balance(uid)
    except Exception as e:
        out["wallet"] = {"error": f"{type(e).__name__}"}
        log.warning("wallet read failed for %s: %s", uid, e)
    out["loyalty"] = _loyalty_payload(uid)
    out["identity"] = _igns_payload(uid)
    try:
        import Restocker_db as db
        out["stocks"] = [
            {"market_id": h.get("market_id"), "shares": float(h.get("shares") or 0),
             "cost_basis": float(h.get("cost_basis") or 0)}
            for h in (db.get_user_holdings(uid) or [])
        ] if hasattr(db, "get_user_holdings") else []
    except Exception:
        out["stocks"] = []
    return web.json_response(out)


async def h_loyalty(request):
    service, err = _auth(request, SCOPE_LOYALTY_READ)
    if err:
        return err
    uid = _uid(request)
    if not uid:
        return _err("Missing user_id.")
    return web.json_response({"ok": True, **_loyalty_payload(uid)})


async def h_igns(request):
    """Both directions: ?user_id= → their igns, ?ign= → who owns it."""
    service, err = _auth(request, SCOPE_IDENTITY_READ)
    if err:
        return err
    import Restocker_db as db
    ign = str(request.query.get("ign") or "").strip()
    if ign:
        owner = db.get_user_id_by_ign(ign)
        return web.json_response({"ok": True, "ign": ign, "user_id": owner,
                                  "found": bool(owner)})
    uid = _uid(request)
    if not uid:
        return _err("Pass user_id= or ign=.")
    return web.json_response({"ok": True, **_igns_payload(uid)})


def _replay(key: str, service: str) -> Optional[dict]:
    if not key:
        return None
    conn = _conn()
    conn.execute("DELETE FROM loyalty_idem WHERE created_at < ?", (time.time() - IDEM_TTL,))
    row = conn.execute("SELECT response FROM loyalty_idem WHERE key=?", (key,)).fetchone()
    return json.loads(row["response"]) if row else None


def _remember(key: str, service: str, payload: dict) -> None:
    if not key:
        return
    try:
        _conn().execute("INSERT OR REPLACE INTO loyalty_idem (key, service, response, "
                        "created_at) VALUES (?,?,?,?)",
                        (key, service, json.dumps(payload), time.time()))
    except Exception:
        log.exception("idempotency store failed")


async def h_award(request):
    service, err = _auth(request, SCOPE_LOYALTY_WRITE)
    if err:
        return err
    body = await _body(request)
    uid = str(body.get("user_id") or "").strip()
    reason = str(body.get("reason") or "")[:300]
    market_id = (str(body.get("market_id") or "").strip() or None)
    key = str(body.get("idempotency_key") or "").strip()
    try:
        pts = float(body.get("points"))
    except Exception:
        return _err("points must be a number.")
    if not uid:
        return _err("Missing user_id.")
    if pts <= 0:
        return _err("points must be > 0 — use /loyalty/redeem to spend.")
    if pts > MAX_AWARD:
        return _err(f"points exceeds the {MAX_AWARD:,} ceiling.", 400, "too_large")
    prior = _replay(key, service)
    if prior:
        return web.json_response(prior)

    import Restocker_db as db
    total = db.add_loyalty_points(uid, pts)
    if market_id:
        try:
            db.add_market_loyalty_points(uid, market_id, pts, reason or "core award")
        except TypeError:
            db.add_market_loyalty_points(uid, market_id, pts)
        except Exception:
            log.exception("per-market award failed (%s/%s)", uid, market_id)
    conn = _conn()
    _audit(conn, service, "award", uid, pts, market_id, reason)
    payload = {"ok": True, "user_id": uid, "awarded": pts, "points": float(total),
               "tier": _tier_for(total), "market_id": market_id}
    _remember(key, service, payload)
    return web.json_response(payload)


async def h_redeem(request):
    """Claim-first: the precondition rides in the UPDATE, and we check rowcount.
    Insufficient points FAIL — they never go negative (which a bare
    add_loyalty_points(-n) would happily do)."""
    service, err = _auth(request, SCOPE_LOYALTY_WRITE)
    if err:
        return err
    body = await _body(request)
    uid = str(body.get("user_id") or "").strip()
    reason = str(body.get("reason") or "")[:300]
    key = str(body.get("idempotency_key") or "").strip()
    try:
        pts = float(body.get("points"))
    except Exception:
        return _err("points must be a number.")
    if not uid:
        return _err("Missing user_id.")
    if pts <= 0:
        return _err("points must be > 0.")
    prior = _replay(key, service)
    if prior:
        return web.json_response(prior)

    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "UPDATE loyalty SET points = points - ?, updated_at = datetime('now') "
            "WHERE user_id = ? AND points >= ?", (pts, uid, pts))
        if cur.rowcount != 1:
            conn.execute("ROLLBACK")
            row = conn.execute("SELECT points FROM loyalty WHERE user_id=?", (uid,)).fetchone()
            have = float(row["points"]) if row else 0.0
            return _err(f"Insufficient points: has {have:g}, needs {pts:g}.",
                        409, "insufficient_points")
        row = conn.execute("SELECT points FROM loyalty WHERE user_id=?", (uid,)).fetchone()
        left = float(row["points"]) if row else 0.0
        _audit(conn, service, "redeem", uid, -pts, None, reason)
        conn.execute("COMMIT")
    except sqlite3.Error as e:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        log.exception("loyalty redeem failed for %s", uid)
        return _err(f"Redeem failed: {type(e).__name__}", 500, "db_error")
    payload = {"ok": True, "user_id": uid, "redeemed": pts, "points": left,
               "tier": _tier_for(left)}
    _remember(key, service, payload)
    return web.json_response(payload)


async def h_health(request):
    """Public — says the module is mounted, nothing about any user."""
    return web.json_response({"ok": True, "service": "core-profile",
                              "version": API_VERSION,
                              "services": sorted(PROFILE_SCOPES)})


_ROUTES = [
    ("get",  "/health",          h_health),
    ("get",  "/profile",         h_profile),
    ("get",  "/loyalty",         h_loyalty),
    ("post", "/loyalty/award",   h_award),
    ("post", "/loyalty/redeem",  h_redeem),
    ("get",  "/igns",            h_igns),
]


def register_profile_routes(app: Any, prefix: str = "/api/v2") -> None:
    if web is None:
        log.warning("[core_profile] aiohttp unavailable — not registered.")
        return
    for method, path, handler in _ROUTES:
        (app.router.add_get if method == "get" else app.router.add_post)(prefix + path, handler)
    log.info("[core_profile] routes registered under %s", prefix)
    print(f"👤  Core profile v{API_VERSION}: {prefix}/profile, /loyalty, /igns", flush=True)
