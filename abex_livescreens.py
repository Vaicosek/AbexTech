"""abex_livescreens.py — the canvas screens, built from the live database.

`abex_canvas` holds the design's screens with the design's SAMPLE rows.
`abex_render` draws whatever screen dict it is handed. This module produces the
same dict shape from `abex_live`, so the main site can render the design against
real money.

## The rule this module exists to keep

**A live screen never falls back to sample rows.** If a figure has no source, the
cell is an em dash and the block says so. The design's numbers are lovely and
they are not yours; a page that quietly shows 21,084c because the query failed is
worse than an empty one, because an empty table is obviously empty and a wrong
balance is not.

That is also why the column sets are kept from the canvas even where the data
cannot fill them. The shape stays honest — the reader sees that "Shares out" is a
column this product has and this market has not disclosed — and the cell says
nothing rather than guessing. It is the same convention the design already uses
for private markets: everything is `—` except the grade.

## What each screen can and cannot answer today

- `hub`      — Index, holdings, open orders and filings-this-month are real.
               The design's "Next report" tile is not: nothing in this schema
               stores a report due date, so that tile asks the same question the
               data can answer ("who still owes a report?") instead of inventing
               a date. `abex_live.hub` made that call already; it is kept here.
- `markets`  — grade, backing, last net and last report are real. Shares out and
               share price exist only for LISTED markets, so they come from the
               exchange listing where there is one and are `—` otherwise.
- `stocks`   — positions, cost, value and unrealised are real. Dividend a share
               is `none declared` because no dividend has ever been paid: the
               `stock_dividend_log` is empty, and an estimate here would be the
               only figure on the page nobody could check.
- `work`     — open orders, with the employee-priority window (spec §6.5).
- `lands`    — claims are bought outright in this economy; there is no rent
               anywhere in `land_listings`, so the design's rent columns are not
               rendered rather than filled with zeroes.
"""
from __future__ import annotations

import logging

log = logging.getLogger("abex_livescreens")

try:
    import abex_live
except Exception:                                   # pragma: no cover
    abex_live = None

from abex_canvas import SCREENS as _CANVAS

#: What a cell says when the product has the column and no answer for it.
DASH = "m|—"


def _cols(screen_key: str, block_index: int) -> list:
    """The canvas's own column headings for a block, so live and design agree."""
    try:
        return list(_CANVAS[screen_key]["blocks"][block_index]["c"])
    except Exception:
        return []


def _shell(key: str, asof: str, band, blocks) -> dict:
    canvas = _CANVAS.get(key, {})
    return {"d": canvas.get("d", key), "title": canvas.get("title", key.title()),
            "asof": asof, "band": band, "blocks": blocks}


def _empty(key: str, why: str) -> dict:
    """The screen with its real shape and no rows, and a line saying why.

    Used when the bot's modules are not importable — in a bare container, or
    while core is restarting. The alternative is the design's sample data on a
    live route, which is the one thing this module will not do.
    """
    canvas = _CANVAS.get(key, {})
    blocks = []
    for b in canvas.get("blocks", []):
        nb = {k: v for k, v in b.items() if k in ("h2", "ac", "own", "c")}
        if "c" in nb:
            nb["r"] = []
        nb["n"] = why
        blocks.append(nb)
    return {"d": canvas.get("d", key), "title": canvas.get("title", key.title()),
            "asof": why, "band": [], "blocks": blocks}


