"""
abex_live.py — the live rows behind the Abex screens.

`abex_data.py` holds the design's sample rows; the screens read them so the design
could be looked at before anything was wired. This module returns the same row
shapes from the real database, one screen at a time, so a screen can be promoted
without touching its markup.

Two rules it follows, both learned the hard way in this codebase:

**Call the canonical function, never a parallel one.** Grade, index weight and the
month's net all have exactly one implementation in `Restocker_main`
(`_backing_rating`, `_group_net_for_month`, `_market_ticker`). A second copy here
would drift from the one the bot quotes, and the screen would disagree with
`/stock price` about the same market.

**Do not invent a column.** The design shows "Next report" as a date. Nothing in
this system stores a per-market report due date — reports arrive when an owner
files them — so this returns the month each market last filed instead, and says
so. A date computed from nothing looks exactly like a date that means something.

`Restocker_main` is imported lazily inside each function. In production the web
server shares a process with the bot, so it is already loaded; in a container
without discord.py installed the import fails and the caller falls back to the
sample rows rather than taking the page down.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("abex_live")

_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")


def _month_name(month_key: Optional[str]) -> str:
    """`2026-08` -> `August 2026`. A month key is an id; a month is a name."""
    try:
        y, m = str(month_key).split("-")[:2]
        return f"{_MONTHS[int(m) - 1]} {y}"
    except Exception:
        return "—"


def _core():
    import Restocker_main as core  # noqa: WPS433 - lazy on purpose, see docstring
    return core


def _db():
    import Restocker_db as db  # noqa: WPS433
    return db


def _owner_name(db, owner_id: Optional[str]) -> str:
    """The owner's in-game name, never their Discord id.

    An id is not a name, and a page that prints one has given up. When no IGN is
    registered the column says so rather than falling back to the number.
    """
    if not owner_id:
        return "no owner recorded"
    try:
        return db.get_ign(str(owner_id)) or "IGN not registered"
    except Exception:
        return "IGN not registered"


def _latest_month(db, market_id: str) -> Optional[str]:
    """The most recent month this market has actually filed.

    `Restocker_db._get_conn` is the module's own accessor — going around it with a
    fresh `sqlite3.connect` would open a second connection with different pragmas,
    which is the bug class that cost a migration once already.
    """
    try:
        row = db._get_conn().execute(
            "SELECT MAX(month) FROM csn_history WHERE market_id=?",
            (market_id,)).fetchone()
        return row[0] if row and row[0] else None
    except Exception as exc:
        log.warning("[abex_live] last month for %s unreadable: %s", market_id, exc)
        return None


def _index_weights(core, db) -> dict:
    """Each listed market's share of the Abexilas index.

    `_backing_rating` returns a `weight` that SCALES a market's cap for the index —
    its own docstring says so — it is not the share itself. Printing it as the
    share was wrong by an order of magnitude: GreyHames read 85.6% when it holds
    about a seventh of the index. The share is the scaled cap over the total.

    A market that is not listed has no cap and therefore no weight, and gets no
    number rather than a zero.
    """
    caps = {}
    try:
        listings = db.get_public_markets() or {}
    except Exception:
        return {}
    for mid, listing in listings.items():
        price = float(listing.get("share_price") or 0)
        out = float(listing.get("shares_outstanding") or 0)
        if price <= 0 or out <= 0:
            continue
        try:
            _grade, weight, _b, _t = core._backing_rating(mid)
        except Exception:
            weight = 0.0
        caps[mid] = price * out * float(weight or 0)
    total = sum(caps.values())
    if total <= 0:
        return {}
    return {mid: 100.0 * cap / total for mid, cap in caps.items()}


def _ticker_of(core, market_id: str) -> str:
    """The market's ticker, from the bot's own resolver."""
    try:
        return core._market_ticker(market_id)
    except Exception:
        return str(market_id)[:4].upper()


def markets() -> Optional[list[tuple]]:
    """Rows for the Markets screen, in `abex_data.MARKETS` shape.

    (ticker, name, owner, grade, backing, last net, index weight, last report)

    Returns None when the bot's modules are not importable, so the caller can
    fall back to the design's rows instead of rendering an empty table.
    """
    try:
        core, db = _core(), _db()
    except Exception as exc:  # pragma: no cover - only in a bare container
        log.warning("[abex_live] markets unavailable: %s", exc)
        return None

    try:
        registry = db.get_markets() or {}
    except Exception as exc:
        log.warning("[abex_live] market registry unreadable: %s", exc)
        return None

    weights = _index_weights(core, db)
    try:
        listed = set(db.get_public_markets() or {})
    except Exception:
        listed = set()
    rows = []
    for market_id, market in registry.items():
        if not market.get("active", 1):
            continue
        # A grade only means something for a listed market: `_backing_rating`
        # divides by market cap, and an unlisted market has none, so it comes back
        # C — which reads as "under 0.3x backed" when the truth is "not rated".
        # Fourteen markets were being told they were junk for not being listed.
        if market_id in listed:
            try:
                # The scaling weight is read separately, in `_index_weights`, where
                # it becomes a share of the index rather than a factor.
                grade, _scale, backed_pct, target_pct = core._backing_rating(market_id)
            except Exception:
                grade, backed_pct, target_pct = "—", 0.0, 0.0
            backing_cell = f"{(float(backed_pct) / float(target_pct)) if target_pct else 0.0:,.2f}×"
        else:
            grade, backing_cell = "not rated", "—"
        month = _latest_month(db, market_id)
        # This market's own net, not `_group_net_for_month` — that one rolls up
        # every member of the group plus their hive ledgers, which is right for a
        # bank statement and wrong for a column headed "Last net" on a row that
        # names one market. GreyHames read 4,864,129c against its own 660,151c.
        net = 0.0
        if month:
            try:
                months = (core._load_csn_for_market(market_id) or {}).get("months", {}) or {}
                net = float((months.get(month) or {}).get("net", 0) or 0)
            except Exception as exc:
                log.warning("[abex_live] net for %s unreadable: %s", market_id, exc)
        try:
            ticker = core._market_ticker(market_id)
        except Exception:
            ticker = market_id[:4].upper()
        rows.append((
            ticker,
            market.get("name") or market_id,
            _owner_name(db, market.get("owner_id")),
            str(grade),
            backing_cell,
            f"{net:,.0f}c",
            (f"{weights[market_id]:,.1f}%" if market_id in weights else "—"),
            _month_name(month),
        ))

    # Best grade first, then by index weight — the same order the design shows,
    # and the order somebody comparing markets actually wants.
    order = {g: i for i, g in enumerate(
        ("AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "C", "D",
         "not rated", "—"))}
    def _weight_value(cell: str) -> float:
        try:
            return float(cell.rstrip("%").replace(",", ""))
        except ValueError:
            return -1.0

    rows.sort(key=lambda r: (order.get(r[3], 99), -_weight_value(r[6])))
    return rows


def nav_counts(user_id: str = "") -> dict:
    """Live counts for the nav, keyed by nav entry.

    Spec §3 is explicit that these are data, not decoration: "recompute them from
    data, don't hardcode". The design ships 8 / 13 / 7 / 6 / 3 / 2 / 3 as part of
    its picture, and a sidebar that keeps those next to live pages tells a reader
    there are three unread messages when there are none — a wrong number in the
    one place he looks before deciding whether to click.

    So every entry here is counted or blank. An entry mapped to "" shows no badge
    at all, which is the honest answer where nobody knows the number; an entry
    missing from this dict falls back to the tree's own figure, and nothing is
    left missing on purpose.

    `user_id` is only for the counts that are about the reader — Messages. Called
    without one, that count is blank rather than somebody else's.
    """
    out: dict = {}
    try:
        db = _db()
    except Exception:
        return out
    try:
        registry = db.get_markets() or {}
        out["markets"] = sum(1 for m in registry.values() if m.get("active", 1))
    except Exception:
        pass
    try:
        out["stocks"] = len(db.get_public_markets() or {})
    except Exception:
        pass
    try:
        open_orders = sum(1 for o in (db.load_orders() or [])
                          if str(o.get("status") or "").lower() == "open")
        out["work"] = open_orders
        out["orders"] = open_orders
    except Exception:
        pass
    try:
        # Two auction houses, counted apart: Auctions is items, Claims is land.
        # One combined figure on either badge is a number for a table nobody can
        # see.
        listings = db.get_active_land_listings() or []
        out["auctions"] = sum(1 for l in listings
                              if str(l.get("kind") or "item") == "item")
        out["lands"] = sum(1 for l in listings if str(l.get("kind") or "") == "land")
    except Exception:
        pass
    if user_id:
        try:
            import messages_web
            out["messages"] = messages_web._unread_total(str(user_id))
        except Exception:
            pass
    # Blank, not the design's number, for everything still uncounted.
    for key in ("investor", "mine", "mine.report"):
        out.setdefault(key, "")
    # Orders is Work's own section now, and it means "orders YOU posted" — a
    # figure this function has no reader to compute. The open-jobs count already
    # sits on Work directly above it; repeating it here would badge the anchor
    # with a number that is not what the anchor counts.
    out["orders"] = ""
    out.setdefault("messages", "")
    # A zero badge is noise — "Auctions 0" says less than "Auctions".
    return {k: ("" if v == 0 else v) for k, v in out.items()}


def stocks(user_id: str) -> Optional[dict]:
    """The viewer's positions, plus how the price is set for their biggest one.

    Returns `{"rows": [...], "formula": [...], "market": name}` in the shapes
    `abex_screens.stocks` expects, or None when the bot's modules are absent.

    The design's last column is "Next" — the date the position next settles. There
    is no such date in this system: a market settles when its owner files. It shows
    the month each market was last priced instead.
    """
    try:
        core, db = _core(), _db()
    except Exception as exc:  # pragma: no cover
        log.warning("[abex_live] stocks unavailable: %s", exc)
        return None

    try:
        portfolio = db.get_portfolio(str(user_id)) or []
    except Exception as exc:
        log.warning("[abex_live] portfolio unreadable: %s", exc)
        return None

    rows = []
    for holding in portfolio:
        market_id = holding.get("market_id") or ""
        shares = float(holding.get("shares") or 0)
        if shares <= 0:
            continue
        listing = {}
        try:
            listing = db.get_market_shares(market_id) or {}
        except Exception:
            pass
        price = float(listing.get("share_price") or 0)
        cost = float(holding.get("cost_basis") or 0)
        value = shares * price
        profit = value - cost
        try:
            grade, _w, _b, _t = core._backing_rating(market_id)
        except Exception:
            grade = "not rated"
        if not listing.get("active"):
            grade = "not rated"
        try:
            ticker = core._market_ticker(market_id)
        except Exception:
            ticker = market_id[:4].upper()
        name = ((db.get_markets() or {}).get(market_id) or {}).get("name") or market_id
        dividend = listing.get("dividend_pct")
        rows.append((market_id, (
            ticker, name, str(grade),
            f"{shares:,.0f}",
            # Average cost, not the total paid: the total is already implied by
            # shares x average, and the column a holder compares against price is
            # the per-share one.
            f"{(cost / shares if shares else 0):,.2f}c",
            f"{price:,.2f}c",
            f"{value:,.0f}c",
            f"{profit:+,.0f}c",
            profit >= 0,
            (f"{float(dividend):,.2f}%" if dividend else "none declared"),
            _month_name(listing.get("last_priced_month")),
        )))

    # Biggest position first, and the price derivation shown is that market's —
    # the one the reader has the most money in.
    rows.sort(key=lambda pair: -float(pair[1][6].rstrip("c").replace(",", "") or 0))
    formula, market_name = ([], "")
    if rows:
        formula, market_name = price_formula(rows[0][0])
    return {"rows": [row for _mid, row in rows],
            "formula": formula, "market": market_name}


def price_formula(market_id: str) -> tuple[list, str]:
    """How this market's share price is derived, from `_fundamental_for_market`.

    The design lists a trailing three-report mean as its own row. That mean is
    computed inside the pricing function and not returned, and recomputing it here
    would be a second implementation of the number the bot quotes — so the rows
    show what the pricing function actually hands back.
    """
    try:
        core, db = _core(), _db()
    except Exception:
        return [], ""
    try:
        listing = db.get_market_shares(market_id) or {}
        name = ((db.get_markets() or {}).get(market_id) or {}).get("name") or market_id
        fundamental = core._fundamental_for_market(market_id)
    except Exception as exc:
        log.warning("[abex_live] price formula for %s unreadable: %s", market_id, exc)
        return [], ""
    if not fundamental:
        return [], name
    price, pe, month = fundamental
    shares_out = float(listing.get("shares_outstanding") or 0)
    current = float(listing.get("share_price") or 0)
    text, dim, accent = "var(--text)", "var(--dim)", "var(--accent)"
    return ([
        ("Growth P/E multiple", f"{float(pe):,.2f}×", text),
        ("Shares outstanding", f"{shares_out:,.0f}", text),
        ("Priced from reports up to", _month_name(month), dim),
        ("Fundamental, from trailing net", f"{float(price):,.2f}c a share", text),
        ("Trading price now", f"{current:,.2f}c a share", accent),
    ], name)


def _holders(db, market_id: str) -> list:
    try:
        return [h for h in (db.get_holders(market_id) or [])
                if float(h.get("shares") or 0) > 0]
    except Exception:
        return []


def exchange() -> Optional[dict]:
    """The share side: every listed market, and the band above it.

    `{"rows": [...], "tiles": [...]}`, or None when the modules are absent.

    Free float here means shares in someone else's hands — the register minus the
    owner's own holding. Counting the owner would have GreyHames reading 93% free
    float while one account holds 92,863 of its 100,000 shares.
    """
    try:
        core, db = _core(), _db()
    except Exception as exc:  # pragma: no cover
        log.warning("[abex_live] exchange unavailable: %s", exc)
        return None
    try:
        listings = db.get_public_markets() or {}
        registry = db.get_markets() or {}
    except Exception as exc:
        log.warning("[abex_live] listings unreadable: %s", exc)
        return None

    rows, total_shares, everyone = [], 0.0, set()
    for market_id, listing in listings.items():
        market = registry.get(market_id) or {}
        shares_out = float(listing.get("shares_outstanding") or 0)
        price = float(listing.get("share_price") or 0)
        holders = _holders(db, market_id)
        everyone.update(str(h.get("user_id")) for h in holders)
        owner_id = str(market.get("owner_id") or "")
        outside = sum(float(h.get("shares") or 0) for h in holders
                      if str(h.get("user_id")) != owner_id)
        try:
            grade, _scale, _b, _t = core._backing_rating(market_id)
        except Exception:
            grade = "not rated"
        total_shares += shares_out
        rows.append((
            _ticker_of(core, market_id),
            market.get("name") or market_id,
            str(grade),
            f"{shares_out:,.0f}",
            f"{len(holders):,}",
            f"{price:,.2f}c",
            f"{(100.0 * outside / shares_out if shares_out else 0):,.1f}%",
        ))
    rows.sort(key=lambda r: -float(r[3].replace(",", "") or 0))

    index_value, index_note = _index_now(db)
    tiles = [
        ("Markets listed", f"{len(rows)}",
         f"of {sum(1 for m in registry.values() if m.get('active', 1))} active", "var(--text)"),
        ("Shares outstanding", f"{total_shares:,.0f}", "across listed markets", "var(--text)"),
        ("Holders", f"{len(everyone):,}", "accounts holding at least one share", "var(--text)"),
        ("Index", index_value, index_note, "var(--text)"),
    ]
    return {"rows": rows, "tiles": tiles}


def _index_now(db) -> tuple[str, str]:
    """The Abexilas index, from the log the bot writes — not recomputed here."""
    try:
        rows = db._get_conn().execute(
            "SELECT index_value, ts FROM market_index_log ORDER BY id DESC LIMIT 2"
        ).fetchall()
    except Exception:
        return "—", "index log unreadable"
    if not rows:
        return "—", "not computed yet"
    value = float(rows[0][0] or 0)
    if len(rows) > 1 and rows[1][0]:
        prev = float(rows[1][0])
        if prev:
            move = 100.0 * (value - prev) / prev
            if abs(move) >= 0.005:
                return f"{value:,.2f}", f"{move:+,.2f}% since the last reading"
    return f"{value:,.2f}", "unchanged since the last reading"


def filings(limit: int = 40) -> Optional[list[tuple]]:
    """Every filing on record, newest first, in `abex_data.FILINGS` shape.

    (ticker, name, month, net, per share, dividend, grade, missed)

    `missed` is always False: a missed filing can only be spotted against a
    schedule, and nothing in this system stores one. Rendering a guess in the loss
    colour would accuse an owner of missing a deadline that does not exist.
    """
    try:
        core, db = _core(), _db()
    except Exception as exc:  # pragma: no cover
        log.warning("[abex_live] filings unavailable: %s", exc)
        return None
    try:
        registry = db.get_markets() or {}
        listings = db.get_public_markets() or {}
        history = db._get_conn().execute(
            "SELECT market_id, month, net FROM csn_history "
            "ORDER BY month DESC, market_id LIMIT ?", (int(limit),)).fetchall()
    except Exception as exc:
        log.warning("[abex_live] csn history unreadable: %s", exc)
        return None

    paid = {}
    try:
        for row in db._get_conn().execute(
                "SELECT market_id, month, per_share FROM stock_dividend_log"):
            paid[(row[0], row[1])] = row[2]
    except Exception:
        pass

    out = []
    for market_id, month, net in history:
        market = registry.get(market_id) or {}
        listing = listings.get(market_id) or {}
        shares_out = float(listing.get("shares_outstanding") or 0)
        net = float(net or 0)
        try:
            grade, _scale, _b, _t = core._backing_rating(market_id)
        except Exception:
            grade = "not rated"
        if not listing:
            grade = "not rated"
        per_share = f"{net / shares_out:,.2f}c" if shares_out else "not listed"
        dividend = paid.get((market_id, month))
        out.append((
            _ticker_of(core, market_id),
            market.get("name") or market_id,
            _month_name(month),
            f"{net:,.0f}c",
            per_share,
            (f"{float(dividend):,.2f}c a share" if dividend else "none paid"),
            str(grade),
            False,
        ))
    return out


def orders() -> Optional[list[tuple]]:
    """Open production orders, in `abex_data.ORDERS` shape.

    (item, market, owner, qty, detail, unit pay, per what, total, points,
     priority?, window)

    Quantities and pay come from `fmt_qty`, `_coin_rates_for_order` and
    `_coins_for_pieces` — the same three the order card in Discord uses. A screen
    that computed "8 stacks" or a per-piece rate itself would eventually disagree
    with the card a worker claimed from, and the difference would be someone's pay.
    """
    try:
        core, db = _core(), _db()
    except Exception as exc:  # pragma: no cover
        log.warning("[abex_live] orders unavailable: %s", exc)
        return None
    try:
        # `load_orders` reads the production-order table the bot posts cards from.
        # `list_web_orders` looks right and is not: it reads `web_orders`, a
        # different table, and returned an empty list while one order was open.
        open_orders = [o for o in (db.load_orders() or [])
                       if str(o.get("status") or "").lower() == "open"]
    except Exception as exc:
        log.warning("[abex_live] orders unreadable: %s", exc)
        return None
    try:
        items_data = core._load_items()
    except Exception:
        items_data = {"items": {}}
    try:
        registry = db.get_markets() or {}
    except Exception:
        registry = {}

    import datetime as _dt

    rows = []
    for order in open_orders:
        requested = int(order.get("requested") or 0)
        market_id = order.get("market_id") or ""
        market = registry.get(market_id) or {}
        try:
            qty = core.fmt_qty(order, requested, prefer_original_amount=True)
        except Exception:
            qty = f"{requested:,} pieces"
        try:
            # The barrel rate the same call returns is not used here — see below.
            piece = core._coin_rates_for_order(order, items_data)[0]
            total = core._coins_for_pieces(order, requested, items_data)
        except Exception:
            piece, total = 0.0, 0

        # `_coin_rates_for_order`'s second rate is per BARREL, and a barrel here is
        # 3,456 pieces. Printing it as "per stack" put a 345,600c figure under a
        # label a worker reads as 64 pieces. The site quotes per piece and per
        # stack of 64, which is the pair every price in this economy is stated in.
        stackable = bool(order.get("stackable"))
        stack_size = int(order.get("stack_size") or 64)
        unit = f"{piece * stack_size:,.2f}c" if stackable else f"{piece:,.2f}c"
        per = (f"per stack of {stack_size} · {piece:,.2f}c a piece"
               if stackable else "per piece")

        # The employee window, from the order's own `priority_until`. No window and
        # no guessed one: an order past its head start is open to all, and says so.
        window, priority = "Open to all", False
        raw_until = order.get("priority_until")
        if raw_until:
            try:
                until = _dt.datetime.fromisoformat(str(raw_until).replace("Z", "+00:00"))
                now = _dt.datetime.now(until.tzinfo) if until.tzinfo else _dt.datetime.now()
                left = (until - now).total_seconds()
                if left > 0:
                    priority = True
                    minutes = int(left // 60)
                    window = (f"{minutes} minutes left" if minutes >= 1
                              else f"{int(left)} seconds left")
            except Exception:
                pass

        rows.append((
            order.get("item") or "unnamed item",
            market.get("name") or order.get("shop") or market_id or "—",
            _owner_name(db, market.get("owner_id")),
            qty,
            f"{requested:,} pieces in total",
            unit, per,
            f"{total:,}c" if isinstance(total, int) else f"{total}c",
            "—",                       # loyalty points per order: not recorded yet
            priority, window,
        ))
    return rows


def parcels(kind: str = "land") -> Optional[list[tuple]]:
    """Listings of one kind, in `abex_data.PARCELS` shape.

    (name, owner, tenant, price, state, note)

    `land_listings` holds BOTH auction kinds and tells them apart by `kind`:
    'land' is a claim, 'item' is goods. They are different surfaces to a player —
    Claims is the land auction, Auctions is the item auction — so a caller asks
    for the one it means. A page that showed both put a stack of diamonds and a
    2,000-chunk claim in one table under one price column.

    The design's rows describe leases with rent. This economy sells outright —
    `land_listings` has a price, a bidder and a status, and no rent anywhere — so
    the columns carry what a listing actually has.
    """
    try:
        db = _db()
    except Exception:  # pragma: no cover
        return None
    try:
        rows = db._get_conn().execute(
            "SELECT title, land, chunks, seller_id, status, current_bid, buy_now, "
            "       sold_price, sold_to "
            "FROM land_listings WHERE kind = ? "
            "ORDER BY COALESCE(closed_at, created_at) DESC LIMIT 40", (str(kind),)
        ).fetchall()
    except Exception as exc:
        log.warning("[abex_live] land listings unreadable: %s", exc)
        return None

    out = []
    for title, land, chunks, seller_id, status, bid, buy_now, sold, sold_to in rows:
        price = sold or bid or buy_now or 0
        out.append((
            title or land or "untitled listing",
            _owner_name(db, seller_id),
            (_owner_name(db, sold_to) if sold_to else "—"),
            f"{float(price or 0):,.0f}c",
            str(status or "—").replace("_", " "),
            f"{int(chunks or 0):,} chunks" if chunks else "—",
        ))
    return out


def hub(user_id: str) -> Optional[dict]:
    """The front page: what is waiting, what you hold, what the index is doing.

    Returns the keyword arguments `abex_hub.body` takes, or None when the modules
    are absent.

    The design's four tiles are Index, Dividends, Holdings and Next report. Three
    of those are facts this system has. The fourth is not — nothing stores a report
    due date — so that tile carries the count of markets that have filed for the
    current month, which is the same question ("who still owes a report?") asked in
    a way the data can answer.
    """
    try:
        db = _db()
    except Exception:  # pragma: no cover
        return None

    market_rows = markets() or []
    order_rows = orders() or []
    index_value, index_note = _index_now(db)

    # Holdings: the reader's own, valued at the current price.
    holdings_value, positions = 0.0, 0
    live = stocks(user_id) or {"rows": []}
    for row in live["rows"]:
        positions += 1
        try:
            holdings_value += float(row[6].rstrip("c").replace(",", ""))
        except ValueError:
            pass

    # Filed this month, against the markets that have ever filed. A market that has
    # never filed anything is not "late", it is not participating.
    month = ""
    try:
        row = db._get_conn().execute("SELECT MAX(month) FROM csn_history").fetchone()
        month = row[0] if row and row[0] else ""
    except Exception:
        pass
    filed = ever = 0
    try:
        conn = db._get_conn()
        filed = conn.execute("SELECT COUNT(DISTINCT market_id) FROM csn_history "
                             "WHERE month=?", (month,)).fetchone()[0]
        ever = conn.execute("SELECT COUNT(DISTINCT market_id) FROM csn_history"
                            ).fetchone()[0]
    except Exception:
        pass

    gain, text = "var(--gain)", "var(--text)"
    tiles = [
        ("Index", index_value, index_note, text),
        ("Your holdings", f"{holdings_value:,.0f}c",
         f"{positions} position{'' if positions == 1 else 's'}",
         gain if holdings_value else text),
        ("Open orders", f"{len(order_rows)}",
         "claimable right now" if order_rows else "nothing to claim", text),
        ("Filed for " + (_month_name(month) if month else "this month"),
         f"{filed} of {ever}", "markets that file at all", text),
    ]

    hub_work = []
    for item, market, _owner, qty, _detail, unit, per, _total, _pts, prio, window in order_rows[:6]:
        hub_work.append((item, qty, f"{unit} {per}", market, window,
                         "var(--loss)" if prio else "var(--faint)"))

    return {
        "tiles": tiles,
        "markets": market_rows[:8],
        "work": hub_work,
        # No dividend has ever been paid: `stock_dividend_log` is empty. An estimate
        # here would be the only number on the page nobody could check.
        "dividends": ("none paid yet", "none declared"),
        "sub": f"{len(market_rows)} markets, each weighted by its credit grade.",
        "market_count": len(market_rows),
        "work_count": len(order_rows),
        "last_col": "Last report",
        "dividend_note": "No market has declared a dividend yet.",
    }


def investor(user_id: str) -> Optional[dict]:
    """The preferred pool: your stake, what the pool is, and where it came from.

    The formula is the bot's own, not a reading of the design: the pool is each
    qualifying market's monthly net times `_investor_pool_pct()` (a live config
    knob, default 10%), split by each investor's `share_pct`. Only markets
    `_is_vtech_market` accepts feed it — pointing the page at every market would
    have inflated the pool by everything the group does not own.
    """
    try:
        core, db = _core(), _db()
    except Exception:  # pragma: no cover
        return None
    try:
        investors = db.get_investors() or {}
        pool_pct = float(core._investor_pool_pct())
    except Exception as exc:
        log.warning("[abex_live] investor pool unreadable: %s", exc)
        return None

    mine = investors.get(str(user_id)) or {}
    try:
        row = db._get_conn().execute("SELECT MAX(month) FROM csn_history").fetchone()
        month = row[0] if row and row[0] else ""
    except Exception:
        month = ""

    registry = {}
    try:
        registry = db.get_markets() or {}
    except Exception:
        pass

    rows, pool = [], 0.0
    for market_id, market in registry.items():
        try:
            if not core._is_vtech_market(market_id):
                continue
        except Exception:
            continue
        months = {}
        try:
            months = (core._load_csn_for_market(market_id) or {}).get("months", {}) or {}
        except Exception:
            pass
        net = float((months.get(month) or {}).get("net", 0) or 0)
        if net <= 0:
            continue          # a loss contributes nothing; it does not claw back
        share = net * pool_pct / 100.0
        pool += share
        rows.append((_ticker_of(core, market_id), market.get("name") or market_id,
                     f"{net:,.0f}c", f"{share:,.0f}c"))
    rows.sort(key=lambda r: -float(r[3].rstrip("c").replace(",", "") or 0))

    pref = float(mine.get("pref_shares") or 0)
    share_pct = float(mine.get("share_pct") or 0)
    total_pref = sum(float(i.get("pref_shares") or 0) for i in investors.values())
    received = float(mine.get("total_received") or 0)

    gain, text, dim = "var(--gain)", "var(--text)", "var(--dim)"
    tiles = [
        ("Your stake", f"{pref:,.0f} of {total_pref:,.0f}",
         f"{share_pct:,.1f}% of the pool", text),
        (f"Pool, {_month_name(month) if month else 'this month'}", f"{pool:,.0f}c",
         f"{pool_pct:,.0f}% of each market's net", text),
        ("Your share", f"{pool * share_pct / 100.0:,.0f}c",
         (f"{received:,.0f}c paid to you so far" if received
          else "nothing paid out yet"), gain if pool else dim),
    ]
    return {"tiles": tiles, "rows": rows, "pool_pct": pool_pct,
            "is_investor": bool(mine)}


# ══════════════════════════════════════════════════════════════════════════
# The owner's side: My market, and the report it files
# ══════════════════════════════════════════════════════════════════════════

def owned_markets(user_id: str) -> list:
    """Markets this account owns, biggest current-month net first.

    Ownership is `markets.owner_id`. `leader_discord_id` is deliberately NOT
    treated as ownership: a leader runs a market's Discord side, and the payout
    waterfall on these screens decides where somebody else's money goes.
    """
    try:
        db = _db()
    except Exception as exc:                        # pragma: no cover
        log.warning("[abex_live] owned markets unavailable: %s", exc)
        return []
    uid = str(user_id or "")
    if not uid:
        return []
    try:
        registry = db.get_markets() or {}
    except Exception as exc:
        log.warning("[abex_live] market registry unreadable: %s", exc)
        return []
    mine = [(mid, m) for mid, m in registry.items()
            if str((m or {}).get("owner_id") or "") == uid]
    month = _now_month()

    def _net(pair):
        return -_month_totals(db, pair[0], month)[2]

    mine.sort(key=_net)
    return [{"market_id": mid, "name": (m or {}).get("name") or mid} for mid, m in mine]


def _now_month() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _day_name(day: str) -> str:
    """`2026-08-07` -> `Fri 7 Aug`. The design writes days, not keys."""
    from datetime import datetime
    try:
        return datetime.strptime(str(day)[:10], "%Y-%m-%d").strftime("%a %-d %b")
    except ValueError:
        try:
            return datetime.strptime(str(day)[:10], "%Y-%m-%d").strftime("%a %d %b")
        except Exception:
            return str(day)
    except Exception:
        return str(day)


def _prev_month(month: str) -> str:
    y, m = (int(x) for x in str(month).split("-")[:2])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _month_totals(db, market_id: str, month: str) -> tuple:
    """(income, spent, net) for one market-month, or zeroes.

    `csn_month_totals` returns income and spent and NOT net — net is derived, and
    deriving it here rather than reading a key that isn't there is the difference
    between this screen showing the month's real result and showing zero. It read
    a missing `net` key for its first draft and every market looked break-even.
    """
    try:
        t = db.csn_month_totals(market_id, month) or {}
    except Exception:
        t = {}
    if int(t.get("sources") or 0):
        income = float(t.get("income") or 0)
        spent = float(t.get("spent") or 0)
        return (income, spent, income - spent)
    # No live source for that month. For a CLOSED month that is the normal case
    # and the filed record is the answer — `csn_month_sources` holds what is
    # still being assembled, `csn_history` holds what was filed. Reading only the
    # first makes every month before this one look like it earned nothing.
    try:
        row = db._get_conn().execute(
            "SELECT income, spent, net FROM csn_history WHERE market_id=? AND month=?",
            (str(market_id), str(month))).fetchone()
    except Exception:
        row = None
    if not row:
        return (0.0, 0.0, 0.0)
    return (float(row[0] or 0), float(row[1] or 0), float(row[2] or 0))


def my_market(user_id: str, market_id: str = "") -> Optional[dict]:
    """The owner's console for one market he owns.

    Returns None when the modules are unreachable, and `{"owns": []}` when this
    account owns no market — which is not an error and must not be rendered as
    one. Most players own nothing; the page says so in a sentence.

    THE WATERFALL IS READ, NOT RECOMPUTED. Spec §6.3 fixes the order net → vault
    retention → debt service and coupons → dividends → owner's residual, and the
    retention half of it is already a live obligation: `_accrue_vault_retention`
    posts 10% of every positive closed month to `vault_due:<mid>`. This reads that
    accrued figure. Recomputing 10% here would produce a number that looks like
    the obligation and disagrees with it the moment a month closes or the rate
    moves, and the owner would have two answers to "what do I owe the vault".
    """
    try:
        db = _db()
    except Exception as exc:                        # pragma: no cover
        log.warning("[abex_live] my market unavailable: %s", exc)
        return None
    # Core is OPTIONAL here, and only optional here. It answers the grade and the
    # retention rate; it does not answer the money. Without it this screen still
    # shows the owner his own ledger, which is the part he came for, and says the
    # market is not rated rather than going dark over a rating.
    try:
        core = _core()
    except Exception as exc:
        log.warning("[abex_live] grade unavailable, money still is: %s", exc)
        core = None
    owned = owned_markets(user_id)
    if not owned:
        return {"owns": []}
    chosen = market_id or owned[0]["market_id"]
    if chosen not in {m["market_id"] for m in owned}:
        return {"owns": owned, "denied": chosen}

    name = next(m["name"] for m in owned if m["market_id"] == chosen)
    month = _now_month()
    income, spent, net = _month_totals(db, chosen, month)
    prev = _prev_month(month)
    _pi, _ps, prev_net = _month_totals(db, chosen, prev)

    try:
        grade, scale, _b, _t = core._backing_rating(chosen)
    except Exception:
        grade, scale = "not rated", 0.0
    try:
        listing = (db.get_public_markets() or {}).get(chosen) or {}
    except Exception:
        listing = {}

    vault_due = 0.0
    try:
        vault_due = float(db.get_config(f"vault_due:{chosen}") or 0)
    except Exception:
        pass
    retention_pct = float(getattr(core, "STOCK_RETAINED_EARNINGS_PCT", 10.0) or 10.0)

    # ── the month's ledger, newest first ────────────────────────────────────
    ledger = []
    try:
        rows = db._get_conn().execute(
            "SELECT sale_day, item, verb, qty, coins FROM csn_transactions "
            "WHERE market_id=? AND sale_day LIKE ? "
            "ORDER BY sale_ts DESC LIMIT 60", (chosen, month + "-%")).fetchall()
        for day, item, verb, qty, coins in rows:
            amount = abs(float(coins or 0))
            sold_to_us = str(verb) == "sold"      # the shop bought stock in
            ledger.append((
                _day_name(day), f"{item} ×{int(qty or 0)}",
                "Restock" if sold_to_us else "Sales",
                "" if sold_to_us else f"{amount:,.0f}c",
                f"{amount:,.0f}c" if sold_to_us else "",
            ))
    except Exception as exc:
        log.warning("[abex_live] ledger for %s unreadable: %s", chosen, exc)

    # ── staff ───────────────────────────────────────────────────────────────
    staff = []
    try:
        team = db.get_team(str(user_id)) or []
        perf = {}
        for row in db._get_conn().execute(
                "SELECT worker_id, kind, SUM(coins), SUM(qty), COUNT(*) "
                "FROM team_perf_log WHERE manager_id=? AND created_at >= ? "
                "GROUP BY worker_id, kind", (str(user_id), month + "-01")):
            wid, kind, coins, qty, n = row
            slot = perf.setdefault(str(wid), {"coins": 0.0, "orders": 0})
            slot["coins"] += float(coins or 0)
            if str(kind) == "order":
                slot["orders"] += int(n or 0)
        for member in team:
            wid = str(member.get("worker_id") if isinstance(member, dict) else member)
            slot = perf.get(wid, {"coins": 0.0, "orders": 0})
            staff.append((_owner_name(db, wid), "Worker", str(slot["orders"]),
                          f"{slot['coins']:,.0f}c"))
    except Exception as exc:
        log.warning("[abex_live] staff for %s unreadable: %s", user_id, exc)

    return {
        "owns": owned, "market_id": chosen, "name": name,
        "month": month, "month_name": _month_name(month),
        "income": income, "spent": spent, "net": net,
        "prev_net": prev_net, "prev_month_name": _month_name(prev),
        "grade": str(grade), "backing": float(scale or 0),
        "share_price": float(listing.get("share_price") or 0) if listing else None,
        "shares_out": float(listing.get("shares_outstanding") or 0) if listing else None,
        "treasury": float(listing.get("treasury_coins") or 0) if listing else 0.0,
        "vault_due": vault_due, "retention_pct": retention_pct,
        "ledger": ledger, "staff": staff,
        "filed": bool(_month_totals(db, chosen, month)[0] or net),
    }


def filing(user_id: str, market_id: str = "") -> Optional[dict]:
    """The report this owner would file for the month, and what filing changes.

    The share-price rows come from `price_formula`, which asks the bot's own
    pricing function. This module does not price a share: `/stock price` and this
    page have to agree, and two implementations of one formula do not stay equal.
    """
    data = my_market(user_id, market_id)
    if data is None or not data.get("owns") or "market_id" not in data:
        return data
    try:
        db = _db()
    except Exception:                               # pragma: no cover
        return data
    mid = data["market_id"]

    rows, _name = price_formula(mid)
    data["price_rows"] = rows

    history = []
    try:
        for month, income, spent, net in db._get_conn().execute(
                "SELECT month, income, spent, net FROM csn_history "
                "WHERE market_id=? ORDER BY month DESC LIMIT 4", (mid,)):
            history.append((_month_name(month), f"{float(income or 0):,.0f}c",
                            f"{float(spent or 0):,.0f}c", f"{float(net or 0):,.0f}c"))
    except Exception as exc:
        log.warning("[abex_live] filing history for %s unreadable: %s", mid, exc)

    dividend = None
    try:
        row = db._get_conn().execute(
            "SELECT month, per_share FROM stock_dividend_log WHERE market_id=? "
            "ORDER BY month DESC LIMIT 1", (mid,)).fetchone()
        if row:
            dividend = (_month_name(row[0]), float(row[1] or 0))
    except Exception:
        pass
    filed_this_month = None
    try:
        row = db._get_conn().execute(
            "SELECT net FROM csn_history WHERE market_id=? AND month=?",
            (mid, data["month"])).fetchone()
        if row is not None:
            filed_this_month = float(row[0] or 0)
    except Exception:
        pass
    data["history"] = history
    data["last_dividend"] = dividend
    data["filed_net"] = filed_this_month
    return data


# ══════════════════════════════════════════════════════════════════════════
# Price history — the shape of a number over time
# ══════════════════════════════════════════════════════════════════════════

def _thin(rows: list, target: int = 120) -> list:
    """Evenly sample a long series down to `target` points, keeping both ends.

    The index is logged every five minutes: a month is ~8,600 readings and the
    chart is a few hundred pixels wide. Sampling is honest here in a way that
    averaging would not be — every point drawn is a reading that happened, at the
    time it happened. An average would draw a price nobody ever saw.

    Both ends are kept because the first and last readings are the two the
    caption quotes; dropping either would make the change figure disagree with
    the line above it.
    """
    if len(rows) <= target:
        return rows
    step = (len(rows) - 1) / float(target - 1)
    out = [rows[int(round(i * step))] for i in range(target)]
    out[-1] = rows[-1]
    return out


#: What a price-log `reason` means to a reader. The distinction this whole chart
#: exists to make: a TRADE is somebody buying or selling; everything else is the
#: model repricing the share. On a real exchange every print is a trade and the
#: question never comes up. Here three of GreyHames' 82 points are trades, so a
#: line that does not say which is a line that implies eighty trades.
_MOVE = {
    "trade:buy":  ("buy", "a buy"),
    "trade:sell": ("sell", "a sell"),
    "csn_report": ("model", "a filed report"),
    "reversion":  ("model", "drift back toward fundamental"),
    "params_changed": ("model", "a parameter change"),
    "ipo_model":  ("model", "the listing price"),
    "vtech_gex_merger": ("model", "the GEX merger"),
}


def _move(reason) -> tuple:
    """`(kind, human)` for a price-log reason. Unknown reasons are `model` and
    are shown under their own stored word rather than guessed at."""
    raw = str(reason or "").strip()
    if raw in _MOVE:
        return _MOVE[raw]
    if raw.startswith("trade:"):
        side = raw.split(":", 1)[1]
        return ("buy" if side == "buy" else "sell", f"a {side}")
    return ("model", raw or "repriced")


def price_series(market_id: str, days: int = 30) -> Optional[dict]:
    """One market's share price over `days`, oldest first, WITH what moved it.

    Every point carries its timestamp and why the price changed, because on this
    exchange most of them are not trades. Returns None when the log is
    unreadable — distinct from an empty series, which means the market has never
    been priced and is a fact worth showing.
    """
    try:
        db = _db()
    except Exception:                               # pragma: no cover
        return None
    try:
        rows = db._get_conn().execute(
            "SELECT logged_at, price, reason FROM stock_price_log "
            "WHERE market_id = ? AND logged_at >= datetime('now', ?) "
            "ORDER BY id ASC", (str(market_id), f"-{int(days)} days")).fetchall()
    except Exception as exc:
        log.warning("[abex_live] price log for %s unreadable: %s", market_id, exc)
        return None
    rows = _thin([(r[0], float(r[1] or 0), r[2]) for r in rows])
    marks, labels, whens = [], [], []
    for i, (at, _p, reason) in enumerate(rows):
        kind, human = _move(reason)
        labels.append(human)
        whens.append(str(at or "")[:16])
        if kind in ("buy", "sell"):
            marks.append({"i": i, "kind": kind})
    return {
        "points": [p for _t, p, _r in rows],
        "at": whens,
        "why": labels,
        "marks": marks,
        "trades": len(marks),
        "days": int(days),
        "from": (rows[0][0] or "")[:10] if rows else "",
        "to": (rows[-1][0] or "")[:10] if rows else "",
        "window": f"{days} days",
    }


def index_series(days: int = 30) -> Optional[dict]:
    """The market index over `days`, oldest first.

    `market_index_log` is written every five minutes whether or not anything
    moved, so a flat stretch here is a real flat stretch — nothing has traded —
    rather than a gap in the record.
    """
    try:
        db = _db()
    except Exception:                               # pragma: no cover
        return None
    try:
        rows = db._get_conn().execute(
            "SELECT ts, index_value FROM market_index_log "
            "WHERE ts >= datetime('now', ?) ORDER BY id ASC",
            (f"-{int(days)} days",)).fetchall()
    except Exception as exc:
        log.warning("[abex_live] index log unreadable: %s", exc)
        return None
    rows = _thin([(r[0], float(r[1] or 0)) for r in rows])
    return {
        "points": [p for _t, p in rows],
        "at": [str(t or "")[:16] for t, _p in rows],
        "why": ["" for _r in rows],
        "marks": [],
        "trades": 0,
        "days": int(days),
        "from": (rows[0][0] or "")[:10] if rows else "",
        "to": (rows[-1][0] or "")[:10] if rows else "",
        "window": f"{days} days",
    }


def stock_detail(market_id: str, user_id: str = "") -> Optional[dict]:
    """Everything one listed market discloses: price, grade, P/E, register, months.

    Spec §6.7 is the rule this obeys: "a listed market discloses ledger, staff
    and liabilities to everyone; a private market discloses nothing but its
    grade." So a listing is required — an unlisted market returns `{"listed":
    False}` and the page says only what it is allowed to say. That is not
    politeness; it is the disclosure bargain a market accepts when it lists.

    The register is disclosed as SHAPE, not as names. How many accounts hold it
    and how much of it is in someone else's hands are facts about the security.
    Who holds 92,863 shares is a fact about a person, and no rule here asks him
    to publish it.
    """
    try:
        db = _db()
    except Exception:                               # pragma: no cover
        return None
    mid = str(market_id or "")
    try:
        market = (db.get_markets() or {}).get(mid)
    except Exception as exc:
        log.warning("[abex_live] market %s unreadable: %s", mid, exc)
        return None
    if not market:
        return None
    name = market.get("name") or mid

    try:
        listing = (db.get_public_markets() or {}).get(mid) or {}
    except Exception:
        listing = {}

    try:
        core = _core()
    except Exception:
        core = None
    grade, scale = "not rated", 0.0
    if core is not None:
        try:
            grade, scale, _b, _t = core._backing_rating(mid)
        except Exception:
            pass

    # ── the months, newest first, each against the one before ───────────────
    months = []
    try:
        rows = db._get_conn().execute(
            "SELECT month, income, spent, net FROM csn_history "
            "WHERE market_id = ? ORDER BY month DESC LIMIT 24", (mid,)).fetchall()
        ordered = list(reversed([(r[0], float(r[1] or 0), float(r[2] or 0),
                                  float(r[3] or 0)) for r in rows]))
        for i, (month, income, spent, net) in enumerate(ordered):
            prev = ordered[i - 1][3] if i else None
            change = (net - prev) if prev is not None else None
            pct = (change / abs(prev) * 100.0) if (prev not in (None, 0)) else None
            months.append({"month": month, "name": _month_name(month),
                           "income": income, "spent": spent, "net": net,
                           "change": change, "pct": pct})
        months.reverse()
    except Exception as exc:
        log.warning("[abex_live] months for %s unreadable: %s", mid, exc)

    # ── the register, as shape ──────────────────────────────────────────────
    holders, held_by_owner, your_shares = 0, 0.0, 0.0
    owner_id = str(market.get("owner_id") or "")
    try:
        for h in (db.get_holders(mid) or []):
            shares = float(h.get("shares") or 0)
            if shares <= 0:
                continue
            holders += 1
            if str(h.get("user_id") or "") == owner_id:
                held_by_owner += shares
            if user_id and str(h.get("user_id") or "") == str(user_id):
                your_shares = shares
    except Exception:
        pass

    shares_out = float(listing.get("shares_outstanding") or 0)
    return {
        "market_id": mid, "name": name, "listed": bool(listing),
        "grade": str(grade), "backing": float(scale or 0),
        "price": float(listing.get("share_price") or 0),
        "shares_out": shares_out,
        "pe": float(listing.get("pe_multiplier") or 0),
        "treasury": float(listing.get("treasury_coins") or 0),
        "last_priced_month": listing.get("last_priced_month"),
        "holders": holders,
        "free_float": max(0.0, shares_out - held_by_owner),
        "owner_holds": held_by_owner,
        "your_shares": your_shares,
        "months": months,
        "price_rows": (price_formula(mid)[0] if listing else []),
        "series": price_series(mid, 90),
        "nets": net_series(mid, 36),
    }


def market_items(market_id: str, months: int = 3, limit: int = 30) -> Optional[dict]:
    """What moves through one market, item by item, month by month.

    `csn_history_items` is the per-item half of a CSN filing: for each month it
    holds how many of an item the shop SOLD to players and how many it BOUGHT
    from them. Those two are opposite directions of trade and the table keeps
    them apart, so this does too — an item with 4,465 sold and 3,727 bought is a
    shop turning stock over, and one figure for "movement" would hide that.

    Direction, stated once so no caller has to guess: `sold_qty` is out of the
    shop and is income; `bought_qty` is into the shop and is what it paid for.
    `net_coins` is signed the same way — negative means the shop spent more on
    that item than it took.

    Items are ranked by TOTAL pieces moved across the window, not by coins, so a
    cheap high-volume line is not buried under one expensive sale.
    """
    try:
        db = _db()
    except Exception:                               # pragma: no cover
        return None
    mid = str(market_id or "")
    try:
        keys = [r[0] for r in db._get_conn().execute(
            "SELECT DISTINCT month FROM csn_history_items WHERE market_id = ? "
            "ORDER BY month DESC LIMIT ?", (mid, int(months)))]
    except Exception as exc:
        log.warning("[abex_live] item months for %s unreadable: %s", mid, exc)
        return None
    if not keys:
        return {"months": [], "rows": [], "total_items": 0}
    keys.reverse()                                   # oldest first, left to right

    marks = ",".join("?" for _ in keys)
    try:
        rows = db._get_conn().execute(
            f"SELECT item, month, sold_qty, bought_qty, net_coins "
            f"FROM csn_history_items WHERE market_id = ? AND month IN ({marks})",
            (mid, *keys)).fetchall()
    except Exception as exc:
        log.warning("[abex_live] items for %s unreadable: %s", mid, exc)
        return None

    by_item: dict = {}
    for item, month, sold, bought, net in rows:
        slot = by_item.setdefault(str(item), {"months": {}, "moved": 0, "net": 0.0})
        slot["months"][str(month)] = (int(sold or 0), int(bought or 0),
                                      float(net or 0))
        slot["moved"] += int(sold or 0) + int(bought or 0)
        slot["net"] += float(net or 0)

    ranked = sorted(by_item.items(), key=lambda kv: -kv[1]["moved"])
    out = []
    for item, slot in ranked[:limit]:
        cells = []
        for key in keys:
            sold, bought, _n = slot["months"].get(key, (0, 0, 0.0))
            cells.append((sold, bought))
        out.append({"item": item, "cells": cells, "moved": slot["moved"],
                    "net": slot["net"]})
    return {"months": [(k, _month_name(k)) for k in keys], "rows": out,
            "total_items": len(by_item)}


def filing_status() -> Optional[list[dict]]:
    """Which markets are behind on their filing, and by how much.

    THE DESIGN ASKS A QUESTION THIS DATA CANNOT ANSWER. Its Markets screen leads
    with "Filing next" — a queue of due dates — and nothing in this system stores
    a per-market due date, because reports arrive when an owner files them. A
    date computed from nothing looks exactly like a date that means something.

    So the block asks the question the record CAN answer, which turns out to be
    the more useful one anyway: who has stopped filing. Months behind and days
    since the last record are both facts, and both come straight from
    `csn_history`. An owner who is current does not appear at all.

    `months_behind` counts calendar months from the last filed month to the
    current one, so a market that filed August is 0 and one whose last month is
    July is 1 — it owes August. `days_since` is against the record's timestamp,
    which is when the filing actually landed, not the month it covered.
    """
    try:
        db = _db()
    except Exception:                               # pragma: no cover
        return None
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    this_month = now.strftime("%Y-%m")
    try:
        registry = db.get_markets() or {}
        rows = db._get_conn().execute(
            "SELECT market_id, MAX(month) AS m, MAX(recorded_at) AS t "
            "FROM csn_history WHERE market_id <> 'main' GROUP BY market_id").fetchall()
    except Exception as exc:
        log.warning("[abex_live] filing status unreadable: %s", exc)
        return None

    def _behind(month: str) -> int:
        try:
            y, m = (int(x) for x in str(month).split("-")[:2])
        except (ValueError, TypeError):
            return 0
        return max(0, (now.year - y) * 12 + (now.month - m))

    out = []
    for market_id, month, seen in rows:
        market = registry.get(market_id) or {}
        if not market or not market.get("active", 1):
            continue
        days = None
        if seen:
            try:
                at = datetime.fromisoformat(str(seen).replace("Z", "+00:00"))
                if at.tzinfo is None:
                    at = at.replace(tzinfo=timezone.utc)
                days = int((now - at).total_seconds() // 86400)
            except ValueError:
                days = None
        out.append({
            "market_id": market_id,
            "name": market.get("name") or market_id,
            "last_month": str(month or ""),
            "last_month_name": _month_name(month),
            "months_behind": _behind(month),
            "days_since": days,
            "current": str(month or "") == this_month,
        })
    out.sort(key=lambda r: (-r["months_behind"], -(r["days_since"] or 0)))
    return out


#: The grade ladder, in one place. Mirrors `Restocker_main._backing_rating`; a
#: page that computed its own would eventually disagree with the engine about
#: what a market is.
_RANK = {"C": 0, "BB": 1, "BBB": 2, "A": 3, "AA": 4, "AAA": 5}


def _band_for(ratio: float) -> str:
    return ("AAA" if ratio >= 1.5 else "AA" if ratio >= 1.0 else "A" if ratio >= 0.75
            else "BBB" if ratio >= 0.5 else "BB" if ratio >= 0.25 else "C")


#: What each pillar weighs in the composite, and what full marks means. Mirrors
#: `Restocker_main.QUALITY_W_*` / `QUALITY_*_TARGET`; read from core when it is
#: importable so the page cannot drift from the engine.
_PILLARS = (
    ("backing", "Backing", "collateral against the 25% target"),
    ("traffic", "Traffic", "teleport-fee visitors a month on bound lands"),
    ("orders",  "Order flow", "fulfilled order value over 30 days"),
    ("history", "Report history", "closed earnings months on record"),
)


def grade_detail(market_id: str) -> Optional[dict]:
    """Why a market has the grade it has: the pillars, and the cap that binds.

    Two markets reading BBB with 0.79x and 1.03x backing is not obviously a
    rating at work — it looks like a rating that is not working. It was both:
    half the composite was scoring zero for want of a data feed, and the backing
    cap was binding underneath. Neither was visible anywhere, so the only way to
    tell them apart was to read the engine.

    The cached `quality:<mid>` blob has every pillar in it already. This reads
    that and says which pillars were MEASURED — an absent feed is unmeasured and
    out of the average, and saying so is the difference between "scored zero" and
    "not scored".
    """
    try:
        db = _db()
    except Exception:                               # pragma: no cover
        return None
    mid = str(market_id or "")
    try:
        import json
        raw = db.get_config(f"quality:{mid}")
        q = json.loads(raw) if raw else None
    except Exception as exc:
        log.warning("[abex_live] quality for %s unreadable: %s", mid, exc)
        q = None
    if not q:
        return None

    try:
        core = _core()
        weights = {"backing": float(core.QUALITY_W_BACKING),
                   "traffic": float(core.QUALITY_W_TRAFFIC),
                   "orders": float(core.QUALITY_W_ORDERS),
                   "history": float(core.QUALITY_W_HISTORY)}
    except Exception:
        weights = {"backing": 0.35, "traffic": 0.25, "orders": 0.25, "history": 0.15}

    measured = set(q.get("pillars_measured") or [])
    if not measured:
        # A blob cached before the engine recorded measurability. Derive it the
        # same way rather than assuming everything counted, which would show a
        # zero for a feed that was never read.
        measured = {"backing", "history"}
        if q.get("traffic_measured") or float(q.get("visitors_month") or 0):
            measured.add("traffic")
        if int(q.get("orders_total_30d") or 0):
            measured.add("orders")

    rows = []
    for key, label, note in _PILLARS:
        rows.append({
            "key": key, "label": label, "note": note,
            "weight": weights.get(key, 0.0),
            "score": float(q.get(f"{key}_score") or 0.0),
            "measured": key in measured,
        })
    backed = float(q.get("backed_pct") or 0)
    target = float(q.get("target_pct") or 0)
    backing_ratio = (backed / target) if target else 0.0
    score = float(q.get("score") or 0.0)

    # VAULT ARREARS ARE A THIRD CONSTRAINT AND THE PAGE NEVER MENTIONED THEM.
    # Amazonia scores AA on composite and is allowed A by its 1.03x backing, and
    # reads BBB — because it owes 140,542c of retained earnings to the vault and
    # `_backing_rating` clamps an arrears market at BBB. With that invisible, the
    # page contradicted itself: pillars that add up to A over a grade that says
    # BBB, and a note blaming a cap that was not the thing binding.
    due = bal = 0.0
    try:
        due = float(db.get_config(f"vault_due:{mid}") or 0)
        bal = float(db.get_config(f"vault_bal:{mid}") or 0)
    except Exception:
        pass
    arrears = max(0.0, due - bal)

    # Free float decides whether those arrears bind, exactly as the engine has
    # it: the retention protects outside shareholders and bondholders, and a
    # market whose whole register is the owner's has neither.
    outside = 0.0
    try:
        owner_id = str((db.get_markets() or {}).get(mid, {}).get("owner_id") or "")
        outside = sum(float(h.get("shares") or 0)
                      for h in (db.get_holders(mid) or [])
                      if str(h.get("user_id") or "") != owner_id)
    except Exception:
        outside = 1.0

    # WHAT THE BACKING IS MADE OF, and what is not counted. Asked for by name
    # after 25,000,000c of items showed up as nothing: Amazonia has 174 stocked
    # lines and every one is a LEGACY per-stack row, so `_market_asset_value`
    # skips them all and its inventory backs the shares by zero. The guard is
    # right — valuing a per-stack price per-unit reads 99,321,236c against a
    # 30,000,000c cap, which is the "383% backed" bug — but a market whose stock
    # is invisible to its own rating should be told, not left to wonder.
    parts, uncounted = [], 0
    try:
        core = _core()
        b = core._market_backing(mid)
        parts = [("Treasury", b.get("cash_pct", 0.0), b.get("cash", 0.0)),
                 ("Inventory", b.get("asset_pct", 0.0), b.get("assets", 0.0)),
                 ("For sale", b.get("sellable_pct", 0.0), b.get("sellable", 0.0)),
                 ("Exchange fund", b.get("fund_pct", 0.0), b.get("fund_share", 0.0)),
                 ("Vault", b.get("vault_pct", 0.0), b.get("vault_bal", 0.0)),
                 ("Pledged, after haircut", b.get("pledge_pct", 0.0),
                  b.get("pledged", 0.0))]
    except Exception as exc:
        log.warning("[abex_live] backing parts for %s unreadable: %s", mid, exc)
    try:
        for _item, x in (db.get_market_stock(mid) or {}).items():
            if float(x.get("stock") or 0) > 0 and x.get("sell_qty") is None \
                    and x.get("buy_qty") is None:
                uncounted += 1
    except Exception:
        uncounted = 0

    band = _band_for(score / 0.60 if score else 0.0)
    cap = "AAA" if backing_ratio >= 1.6 else "AA" if backing_ratio >= 1.2 else "A"
    return {"rows": rows, "score": score, "ratio": score / 0.60 if score else 0.0,
            "backed_pct": backed, "target_pct": target,
            "backing_ratio": backing_ratio,
            "band": band, "cap": cap,
            "backing_parts": parts, "uncounted_lines": uncounted,
            "vault_due": due, "vault_bal": bal, "vault_arrears": arrears,
            "free_float": outside,
            "vault_binds": bool(arrears > 1 and outside > 0
                                and _RANK.get(band, 0) > 2
                                and _RANK.get(cap, 0) > 2),
            "history_months": int(q.get("history_months") or 0),
            "order_value_30d": float(q.get("order_value_30d") or 0),
            "visitors_month": float(q.get("visitors_month") or 0)}


def net_series(market_id: str, months: int = 36) -> Optional[dict]:
    """Filed net, month by month, oldest first.

    THE PRICE LOG IS NOT THE HISTORY. `stock_price_log` for GreyHames starts on
    16 July 2026 — three weeks — because that is when the exchange started
    logging prices. Its EARNINGS go back to April 2024: twenty-nine filed months.
    A page that draws only the price line says a market with two years of
    accounts has no history.

    So this is the other line: what the market actually earned, per filed month.
    Not a price and not live — a month closes once.
    """
    try:
        db = _db()
    except Exception:                               # pragma: no cover
        return None
    try:
        rows = db._get_conn().execute(
            "SELECT month, net FROM csn_history WHERE market_id = ? "
            "ORDER BY month DESC LIMIT ?", (str(market_id), int(months))).fetchall()
    except Exception as exc:
        log.warning("[abex_live] net history for %s unreadable: %s", market_id, exc)
        return None
    rows = list(reversed([(r[0], float(r[1] or 0)) for r in rows]))
    if not rows:
        return {"points": [], "at": [], "why": [], "marks": [], "trades": 0}
    return {
        "points": [n for _m, n in rows],
        "at": [_month_name(m) for m, _n in rows],
        "why": ["as filed" for _r in rows],
        "marks": [],
        "trades": 0,
        "months": len(rows),
        "from": rows[0][0],
        "to": rows[-1][0],
        "window": f"{len(rows)} filed months",
    }


def shelves(market_id: str, limit: int = 60) -> Optional[dict]:
    """What is on a market's shelves right now: stock, capacity and prices.

    `market_stock` is a live snapshot of the shop, and it has never been on this
    site. That is why 25,000,000c of Amazonia's stock reads as nothing in its
    backing with no way to see the reason from any page.

    THE PRICE UNIT IS THE POINT. `buy_price`/`sell_price` are stored PER UNIT and
    `buy_qty`/`sell_qty` are the shop's listed bulk quantity. A row with NO qty
    is a LEGACY per-bulk price stored raw — the number is per stack, not per
    piece, and nothing downstream trusts it: `_market_asset_value` skips those
    rows, so they back the shares by zero. This returns that flag per row rather
    than quietly rendering a figure that is 64x out.
    """
    try:
        db = _db()
    except Exception:                               # pragma: no cover
        return None
    try:
        stock = db.get_market_stock(str(market_id)) or {}
    except Exception as exc:
        log.warning("[abex_live] shelves for %s unreadable: %s", market_id, exc)
        return None

    rows, counted, uncounted, seen = [], 0.0, 0.0, ""
    for item, x in stock.items():
        have = float(x.get("stock") or 0)
        if have <= 0:
            continue
        per_unit = (x.get("sell_qty") is not None or x.get("buy_qty") is not None)
        sell = float(x.get("sell_price") or 0)
        buy = float(x.get("buy_price") or 0)
        worth = have * (sell or buy)
        if per_unit:
            counted += worth
        else:
            uncounted += worth
        at = str(x.get("updated_at") or "")
        if at > seen:
            seen = at
        rows.append({"item": str(item), "stock": have,
                     "capacity": float(x.get("capacity") or 0),
                     "sell": sell, "buy": buy, "per_unit": per_unit,
                     "worth": worth})
    rows.sort(key=lambda r: -r["worth"])
    return {"rows": rows[:limit], "lines": len(rows),
            "counted": counted, "uncounted": uncounted,
            "legacy_lines": sum(1 for r in rows if not r["per_unit"]),
            "scanned": seen[:16]}


def shop_side(market_id: str) -> Optional[dict]:
    """The shop half of a market: its ledger, who runs it, what it owes.

    §6.7: a LISTED market discloses ledger, staff and liabilities to everyone; a
    private one discloses nothing but its grade. The owner console has had all
    three since it was built, keyed to the person who owns the market — so a
    listed market's own investors could not see the things the rule says they
    are entitled to. The caller decides who may look; this just reads.
    """
    try:
        db = _db()
    except Exception:                               # pragma: no cover
        return None
    mid = str(market_id or "")
    month = _now_month()
    out = {"ledger": [], "staff": [], "liabilities": [], "month": month,
           "month_name": _month_name(month)}

    try:
        for day, item, verb, qty, coins in db._get_conn().execute(
                "SELECT sale_day, item, verb, qty, coins FROM csn_transactions "
                "WHERE market_id = ? ORDER BY sale_ts DESC LIMIT 40", (mid,)):
            amount = abs(float(coins or 0))
            bought_in = str(verb) == "sold"          # the shop bought stock in
            out["ledger"].append((
                _day_name(day), f"{item} ×{int(qty or 0)}",
                "Restock" if bought_in else "Sales",
                "" if bought_in else f"{amount:,.0f}c",
                f"{amount:,.0f}c" if bought_in else ""))
    except Exception as exc:
        log.warning("[abex_live] ledger for %s unreadable: %s", mid, exc)

    try:
        owner = str((db.get_markets() or {}).get(mid, {}).get("owner_id") or "")
        perf = {}
        for wid, coins, n in db._get_conn().execute(
                "SELECT worker_id, SUM(coins), COUNT(*) FROM team_perf_log "
                "WHERE manager_id = ? AND created_at >= ? GROUP BY worker_id",
                (owner, month + "-01")):
            perf[str(wid)] = (float(coins or 0), int(n or 0))
        for member in (db.get_team(owner) or []):
            wid = str(member.get("worker_id") if isinstance(member, dict) else member)
            paid, jobs = perf.get(wid, (0.0, 0))
            out["staff"].append((_owner_name(db, wid), "Worker", str(jobs),
                                 f"{paid:,.0f}c"))
    except Exception as exc:
        log.warning("[abex_live] staff for %s unreadable: %s", mid, exc)

    try:
        due = float(db.get_config(f"vault_due:{mid}") or 0)
        bal = float(db.get_config(f"vault_bal:{mid}") or 0)
        if due - bal > 1:
            out["liabilities"].append(
                ("Vault retention owed", "Abex Tech", f"{due - bal:,.0f}c",
                 "accrued from closed months"))
    except Exception:
        pass
    return out