# ── Hub ─────────────────────────────────────────────────────────────────────
def hub(user_id: str) -> dict:
    if abex_live is None:
        return _empty("hub", "The exchange is not reachable from this process.")
    data = abex_live.hub(str(user_id))
    if not data:
        return _empty("hub", "The exchange is not reachable right now.")

    band = [(t[0], t[1], t[2]) for t in data["tiles"]]

    # "Today" — the waiting-on-you queue. Live orders are the only thing this
    # schema can say is waiting; the design also lists a due report and unread
    # messages, and neither has a source here, so neither is faked.
    work_rows = []
    for item, qty, pay, market, window, _tone in data.get("work", []):
        who = ("m|" + window) if window else "g|Open to all"
        work_rows.append([f"{item} for {market}, {qty} at {pay}", who, "k|Claim"])
    today = {"h2": "Today", "ac": 1, "c": _cols("hub", 0),
             "r": work_rows,
             "n": (f"{len(work_rows)} open order{'' if len(work_rows) == 1 else 's'}, "
                   "soonest first." if work_rows else "Nothing is waiting on you.")}

    by_grade = {"h2": "Markets by grade", "c": _cols("hub", 1),
                "r": [[m[1], "G|" + m[3], m[4], m[5], DASH, m[7]]
                      for m in data.get("markets", [])],
                "n": data.get("dividend_note", "")}

    dividends = {"h2": "Dividends",
                 "bal": [["Confirmed, last cycle", data["dividends"][0], ""],
                         ["Estimated, next cycle", data["dividends"][1], ""]]}
    return _shell("hub", data.get("sub", ""), band, [today, by_grade, dividends])


# ── Markets ─────────────────────────────────────────────────────────────────
def markets(user_id: str = "") -> dict:
    if abex_live is None:
        return _empty("markets", "The exchange is not reachable from this process.")
    rows = abex_live.markets()
    if rows is None:
        return _empty("markets", "The market registry is not readable right now.")

    listings = {}
    ex = abex_live.exchange() or {}
    for r in ex.get("rows", []):
        listings[r[1]] = r            # keyed by market NAME, which is what rows carry

    held = {}
    live = abex_live.stocks(str(user_id)) if user_id else None
    for row in (live or {}).get("rows", []):
        held[row[0]] = row[1]         # market name -> shares

    graded = sum(1 for m in rows if m[3] in ("AAA", "AA", "A", "BBB"))
    band = [("Markets", str(len(rows)),
             f"{len(listings)} listed, {len(rows) - len(listings)} private"),
            ("Investment grade", f"{graded} of {len(rows)}", "BBB or better"),
            ("Listed", str(len(listings)), "shares you can trade"),
            ("Your positions", str(len(held)), "markets you hold")]

    all_rows = []
    for ticker, name, _owner, grade, backing, last_net, _weight, last_report in rows:
        L = listings.get(name)
        all_rows.append([
            name, "G|" + grade, backing, last_net,
            L[3] if L else DASH,                    # shares out
            L[5] if L else DASH,                    # share price
            held.get(name, DASH),                   # you hold
            "Listed" if L else "m|Private",
            last_report,
        ])
    table = {"h2": "All markets", "ac": 1, "c": _cols("markets", 1), "r": all_rows,
             "n": ("Shares out and share price exist only for a listed market; "
                   "a private market discloses nothing but its grade.")}
    return _shell("markets", f"{len(rows)} markets, {len(listings)} of them listed.",
                  band, [table])


# ── Stocks ──────────────────────────────────────────────────────────────────
def stocks(user_id: str) -> dict:
    if abex_live is None:
        return _empty("stocks", "The exchange is not reachable from this process.")
    data = abex_live.stocks(str(user_id))
    if data is None:
        return _empty("stocks", "The share register is not readable right now.")

    rows = data.get("rows", [])
    value = cost = 0.0
    positions = []
    for r in rows:
        # (name, shares, avg cost, price, value, profit, up?, dividend, month)
        try:
            v = float(str(r[4]).rstrip("c").replace(",", ""))
            c = float(str(r[2]).rstrip("c").replace(",", "")) * float(str(r[1]).replace(",", ""))
        except (ValueError, IndexError):
            v = c = 0.0
        value += v
        cost += c
        up = bool(r[6]) if len(r) > 6 else True
        positions.append([r[0], r[1], r[3], r[4], r[2],
                          ("g|" if up else "l|") + str(r[5]),
                          r[7] if len(r) > 7 else DASH])

    unrealised = value - cost
    band = [("Holdings", f"{value:,.0f}c", f"{len(rows)} position"
             f"{'' if len(rows) == 1 else 's'}", "g" if value else ""),
            ("Unrealised", f"{unrealised:+,.0f}c", "value less cost",
             "g" if unrealised >= 0 else "l"),
            ("Dividends", "none paid yet", "no market has declared one"),
            ("Cost", f"{cost:,.0f}c", "what you paid")]

    pos = {"h2": "Your positions", "ac": 1, "c": _cols("stocks", 1), "r": positions,
           "n": "" if positions else "You hold no shares."}
    portfolio = {"h2": "Portfolio",
                 "bal": [["Value", f"{value:,.2f}c", ""],
                         ["Less cost", f"{cost:,.2f}c", "what you paid for it"]],
                 "tot": ["Unrealised", ("g|" if unrealised >= 0 else "l|")
                         + f"{unrealised:+,.2f}c"]}
    return _shell("stocks", f"{len(rows)} position"
                  f"{'' if len(rows) == 1 else 's'} in your name.",
                  band, [pos, portfolio])


# ── Work ────────────────────────────────────────────────────────────────────
def work(user_id: str = "") -> dict:
    if abex_live is None:
        return _empty("work", "The exchange is not reachable from this process.")
    rows = abex_live.orders()
    if rows is None:
        return _empty("work", "Open orders are not readable right now.")

    out = []
    for item, market, _owner, qty, detail, unit, per, total, _pts, prio, window in rows:
        out.append([f"{item} for {market}", detail or qty, f"{unit} {per}", total,
                    ("l|" if prio else "g|") + (window or "Open to all"), "k|Claim"])
    band = [("Open jobs", str(len(rows)), "claimable right now"),
            ("Markets hiring", str(len({r[1] for r in rows})), "posting work"),
            ("Employee-priority", str(sum(1 for r in rows if r[9])),
             "first 45 minutes"),
            ("Open to all", str(sum(1 for r in rows if not r[9])), "anyone may claim")]
    table = {"h2": "Open jobs", "ac": 1,
             "c": ["Job", "Quantity", "Pay#", "Total#", "Who can act", "#"],
             "r": out,
             "n": ("A new job is employee-only for its first 45 minutes, then "
                   "open to all." if out else "No open jobs.")}
    return _shell("work", f"{len(rows)} open job{'' if len(rows) == 1 else 's'}.",
                  band, [table])


# ── Claims (land) ───────────────────────────────────────────────────────────
def lands(user_id: str = "") -> dict:
    if abex_live is None:
        return _empty("lands", "Estates are not reachable from this process.")
    rows = abex_live.parcels()
    if rows is None:
        return _empty("lands", "Land listings are not readable right now.")

    out = [[name, owner or DASH, price, state, note or ""]
           for name, owner, _tenant, price, state, note in rows]
    band = [("Claims", str(len(rows)), "on the register"),
            ("For sale", str(sum(1 for r in rows if "sale" in str(r[4]).lower())),
             "listed right now"),
            ("Owned", str(sum(1 for r in rows if r[1])), "have an owner"),
            ("Rent", "none", "claims are bought outright")]
    table = {"h2": "Claims", "ac": 1,
             "c": ["Claim", "Owner", "Price#", "State", "Note"], "r": out,
             "n": ("A claim is bought outright and transfers with whatever is "
                   "built on it — there is no recurring rent."
                   if out else "No claims on the register.")}
    return _shell("lands", f"{len(rows)} claim{'' if len(rows) == 1 else 's'} "
                  "on the register.", band, [table])


#: key -> builder. A screen absent here has no live source yet and keeps its
#: canvas page under /canvas; it is NOT served with sample rows on a live route.
BUILDERS = {
    "hub": hub, "markets": markets, "stocks": stocks, "work": work, "lands": lands,
}


def screen(key: str, user_id: str = "") -> dict | None:
    fn = BUILDERS.get(key)
    if fn is None:
        return None
    try:
        return fn(user_id)
    except Exception as exc:                        # pragma: no cover
        log.warning("[livescreens] %s failed: %s", key, exc, exc_info=True)
        return _empty(key, "That screen could not be built from live data.")
