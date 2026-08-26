"""abex_livescreens.py — the canvas screens, built from the live database.

`abex_canvas` holds the design's screens - their titles, column headings and
block order - with the design's sample rows still attached. Those rows are read
by nothing: they were served under `/canvas/*` while each screen was being wired
and that set is retired. What is read is the SHAPE.
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

#: Column headings that are about the READER, not about the thing listed.
PERSONAL_COLUMNS = {"you hold", "your position", "shares", "value", "cost",
                    "unrealised", "dividend last cycle"}

#: Band tiles that are about the reader, matched on the label, case-folded.
PERSONAL_TILES = {"your holdings", "holdings", "unrealised", "cost",
                  "your positions", "open orders"}


def depersonalise(screen: dict) -> dict:
    """The same screen with everything about the reader removed.

    Spec §7: "Role gating changes visibility, not copy - an investor and an owner
    see the same sentence structure, just fewer blocks." So this drops columns,
    tiles and whole blocks; it does not rewrite a sentence or swap in a friendlier
    heading. A stranger reads the same page with less in it.

    Columns are DROPPED, not dashed. An em dash already means something specific
    in this design - "the product has this column and this market did not
    disclose it", a fact about the market. For a signed-out reader the truth is
    different: the column is about them, and there is no them yet. A wall of
    dashes would say the wrong thing in the design's own vocabulary.

    A balance block goes entirely. Portfolio, credit limit, your bids - each is a
    personal statement end to end, and there is no public half of one.
    """
    out = dict(screen)
    out["band"] = [t for t in (screen.get("band") or [])
                   if str(t[0]).strip().lower() not in PERSONAL_TILES]
    blocks = []
    for b in screen.get("blocks", []):
        if "bal" in b:
            continue
        nb = dict(b)
        heads = nb.get("c") or []
        keep = [i for i, h in enumerate(heads)
                if str(h).rstrip("#").strip().lower() not in PERSONAL_COLUMNS]
        if heads and len(keep) != len(heads):
            nb["c"] = [heads[i] for i in keep]
            nb["r"] = [[row[i] for i in keep if i < len(row)]
                       for row in (nb.get("r") or [])]
        blocks.append(nb)
    out["blocks"] = blocks
    return out


def _num(cell) -> float:
    """A bare number out of a formatted cell. 0.0 when it is not one."""
    try:
        return float(str(cell).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def _coins(cell) -> float:
    """A coin figure out of a cell like `1,234.50c` or `+92,328c`."""
    return _num(str(cell).rstrip("c").lstrip("+"))


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
def _your_filings_due(user_id: str) -> list:
    """Rows for the Hub queue: markets THIS reader owns that have not filed.

    A market being behind is on the Markets screen for everyone. This puts it in
    front of the one person who can fix it, which is the difference between a
    register and a queue. Amazonia went two filings behind before a player
    mentioned it in Discord — its owner was never told by the site.
    """
    if abex_live is None or not user_id:
        return []
    try:
        mine = {m["market_id"] for m in abex_live.owned_markets(str(user_id))}
    except Exception:
        return []
    if not mine:
        return []
    try:
        status = abex_live.filing_status() or []
    except Exception:
        return []
    out = []
    for r in status:
        if r["market_id"] not in mine or r["months_behind"] < 1:
            continue
        behind = r["months_behind"]
        days = r["days_since"]
        since = f", {days:,} days since the last one" if days is not None else ""
        out.append([
            f"File the report for {r['name']} — "
            f"{behind} month{'' if behind == 1 else 's'} behind{since}",
            ("l|" if behind > 1 else "w|") + f"last filed {r['last_month_name']}",
            "k|Open",
        ])
    return out


def hub(user_id: str) -> dict:
    if abex_live is None:
        return _empty("hub", "The exchange is not reachable from this process.")
    data = abex_live.hub(str(user_id))
    if not data:
        return _empty("hub", "The exchange is not reachable right now.")

    band = [(t[0], t[1], t[2]) for t in data["tiles"]]

    # "Today" — the waiting-on-you queue. The design also lists unread messages,
    # which has no source here and is not faked. A due REPORT does have one now:
    # not a date, which nothing stores, but the fact that a market you own has
    # not filed for the current month. That belongs at the top of this queue
    # rather than only on Markets — the owner is the one who can act on it, and
    # he has no reason to be reading the market register to find out.
    due = _your_filings_due(user_id)
    work = []
    for item, qty, pay, market, window, _tone in data.get("work", []):
        who = ("m|" + window) if window else "g|Open to all"
        work.append([f"{item} for {market}, {qty} at {pay}", who, "k|Claim"])
    # Reports first: an order can be claimed by anybody, a filing only by him.
    rows = due + work

    parts = []
    if due:
        parts.append(f"{len(due)} report{'' if len(due) == 1 else 's'} you owe")
    if work:
        parts.append(f"{len(work)} open order{'' if len(work) == 1 else 's'}")
    note = (" and ".join(parts) + ".") if parts else "Nothing is waiting on you."
    today = {"h2": "Today", "ac": 1, "c": _cols("hub", 0), "r": rows, "n": note}

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
        held[row[1]] = row[3]         # NAME -> shares; row[0] is the ticker

    graded = sum(1 for m in rows if m[3] in ("AAA", "AA", "A", "BBB"))
    band = [("Markets", str(len(rows)),
             f"{len(listings)} listed, {len(rows) - len(listings)} private"),
            ("Investment grade", f"{graded} of {len(rows)}", "BBB or better"),
            ("Listed", str(len(listings)), "shares you can trade"),
            ("Your positions", str(len(held)), "markets you hold")]

    # Every market gets a page, listed or not: a private one's page says it is
    # private and shows its grade, which is exactly what §6.7 says it discloses.
    # A name that leads nowhere for 17 of 19 rows is a worse rule than a page
    # that honestly has little on it.
    try:
        ids = {(m or {}).get("name"): k
               for k, m in (abex_live._db().get_markets() or {}).items()}
    except Exception:
        ids = {}
    all_rows = []
    for ticker, name, _owner, grade, backing, last_net, _weight, last_report in rows:
        L = listings.get(name)
        mid = ids.get(name)
        all_rows.append([
            (f"A|/hub/stocks/{mid}|{name}" if mid else name),
            "G|" + grade, backing, last_net,
            L[3] if L else DASH,                    # shares out
            L[5] if L else DASH,                    # share price
            held.get(name, DASH),                   # you hold
            "Listed" if L else "m|Private",
            last_report,
        ])
    table = {"h2": "All markets", "ac": 1, "c": _cols("markets", 1), "r": all_rows,
             "n": ("Shares out and share price exist only for a listed market; "
                   "a private market discloses nothing but its grade.")}
    # NO "WAITING ON A FILING" PANEL. It named markets that were a month behind
    # at the top of the public Markets screen, and the answer to what it was for
    # is: nothing this product does. Nothing in the engine penalises a late
    # filing — the history pillar counts closed months on record, so a quiet
    # market stops GAINING, it is not docked — and the block's own note claimed
    # a grade-band drop that has never existed. A panel that shames two owners
    # for a rule the code does not enforce is worse than no panel.
    #
    # An owner is still told about HIS OWN market: `_your_filings_due` puts it in
    # the Hub's waiting-on-you queue, where it is a thing he can act on rather
    # than a thing everyone else reads about him.
    blocks = [table]
    return _shell("markets", f"{len(rows)} markets, {len(listings)} of them listed.",
                  band, blocks)


# ── Stocks ──────────────────────────────────────────────────────────────────
def stocks(user_id: str = "", csrf: str = "") -> dict:
    """THE TRADING PAGE. Every listed market: its line, its price, buy and sell.

    This replaced a seven-column positions table. Market, shares, price, value,
    cost, unrealised, dividend — for GreyHames that is 92,863 / 999.77c /
    92,841,741c / 96,183,410c / -3,341,188c across one row, and the last column
    said "none declared" and always would. Seven figures of the same size, one of
    them dead, and nowhere to act on any of it.

    A holder asks two things: what is it doing, and do I buy or sell. So each
    market is a section — the line, then what you hold in one sentence, then the
    ticket — and the page is those sections stacked. Two listed markets today, so
    it is short; it stays readable at ten because a section is three blocks and
    not a row of twelve columns.
    """
    if abex_live is None:
        return _empty("stocks", "The exchange is not reachable from this process.")
    try:
        db = abex_live._db()
        listings = db.get_public_markets() or {}
        registry = db.get_markets() or {}
    except Exception as exc:
        log.warning("[livescreens] listings unreadable: %s", exc)
        return _empty("stocks", "The share register is not readable right now.")

    held = {}
    data = abex_live.stocks(str(user_id)) if user_id else None
    for r in (data or {}).get("rows", []):
        # 0 ticker 1 name 2 grade 3 shares 4 average cost 5 price 6 value 7 profit
        held[str(r[1])] = {"shares": _num(r[3]), "avg": _coins(r[4]),
                           "value": _coins(r[6]), "profit": _coins(r[7]),
                           "up": bool(r[8]) if len(r) > 8 else True}

    value = sum(h["value"] for h in held.values())
    cost = sum(h["avg"] * h["shares"] for h in held.values())
    unrealised = value - cost

    band = [("Your holdings", f"{value:,.0f}c",
             f"across {len(held)} market{'' if len(held) == 1 else 's'}"),
            ("Unrealised", f"{unrealised:+,.0f}c", "value less what you paid",
             "g" if unrealised >= 0 else "l"),
            ("Listed", str(len(listings)), "markets you can trade"),
            ("Dividends", "none paid yet", "no market has declared one")]

    blocks = []
    for mid, listing in sorted(listings.items(),
                               key=lambda kv: -float((kv[1] or {}).get("share_price") or 0)):
        name = str((registry.get(mid) or {}).get("name") or mid)
        price = float((listing or {}).get("share_price") or 0)
        mine = held.get(name)

        chart = _spark_block(name, abex_live.price_series(mid, 30),
                             src=f"/api/series/market/{mid}?days=30", note="")
        if chart is None:
            chart = {"h2": name, "c": [], "r": [],
                     "n": "No price has been recorded for this market yet."}
        else:
            chart["spark"]["live"] = 1
            chart["spark"]["mid"] = mid
        blocks.append(chart)

        if mine:
            tone = "g|" if mine["up"] else "l|"
            blocks.append({
                "bal": [["You hold", f"{mine['shares']:,.0f} shares", ""],
                        ["Worth today", f"{mine['value']:,.0f}c",
                         f"at {price:,.2f}c a share"],
                        ["You paid", f"{mine['avg'] * mine['shares']:,.0f}c",
                         f"{mine['avg']:,.2f}c a share on average"]],
                "tot": ["Unrealised", tone + f"{mine['profit']:+,.0f}c"]})
        else:
            blocks.append({"bal": [["You hold", "nothing", ""]],
                           "n": "Nothing is committed until you place an order."})

        if user_id and csrf and price > 0:
            hold = mine["shares"] if mine else 0.0
            blocks.append({
                "ticket": {"market_id": mid, "price": price, "you_hold": hold,
                           "csrf": csrf,
                           "hint": (f"Selling is capped at the {hold:,.0f} you hold."
                                    if hold else "You hold none of this market yet.")}})

        blocks.append({"act": "", "btns": [["Everything about " + name, "s",
                                            f"/hub/stocks/{mid}"]],
                       "n": "Months filed, the grade and its pillars, the register, "
                            "and what moves through the shop."})

    if not blocks:
        return _shell("stocks", "No market is listed yet.", band,
                      [{"h2": "Nothing to trade", "c": [], "r": [],
                        "n": "A market appears here when its owner lists it."}])

    asof = (f"{len(listings)} market{'' if len(listings) == 1 else 's'} listed. "
            "Prices refresh every minute.")
    return _shell("stocks", asof, band, blocks)


def _item_block(market_id: str, listed: bool, owner: bool) -> dict | None:
    """What moves through a market, item by item, month by month.

    Two columns per month because in and out are different trades. An item that
    sold 4,465 and bought 3,727 is a shop turning stock over; a single
    "movement" figure would read as one number and hide which direction the
    shop is leaning.

    §6.7 gates it: a LISTED market discloses its ledger to everyone, so this is
    public on one. A PRIVATE market discloses nothing — except to its own owner,
    who is not a stranger to his own shop. Anyone else gets no block at all
    rather than an empty table, which would advertise that there is something
    here to see.
    """
    if not (listed or owner):
        return None
    if abex_live is None:
        return None
    data = abex_live.market_items(market_id, months=3, limit=30)
    if data is None or not data.get("months"):
        return None

    cols = ["Item"]
    for _key, name in data["months"]:
        short = name.split()[0]
        cols += [f"{short} out#", f"{short} in#"]
    cols.append("Net#")

    rows = []
    for r in data["rows"]:
        cells = [r["item"]]
        for sold, bought in r["cells"]:
            cells.append(f"{sold:,}" if sold else DASH)
            cells.append(f"{bought:,}" if bought else DASH)
        net = r["net"]
        cells.append(("g|" if net >= 0 else "l|") + f"{net:+,.0f}c")
        rows.append(cells)

    shown, total = len(rows), data["total_items"]
    more = ("" if shown >= total
            else f" {total - shown} further item"
                 f"{'' if total - shown == 1 else 's'} moved less and are not listed.")
    note = (f"{shown} of {total} items, most moved first. OUT is what the shop "
            f"sold to players; IN is what it bought from them — opposite trades, "
            f"so they are opposite columns. Net is coins across the window.{more}")
    if not listed:
        note += (" This market is private: only you can see this.")
    return {"h2": "What moves here", "c": cols, "r": rows, "n": note}


#: Mirrors the engine's ladder so the page can say which constraint bound.
_GRADE_RANK = {"C": 0, "BB": 1, "BBB": 2, "A": 3, "AA": 4, "AAA": 5}


def _grade_block(market_id: str, grade: str) -> dict | None:
    """Why this market has this grade — the pillars, and the cap that binds.

    Written because two markets read BBB with 0.79x and 1.03x backing and there
    was no way to tell from the page whether that was the rating working or the
    rating broken. It was both, and neither half was visible.

    An UNMEASURED pillar reads "no data" and is out of the average, not a zero.
    That distinction is the whole block: a feed that has never delivered a row
    scored every market zero on a quarter of its composite, which is how eleven
    markets ended up indistinguishable.
    """
    if abex_live is None:
        return None
    d = abex_live.grade_detail(market_id)
    if d is None:
        return None

    rows = []
    for r in d["rows"]:
        if r["measured"]:
            score = f"{r['score'] * 100:,.0f}%"
            tone = "g|" if r["score"] >= 0.75 else ("w|" if r["score"] >= 0.4 else "l|")
            weight = f"{r['weight'] * 100:,.0f}%"
        else:
            score, tone, weight = "no data", "m|", "m|out of the average"
        rows.append([r["label"], (tone + score) if r["measured"] else "m|no data",
                     weight, "m|" + r["note"]])

    # NAME THE CONSTRAINT THAT ACTUALLY BINDS. Three can: the composite's own
    # band, the backing cap, and vault arrears. The note used to blame the cap
    # every time, which is how Amazonia came to show four pillars adding up to
    # AA over a grade reading BBB with an explanation that fitted neither.
    ratio = d["backing_ratio"]
    band, cap = d.get("band", ""), d.get("cap", "")
    note = (f"Composite {d['score'] * 100:,.0f}% of the pillars that could be "
            f"measured, which is {band} on its own.")
    if d.get("vault_binds"):
        note += (f" It reads {grade} because {d['vault_arrears']:,.0f}c of "
                 "retained earnings are owed to the vault, and a market in "
                 "arrears cannot rate above BBB whatever else it has. Pay the "
                 "vault first.")
    elif cap and band and cap != band and _GRADE_RANK.get(cap, 9) < _GRADE_RANK.get(band, 0):
        note += (f" Backing of {ratio:,.2f}x the target allows {cap} at most — "
                 "collateral gates the top two bands, so a market cannot score "
                 "its way into AA or AAA without the chests.")
    else:
        note += (f" Backing of {ratio:,.2f}x the target allows up to {cap}, so "
                 "nothing is holding it back.")

    unmeasured = [r["label"] for r in d["rows"] if not r["measured"]]
    if unmeasured:
        one = len(unmeasured) == 1
        note += (" " + " and ".join(unmeasured) +
                 (" has no data feeding it, so it is" if one
                  else " have no data feeding them, so they are") +
                 " left out of the average rather than counted as zero.")
    # The backing pillar is one number made of six. When it is the thing holding
    # a grade down, "79%" is not an answer a market owner can act on.
    for label, pct, coins in (d.get("backing_parts") or []):
        if pct <= 0:
            continue
        rows.append(["  " + label, f"m|{pct:,.1f}%", "m|of market cap",
                     f"m|{coins:,.0f}c"])

    if d.get("uncounted_lines"):
        n = int(d["uncounted_lines"])
        rows.append(["  Inventory not counted", f"w|{n:,} line{'' if n == 1 else 's'}",
                     "m|priced per stack",
                     "m|a per-stack price valued per unit reads up to 64x high, so "
                     "these are skipped until the next stock scan rewrites them"])

    if d.get("vault_arrears", 0) > 1:
        binds = d.get("vault_binds")
        rows.append(["Vault arrears",
                     ("l|" if binds else "m|") + f"{d['vault_arrears']:,.0f}c",
                     "m|caps at BBB" if binds else "m|does not bind",
                     ("m|10% of each closed month, retained; unpaid here" if binds
                      else "m|nobody outside the owner holds this market, so the "
                           "retention protects nobody")])

    return {"h2": f"Why this market is {grade}",
            "c": ["Pillar", "Score#", "Weight#", "What it measures"],
            "r": rows, "n": note}


def _shop_blocks(market_id: str, name: str, listed: bool, owner: bool) -> list:
    """The shop side: shelves, ledger, who runs it, what it owes.

    §6.7 decides who sees it — a LISTED market discloses ledger, staff and
    liabilities to everyone; a private one to its owner only. All four have
    existed in the database the whole time and none were on a market's page, so
    the site could tell you a market was rated on its inventory and never show
    you the inventory.
    """
    if abex_live is None or not (listed or owner):
        return []
    out = []

    sh = abex_live.shelves(market_id)
    if owner and sh is not None and not sh["rows"]:
        # AN EMPTY SHELF IS A FACT TO THE OWNER AND NOISE TO EVERYONE ELSE.
        # Empty states stay empty on a public page — a headed table with nothing
        # in it is a worse read than no table. But the owner is asking a
        # question the absence answers: he sees "there is no inventory here" and
        # concludes the SITE has none, when what it means is that no stock scan
        # has ever recorded a line for his shop. So the block stands for him,
        # and says which of the two it is.
        out.append({"h2": "On the shelves",
                    "c": ["Item", "In stock#", "Capacity#", "Sells at#",
                          "Buys at#", "Backing"],
                    "r": [],
                    "n": ("No stocked line has ever been recorded for this shop. "
                          "Inventory comes from a stock scan — until one runs, "
                          "there is nothing here to back the shares, and the "
                          "rating sees the same nothing."
                          if not sh["scanned"] else
                          "The last stock scan (" + sh["scanned"].replace("T", " ")
                          + ") found no stocked lines.")})
    if sh and sh["rows"]:
        rows = []
        for r in sh["rows"]:
            # A LEGACY ROW'S PRICE IS PER STACK, NOT PER PIECE. Nothing
            # downstream trusts it — `_market_asset_value` skips the row — so it
            # is not rendered as a per-piece figure here either. Saying "per
            # stack" is the whole difference between a price and a 64x error.
            unit = "a piece" if r["per_unit"] else "a stack"
            rows.append([
                r["item"], f"{r['stock']:,.0f}",
                (f"{r['capacity']:,.0f}" if r["capacity"] else DASH),
                (f"{r['sell']:,.0f}c {unit}" if r["sell"] else DASH),
                (f"{r['buy']:,.0f}c {unit}" if r["buy"] else DASH),
                ("m|counted" if r["per_unit"] else "w|not counted"),
            ])
        note = (f"{len(rows)} of {sh['lines']} stocked lines, most valuable first. "
                f"Last scanned {sh['scanned'].replace('T', ' ')}.")
        if sh["legacy_lines"]:
            note += (f" {sh['legacy_lines']:,} line"
                     f"{'' if sh['legacy_lines'] == 1 else 's'} carry a per-STACK "
                     "price from an older scan. They back the shares by nothing "
                     f"— {sh['uncounted']:,.0f}c of stock the rating cannot see — "
                     "because valuing a per-stack price per piece reads up to 64x "
                     "high. A fresh stock scan rewrites them.")
        out.append({"h2": "On the shelves",
                    "c": ["Item", "In stock#", "Capacity#", "Sells at#",
                          "Buys at#", "Backing"],
                    "r": rows, "n": note})

    side = abex_live.shop_side(market_id)
    if not side:
        return out

    if side["ledger"]:
        out.append({"h2": f"Ledger, {side['month_name'].split()[0]}",
                    "c": ["Date", "Entry", "Category", "In#", "Out#"],
                    "r": [[d, e, c, ("g|" + i if i else DASH),
                           ("l|" + o if o else DASH)]
                          for d, e, c, i, o in side["ledger"]],
                    "n": "Sales are what customers bought; restock is what the "
                         "shop bought in."})

    if side["staff"]:
        out.append({"h2": "Who runs it",
                    "c": ["Worker", "Role", "Jobs this month#", "Paid#"],
                    "r": [list(r) for r in side["staff"]],
                    "n": "Paid is what the team log recorded this month."})

    if side["liabilities"]:
        out.append({"h2": "Liabilities",
                    "c": ["Item", "Held by", "Amount#", "Note"],
                    "r": [[a, b, c, "m|" + d] for a, b, c, d in side["liabilities"]],
                    "n": "Serviced out of net before dividends."})
    return out


# ── One stock ───────────────────────────────────────────────────────────────
def stock(user_id: str = "", market_id: str = "", csrf: str = "") -> dict:
    """One market's page: the price, its shape, its months, its register.

    Not a canvas screen — the design has a Stocks screen that lists YOUR
    positions and a Markets screen that lists everyone's, and neither answers
    "how has this one done". That question is what a reader asks before buying,
    and answering it in a tooltip on a table row is answering it badly.

    Spec §6.7 decides what goes on it: a LISTED market discloses; a private one
    discloses nothing but its grade. An unlisted market therefore gets a real
    page with almost nothing on it, which is the honest shape — the reader
    learns that the market exists, what it is rated, and that it has chosen not
    to disclose. A 404 would teach him nothing.
    """
    if abex_live is None:
        return _empty("stocks", "The exchange is not reachable from this process.")
    d = abex_live.stock_detail(str(market_id), str(user_id))
    if d is None:
        return _empty("stocks", "No such market.")

    # Whether the reader owns this market. It decides one thing only: whether a
    # PRIVATE market's item table is built. §6.7 keeps a private market's trade
    # from everyone else; it was never meant to keep it from its own owner.
    owner = False
    if user_id:
        try:
            owner = any(m["market_id"] == d["market_id"]
                        for m in abex_live.owned_markets(str(user_id)))
        except Exception:
            owner = False

    grade_sub = (f"{d['backing']:,.2f}× backed" if d["backing"] else "not scored")
    if not d["listed"]:
        band = [("Grade", d["grade"], grade_sub),
                ("Listed", "no", "shares are not traded"),
                ("Discloses", "grade only", "a private market publishes nothing else")]
        note = {"h2": "Private market", "ac": 1,
                "act": (f"{d['name']} is not listed on the exchange. A private "
                        "market discloses its grade and nothing else — no ledger, "
                        "no staff, no liabilities — and that is the bargain it "
                        "took by not listing."),
                "btns": [["Back to the exchange", "s", "/hub/exchange"]],
                "n": "Its grade is still scored from the same pillars as everyone "
                     "else's, which is why it can be shown."}
        # Its OWNER is not a stranger to his own shop. §6.7 keeps a private
        # market's trade from everybody else, and returning here without this
        # meant it was kept from him too — he would have had to list the market
        # publicly to read his own item ledger.
        blocks = [note]
        mine = _item_block(d["market_id"], False, owner)
        if mine is not None:
            blocks.append(mine)
        blocks += _shop_blocks(d["market_id"], d["name"], False, owner)
        out = _shell("stocks", f"{d['name']} · private", band, blocks)
        out["title"] = d["name"]
        return out

    price, shares = d["price"], d["shares_out"]
    mcap = price * shares
    band = [("Share price", f"{price:,.2f}c",
             (f"priced from {abex_live._month_name(d['last_priced_month'])}"
              if d.get("last_priced_month") else "not priced yet")),
            ("Grade", d["grade"], grade_sub),
            ("Growth P/E", f"{d['pe']:,.2f}×", "multiple applied to trailing net"),
            ("Shares listed", f"{shares:,.0f}",
             f"{d['holders']} holder{'' if d['holders'] == 1 else 's'}")]

    chart = _spark_block(
        f"{d['name']} · share price", d.get("series"),
        src=f"/api/series/market/{d['market_id']}?days=90",
        note=("Every point is a price the exchange recorded. The series is "
              "sampled, never averaged, so no point drawn is a price nobody saw."))

    # ── the months ──────────────────────────────────────────────────────────
    nets = d.get("nets") or {}
    rows = []
    for m in d["months"]:
        change = m["change"]
        if change is None:
            cell, pct = DASH, DASH
        else:
            tone = "g|" if change >= 0 else "l|"
            cell = f"{tone}{change:+,.0f}c"
            pct = (f"{tone}{m['pct']:+,.1f}%" if m["pct"] is not None
                   else "m|no prior month")
        rows.append([m["name"], f"{m['income']:,.0f}c", f"{m['spent']:,.0f}c",
                     f"{m['net']:,.0f}c", cell, pct])
    months = {"h2": "Month by month", "ac": 1,
              "c": ["Month", "Revenue#", "Costs#", "Net#", "Change#", "Change %#"],
              "r": rows,
              "n": (f"{len(rows)} of {nets.get('months', len(rows))} filed months, "
                    "each against the one before it. Net is the FILED "
                    "figure — what stands on the record, which is what the share "
                    "price is derived from, not what the shop has taken since."
                    if rows else "Nothing filed yet.")}

    price_block = {"h2": "How the price is set",
                   "bal": [[label, value, ""] for label, value, _t in d["price_rows"]],
                   "n": ("From the pricing function the bot itself quotes, so this "
                         "page and /stock price cannot disagree."
                         if d["price_rows"] else
                         "The pricing function is not reachable from this process. "
                         "It is not being estimated here.")}

    float_pct = (d["free_float"] / shares * 100.0) if shares else 0.0
    register = {"h2": "The register",
                "bal": [["Shares outstanding", f"{shares:,.0f}", ""],
                        ["Held by the owner", f"{d['owner_holds']:,.0f}",
                         "not free float"],
                        ["In other hands", f"{d['free_float']:,.0f}",
                         f"{float_pct:,.1f}% of the register"],
                        ["Holder accounts", f"{d['holders']:,.0f}", ""],
                        ["Market capitalisation", f"{mcap:,.0f}c",
                         "price × shares outstanding"]],
                "n": ("How many accounts hold this and how much of it is in "
                      "someone else's hands are facts about the security. Who "
                      "holds which shares is a fact about a person, and nothing "
                      "asks him to publish it.")}

    if chart is not None:
        # The live price rides on the chart here too, so the market page and the
        # trading page cannot disagree about what a share costs.
        chart["spark"]["live"] = 1
        chart["spark"]["mid"] = d["market_id"]

    # THE SECOND LINE, AND THE LONGER ONE. The price log starts when the exchange
    # started logging prices — three weeks for GreyHames. Its earnings go back to
    # April 2024. Drawing only the price says a market with two years of accounts
    # has no history.
    net_chart = None
    if nets.get("points"):
        net_chart = _spark_block(
            "Net, every filed month", nets,
            note=("What the market earned, per month, as filed. A month closes "
                  "once, so this line does not move between filings."))

    items = _item_block(d["market_id"], d["listed"], owner)

    ticket = None
    if user_id and csrf and price > 0 and shares > 0:
        held = d["your_shares"]
        ticket = {"h2": "Trade", "ac": 1,
                  "ticket": {"market_id": d["market_id"], "price": price,
                             "you_hold": held, "csrf": csrf,
                             "hint": ("You hold %s share%s. Selling is capped at "
                                      "what you hold." % (f"{held:,.0f}",
                                                          "" if held == 1 else "s"))
                             if held else "You hold none of this market yet."}}

    grade_block = _grade_block(d["market_id"], d["grade"])
    shop = _shop_blocks(d["market_id"], d["name"], d["listed"], owner)
    blocks = ([b for b in (chart, net_chart, months) if b is not None]
              + shop
              + [b for b in (items, grade_block, price_block, ticket, register)
                 if b is not None])
    # Both halves, as everywhere else that serves a signed-out reader: the
    # detail call is passed no user id so nothing is looked up against an
    # account, AND the block is not built without one. Either alone is a bug
    # waiting for the other to be edited.
    if user_id and d["your_shares"]:
        blocks.append({"h2": "Your position", "own": 1,
                       "bal": [["Shares you hold", f"{d['your_shares']:,.0f}", ""],
                               ["At the current price",
                                f"{d['your_shares'] * price:,.0f}c",
                                "what the register says it is worth today"]],
                       "n": "Value at the quoted price. What you paid is on Stocks."})

    asof = (f"{d['name']} · {d['grade']} · {shares:,.0f} shares listed, "
            f"{d['holders']} holder{'' if d['holders'] == 1 else 's'}.")
    out = _shell("stocks", asof, band, blocks)
    out["title"] = d["name"]
    return out


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
    # Work and Orders are ONE PAGE. Same table, two sides of it: what can I
    # claim, and what did I commit. The design already says so - Orders hangs off
    # Work as a child, not a sibling - and as two pages you scrolled one list to
    # size a job and another to see who took it. These blocks carry `own:1`, so
    # a worker who posts nothing sees the page he saw before.
    blocks = [table] + _order_blocks(user_id)
    return _shell("work", f"{len(rows)} open job{'' if len(rows) == 1 else 's'}.",
                  band, blocks)


# ── Claims — the LAND auction ───────────────────────────────────────────────
def lands(user_id: str = "", csrf: str = "") -> dict:
    """Land auctions. The item auction is a different page (`auctions`).

    `land_listings` holds both and separates them by `kind`. They are different
    things to bid on and different things to think about — a claim is ground with
    whatever is built on it, priced in chunks — so they get a page each rather
    than one table where a stack of diamonds sits above a 2,000-chunk claim.
    """
    if abex_live is None:
        return _empty("lands", "Estates are not reachable from this process.")
    rows = abex_live.parcels("land")
    if rows is None:
        return _empty("lands", "Land auctions are not readable right now.")

    out = [[name, owner or DASH, price, state, note or ""]
           for name, owner, _tenant, price, state, note in rows]
    live = sum(1 for r in rows if str(r[4]).lower() in ("active", "open"))
    band = [("Land lots", str(len(rows)), "on the register"),
            ("Live now", str(live), "open for bidding"),
            ("Sellers", str(len({r[1] for r in rows})), "with land listed"),
            ("Rent", "none", "a claim is bought outright")]
    # "Chunks", not "Size": §4 size-scales the CHUNK COUNT column, and the
    # renderer keys that ramp off the heading. A column called something else is
    # a column that silently loses it.
    table = {"h2": "Land auctions", "ac": 1,
             "c": ["Claim", "Seller", "Price#", "State", "Chunks#"], "r": out,
             "n": ("A claim is bought outright and transfers with whatever is "
                   "built on it — there is no recurring rent. Items are auctioned "
                   "separately, under Auctions."
                   if out else "No land is listed. Items are auctioned separately, "
                   "under Auctions.")}
    blocks = [table] + _bid_blocks("lands", str(user_id), csrf)
    return _shell("lands", f"{len(rows)} land lot{'' if len(rows) == 1 else 's'} "
                  "on the register.", band, blocks)


# ── Exchange ────────────────────────────────────────────────────────────────
def exchange(user_id: str = "") -> dict:
    """The share side: every LISTED market, free float and price.

    Free float here is shares in someone else's hands - the register minus the
    owner's own holding. `abex_live.exchange` already makes that distinction, and
    it matters: counting the owner has GreyHames reading 93% free float while one
    account holds 92,863 of its 100,000 shares.
    """
    if abex_live is None:
        return _empty("exchange", "The exchange is not reachable from this process.")
    data = abex_live.exchange()
    if data is None:
        return _empty("exchange", "Listings are not readable right now.")

    rows = data.get("rows", [])
    held = {}
    live = abex_live.stocks(str(user_id)) if user_id else None
    for r in (live or {}).get("rows", []):
        held[r[1]] = r[3]             # NAME -> shares

    out = []
    # The market name is the way into its own page. §1 reserves the accent for
    # things you can click, and `A|` is what spends it — a listed market's name
    # is now the one clickable thing in its row.
    try:
        ids = {(m or {}).get("name"): k
               for k, m in (abex_live._db().get_markets() or {}).items()}
    except Exception:
        ids = {}
    for ticker, name, grade, shares_out, holders, price, free in rows:
        mid = ids.get(name)
        cell = f"A|/hub/stocks/{mid}|{name}" if mid else name
        out.append([cell, ticker, "G|" + str(grade), price, shares_out,
                    holders, free, held.get(name, DASH)])

    listed = len(rows)
    band = [("Listed markets", str(listed), "shares you can trade"),
            ("Your positions", str(len(held)), "markets you hold"),
            ("Holders", str(sum(int(str(r[4]).replace(",", "") or 0) for r in rows)),
             "share accounts on the register"),
            ("Dividends", "none paid yet", "no market has declared one")]
    # §5: the rows this reader holds are flagged, and only while they are the
    # minority of the table - `_table` enforces that half. A wash on most of the
    # rows is a zebra stripe, not a flag.
    held_rows = [i for i, r in enumerate(out) if r[7] != DASH]
    index = _spark_block(
        "The index", abex_live.index_series(30),
        unit="", src="/api/series/index?days=30",
        note=("The index is written every five minutes whether or not anything "
              "moved, so a flat stretch is a real flat stretch — nothing traded "
              "— and not a gap in the record."))
    table = {"h2": "Listed markets", "ac": 1,
             "c": ["Market", "Ticker", "Grade", "Share price#", "Shares out#",
                   "Holders#", "Free float#", "You hold#"],
             "r": out, "mine": held_rows,
             "n": ("Free float counts shares in someone else's hands - the "
                   "register minus the owner's own holding."
                   if out else "No market is listed.")}
    blocks = [b for b in (index, table) if b is not None]
    return _shell("exchange", f"{listed} market{'' if listed == 1 else 's'} listed.",
                  band, blocks)


# ── My market, and the report it files ──────────────────────────────────────
def _coin(n) -> str:
    return f"{float(n or 0):,.0f}c"


def _no_market(key: str, owns_none: bool) -> dict:
    """The owner screens for somebody who owns no market.

    Not an error, and not an empty table either. Most players own nothing; the
    page says so in a sentence rather than showing five headed tables with no
    rows, which reads as breakage.
    """
    why = ("You do not own a market. These pages are the owner's console — the "
           "ledger, the payout order and the report — and they appear when a "
           "market is registered to your account."
           if owns_none else "That market is not yours.")
    return _empty(key, why)


def market(user_id: str = "") -> dict:
    """The owner's console: his ledger, where the net goes, and what he owes.

    THE WATERFALL'S ORDER IS THE SPEC'S (§6.3) AND ITS FIGURES ARE THE
    DATABASE'S. Net, then vault retention, then debt service and coupons, then
    dividends, then the owner's residual — in that order, always, because the
    order is the rule. What this will not do is fill the middle rows with
    plausible numbers: no bond has been issued and no dividend has ever been
    declared in this database, so those two lines read 0c and say why. A payout
    page that invents a coupon is a page that tells an owner he owes money to
    nobody.
    """
    if abex_live is None:
        return _empty("market", "The exchange is not reachable from this process.")
    data = abex_live.my_market(str(user_id))
    if data is None:
        return _empty("market", "Your market is not readable right now.")
    if not data.get("owns"):
        return _no_market("market", True)
    if "market_id" not in data:
        return _no_market("market", False)

    net = float(data["net"])
    retention = net * float(data["retention_pct"]) / 100.0 if net > 0 else 0.0
    vault_due = float(data["vault_due"])
    residual = net - retention

    band = [
        ("Grade", data["grade"],
         (f"{data['backing']:,.2f}× backed" if data["backing"] else "not scored")),
        (f"Net, {data['month_name']}", _coin(net),
         (f"{_coin(data['prev_net'])} in {data['prev_month_name']}"
          if data["prev_net"] else "no prior month on record"),
         "g" if net >= float(data["prev_net"] or 0) else "l"),
        ("Share price",
         (f"{data['share_price']:,.2f}c" if data.get("share_price") else "not listed"),
         (f"{data['shares_out']:,.0f} shares out" if data.get("shares_out")
          else "no shares issued")),
        ("Vault owed", _coin(vault_due),
         f"{data['retention_pct']:,.0f}% of each closed month"),
    ]

    entries = data["ledger"]
    ledger = {"h2": f"Ledger, {data['month_name'].split()[0]}", "ac": 1,
              "c": _cols("market", 1) or ["Date", "Entry", "Category", "In#", "Out#"],
              "r": [[d, e, c, ("g|" + i if i else DASH), ("l|" + o if o else DASH)]
                    for d, e, c, i, o in entries],
              "n": (f"{len(entries)} most recent entries this month, newest first. "
                    "Categories are the two this ledger records — a sale to a "
                    "customer, and stock bought in."
                    if entries else "No entries recorded this month.")}

    month_bal = {"h2": f"{data['month_name'].split()[0]} so far",
                 "bal": [["Revenue", _coin(data["income"]), ""],
                         ["Less stock and costs", _coin(data["spent"]), ""]],
                 "tot": ["Net for the month", _coin(net)],
                 "n": "Worker pay is not in this ledger — it is paid through the "
                      "team log and is shown under Staff."}

    waterfall = {"h2": "Where the net goes", "own": 1,
                 "bal": [
                     ["Net for the month", _coin(net), ""],
                     [f"Less vault, {data['retention_pct']:,.0f}% retained",
                      _coin(retention),
                      (f"{_coin(vault_due)} already accrued and unpaid"
                       if vault_due else "no arrears")],
                     ["Less debt service and bond coupons", "0c",
                      "no bond issued and no loan drawn against this market"],
                     ["Less dividends to shareholders", "0c",
                      "no dividend has been declared"],
                 ],
                 "tot": ["To the owner", _coin(residual)],
                 "n": "The order is fixed: vault first, then debt and coupons, "
                      "then dividends, then you."}

    liabilities = []
    if vault_due:
        liabilities.append(["Vault retention owed", "Abex Tech", _coin(vault_due),
                            DASH,
                            "m|accrued from closed months, arrears cap the grade at BBB"])
    liab = {"h2": "Liabilities", "own": 1,
            "c": _cols("market", 4) or ["Item", "Held by", "Amount#", "Due", "Note"],
            "r": liabilities,
            "n": ("The only liability on record. No bond has been issued against "
                  "this market and no loan is drawn."
                  if liabilities else "Nothing owed: no vault arrears, no bond, "
                  "no loan.")}

    staff_rows = [[w, role, filled, paid, DASH]
                  for w, role, filled, paid in data["staff"]]
    staff = {"h2": "Staff", "own": 1,
             "c": _cols("market", 5) or ["Worker", "Role", "Orders filled#",
                                         "Paid this month#", "Owed#"],
             "r": staff_rows,
             "n": ("Paid is what the team log recorded this month. Owed is blank "
                   "because nothing in this schema records an unpaid worker "
                   "balance — a figure here would be a guess about somebody's wages."
                   if staff_rows else "No workers on your team.")}

    asof = (f"{data['name']} · you are the owner · "
            + (f"listed at {data['share_price']:,.2f}c a share"
               if data.get("share_price") else "not listed on the exchange"))
    # HIS OWN STOCK, ON HIS OWN CONSOLE. Inventory was built for a market's
    # public page and never put here, so the one person who most needs to see
    # what is on the shelves — the owner — had a console with a ledger, a
    # waterfall and no goods on it. Same block, same "counted / not counted"
    # flag, because the rating reads the same rows.
    mid = str(data["market_id"])
    listed = bool(data.get("share_price"))
    shelves = [b for b in (_item_block(mid, listed, True),) if b is not None]
    shelves += [b for b in _shop_blocks(mid, data["name"], listed, True)
                # The ledger, the team and the liabilities are already on this
                # console, in the owner's own form. Only the shelves are new.
                if str(b.get("h2") or "").startswith("On the shelves")]
    screen_d = _shell("market", asof, band,
                      shelves + [ledger, month_bal, waterfall, liab, staff])
    screen_d["title"] = data["name"]
    return screen_d


def filing(user_id: str = "") -> dict:
    """The report this owner would file for the month.

    The share-price block comes from `abex_live.price_formula`, which asks the
    bot's own pricing function rather than restating the formula. When that is
    unreachable the block says so and shows nothing — an unpriced share is a
    thing this page can admit to.
    """
    if abex_live is None:
        return _empty("filing", "The exchange is not reachable from this process.")
    data = abex_live.filing(str(user_id))
    if data is None:
        return _empty("filing", "Your report is not readable right now.")
    if not data.get("owns"):
        return _no_market("filing", True)
    if "market_id" not in data:
        return _no_market("filing", False)

    net = float(data["net"])
    retention = net * float(data["retention_pct"]) / 100.0 if net > 0 else 0.0
    residual = net - retention
    month_word = data["month_name"].split()[0]

    band = [(f"Net for {month_word}", _coin(net),
             "revenue less stock and costs"),
            ("Share price",
             (f"{data['share_price']:,.2f}c" if data.get("share_price")
              else "not listed"),
             "the exchange's current price"),
            ("Grade", data["grade"],
             (f"{data['backing']:,.2f}× backed" if data["backing"] else "not scored"))]

    # A month can already have a filed figure while the sources have moved on —
    # a shop keeps trading after its owner files. Saying so is the point of the
    # screen: the gap between what stands on the record and what the ledger now
    # holds is exactly what refiling would change.
    filed = data.get("filed_net")
    if filed is None:
        stands = f"Nothing is filed for {month_word} yet."
    elif abs(filed - net) >= 1:
        stands = (f"{_coin(filed)} stands filed for {month_word}; the ledger now "
                  f"holds {_coin(net)}. Refiling replaces the figure on record.")
    else:
        stands = f"{_coin(filed)} stands filed for {month_word}, and the ledger agrees."
    action = {"h2": "File the report", "ac": 1, "own": 1,
              "act": ("Filing settles the share price, re-scores the grade and "
                      "closes the month. Reports are filed from Discord — this "
                      "page shows what would be filed."),
              "btns": [],
              "n": stands + " A missed filing keeps the last price, pays no "
                   "dividend and drops a band."}

    figures = {"h2": "The figures you are filing",
               "bal": [["Revenue", _coin(data["income"]), ""],
                       ["Less stock and costs", _coin(data["spent"]), ""]],
               "tot": ["Net for the month", _coin(net)]}

    price_rows = data.get("price_rows") or []
    price = {"h2": "How the price is set",
             "bal": [[label, value, ""] for label, value, _tone in price_rows],
             "n": ("Straight from the pricing function the bot quotes, so this "
                   "page and /stock price cannot disagree."
                   if price_rows else
                   "The pricing function is not reachable from this process, so "
                   "no derivation is shown. It is not being estimated here.")}

    pays = {"h2": "What filing pays", "own": 1,
            "bal": [["Net for the month", _coin(net), ""],
                    [f"Less vault, {data['retention_pct']:,.0f}% retained",
                     _coin(retention),
                     (f"{_coin(data['vault_due'])} already accrued"
                      if data["vault_due"] else "no arrears")],
                    ["Less debt service and bond coupons", "0c",
                     "nothing issued against this market"],
                    ["Less dividend", "0c",
                     ("last paid " + data["last_dividend"][0]
                      if data.get("last_dividend") else "none has ever been declared")]],
            "tot": ["To the owner", _coin(residual)]}

    hist_rows = [[m, DASH, n, DASH, DASH, DASH]
                 for m, _inc, _sp, n in (data.get("history") or [])[:3]]
    history = {"h2": "Last three filings",
               "c": _cols("filing", 4) or ["Month", "Filed", "Net#",
                                           "Price after#", "Dividend a share#",
                                           "Grade"],
               "r": hist_rows,
               "n": ("Net is the filed figure. Filing date, the price it set and "
                     "the grade it scored are not kept per month — the price log "
                     "records trades, not reports — so those cells are blank "
                     "rather than reconstructed."
                     if hist_rows else "Nothing filed yet.")}

    asof = f"{month_word} report · {data['name']}"
    screen_d = _shell("filing", asof, band,
                      [action, figures, price, pays, history])
    screen_d["title"] = f"{month_word} report, {data['name']}"
    return screen_d


def _spark_block(heading: str, series, unit: str = "c", note: str = "",
                 src: str = "") -> dict | None:
    """A price-line block, or None when there is nothing truthful to draw.

    None on an unreadable log, because a missing chart is quieter than a chart
    of nothing. A series of one point still returns a block: `_spark` renders it
    as a sentence saying one reading is not a trend, which is worth saying — the
    reader can see the market exists and has simply never moved.
    """
    if not series:
        return None
    spark = {"points": series.get("points") or [], "unit": unit,
             "window": series.get("window") or "", "src": src, "note": note}
    # Carried through so the chart can mark trades, name what moved each point
    # on hover, and open on the timeframe it was actually served.
    for key in ("at", "why", "marks", "trades", "days"):
        if series.get(key) is not None:
            spark[key] = series[key]
    return {"h2": heading, "spark": spark}


# ── Orders — the owner's half of Work, on the same page ─────────────────────
def _order_blocks(user_id: str = "") -> list:
    """The poster's read of the order table, as blocks for the Work screen.

    Work and Orders are ONE PAGE. They are the same table read from two sides —
    what can I claim, and what did I commit — and the design already says so by
    hanging Orders off Work as a child rather than a sibling. Two pages meant
    scrolling one list to size a job and another to see who took it.

    Owner blocks are filtered to markets this account owns. Without that filter
    every reader saw every order twice: once as work to claim, once as if he had
    posted it.
    """
    if abex_live is None:
        return []
    try:
        db = abex_live._db()
        raw = db.load_orders() or []
    except Exception as exc:
        log.warning("[livescreens] orders unreadable: %s", exc)
        return []
    try:
        owned = {m["market_id"] for m in abex_live.owned_markets(str(user_id))}
    except Exception:
        owned = set()
    if not owned:
        return []
    raw = [o for o in raw if str(o.get("market_id") or "") in owned]
    if not raw:
        return []

    try:
        registry = db.get_markets() or {}
    except Exception:
        registry = {}

    # PAY COMES FROM THE BOT'S OWN RATE FUNCTION, not from `coin_per_piece`.
    # That column is NULL on real orders - the rate is derived from the item
    # book - so reading it directly printed an em dash on Orders while Work,
    # which asks `_coin_rates_for_order`, printed 100.00c a piece for the same
    # order. Two order lists disagreeing about pay is the one thing this screen
    # must not do; a worker sizes a job by that number.
    core = items_data = None
    try:
        core = abex_live._core()
        items_data = core._load_items()
    except Exception as exc:
        log.warning("[livescreens] order rates unavailable, pay will be blank: %s", exc)

    def _rate_and_total(o):
        if core is None:
            return None, None
        try:
            piece = core._coin_rates_for_order(o, items_data)[0]
            total = core._coins_for_pieces(o, int(o.get("requested") or 0), items_data)
            return float(piece), float(total)
        except Exception:
            return None, None

    open_rows, filled = [], []
    committed = 0.0
    for o in raw:
        status = str(o.get("status") or "").lower()
        item = str(o.get("item") or "")
        mid = str(o.get("market_id") or o.get("shop") or "")
        market = str((registry.get(mid) or {}).get("name") or mid) or DASH
        # `requested` IS IN PIECES AND `amount` IS IN THE STATED UNIT. Printing
        # `requested` next to `unit_type` reads 6,912 stacks for an order of 108,
        # which is the same figure out by a factor of 64 - and this column is what
        # a worker sizes a job by. The quantity shown is the one the order was
        # written in; pay is per piece, so the total multiplies by pieces.
        pieces = int(o.get("requested") or 0)
        shown = int(o.get("amount") or pieces)
        unit = str(o.get("unit_type") or "pieces")
        rate, total = _rate_and_total(o)
        if rate is None:
            rate = float(o.get("coin_per_piece") or 0) or None
            total = rate * pieces if rate else None
        claims = o.get("claims") or []
        who = ", ".join(str(c.get("user_tag") or "") for c in claims if c.get("user_tag"))
        stack = int(o.get("stack_size") or 64)
        stackable = bool(o.get("stackable"))
        # Quoted the way every price in this economy is quoted - per piece, and
        # per stack of 64 when the item stacks. Never per barrel: that rate is
        # 3,456 pieces and printing it under "per stack" is a 54x overstatement.
        if rate and stackable:
            pay = f"{rate * stack:,.2f}c per stack of {stack} · {rate:,.2f}c a piece"
        elif rate:
            pay = f"{rate:,.2f}c per piece"
        else:
            pay = DASH
        if status == "open":
            committed += float(total or 0)
            open_rows.append([
                item, market, f"{shown:,} {unit}", pay,
                (f"{total:,.0f}c" if total else DASH),
                (who or "m|unclaimed"),
                ("w|claimed" if claims else "g|open"),
            ])
        elif claims:
            for c in claims:
                qty = int(c.get("qty") or 0)
                filled.append([
                    str(c.get("claimed_at") or "")[:10] or DASH, item, market,
                    str(c.get("user_tag") or DASH),
                    f"{qty:,} piece{'' if qty == 1 else 's'}",
                    (f"g|{rate * qty:,.0f}c" if rate else DASH),
                ])
    filled.sort(key=lambda r: str(r[0]), reverse=True)
    filled = filled[:12]

    a = {"h2": "Orders you posted", "own": 1,
         "c": _cols("orders", 0) or ["Item", "Market", "Quantity", "Pay#", "Total#",
                                     "Claimed by", "Status"],
         "r": open_rows,
         "n": (f"{len(open_rows)} open, {committed:,.0f}c committed. Pay is per "
               "piece unless the order says per stack; a stack is 64."
               if open_rows else "You have no open orders.")}
    b = {"h2": "Filled this week", "own": 1,
         "c": _cols("orders", 1) or ["Filled", "Item", "Market", "Worker",
                                     "Quantity", "Paid#"],
         "r": filled,
         "n": ("Paid is the order's rate against the quantity claimed. What was "
               "actually transferred is in History."
               if filled else "Nothing filled on record.")}
    act = {"h2": "Posting work", "own": 1,
           "act": ("Orders are posted and approved from Discord. A new order is "
                   "employee-only for its first 45 minutes, then open to all."),
           "btns": [],
           "n": "Claims are approved on the order card, not here."}
    return [a, b, act]


def _closes(ends_at) -> str:
    """A `T|<seconds>` countdown cell, or an em dash for a lot with no close.

    A timestamp printed once is a clock that stops. On an auction board that is
    not a cosmetic problem: a bidder reads "2026-08-25 19:00" and has to work out
    what it means now, or reads a cached page and bids on a lot that shut. §5
    has the renderer emit a live cell and the page tick it; this is what feeds
    it. Seconds, because the cell counts down from whenever it was served.
    """
    if not ends_at:
        return DASH
    from datetime import datetime, timezone
    try:
        when = datetime.fromisoformat(str(ends_at).replace("Z", "+00:00"))
    except ValueError:
        return DASH
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    left = int((when - datetime.now(timezone.utc)).total_seconds())
    return "T|%d" % max(0, left)


def _bid_blocks(kind: str, user_id: str, csrf: str) -> list:
    """A bid box per open lot, on the designed page.

    This is what retires `/auctions` and `/lands` as separate places to act. The
    older pages own the bidding flow and the designed ones could only link to
    them, so the site had a page to read a lot on and a different page to bid on
    it — the /canvas split again, one level down.

    The FORM KEY is minted here, bound to this user and this lot, exactly as
    `estates_web._lots` mints it: `money_post` checks the key against the thing
    the request is about, so a key from another lot is refused rather than
    quietly spent.
    """
    if not (user_id and csrf) or abex_live is None:
        return []
    try:
        import estates_web
        import vt_web_shell as shell
        db = abex_live._db()
        want = "land" if kind == "lands" else "item"
        lots = [l for l in (db.get_active_land_listings() or [])
                if str(l.get("kind") or "item") == want
                and str(l.get("mode") or "") == "auction"]
    except Exception as exc:
        log.warning("[livescreens] bid boxes unavailable: %s", exc)
        return []

    out = []
    for lot in lots[:12]:
        lid = int(lot.get("id") or 0)
        if str(lot.get("seller_id") or "") == str(user_id):
            continue                      # a seller cannot bid on his own lot
        try:
            minimum = int(estates_web._min_next_bid(lot))
            key = shell.mint_form_key(str(user_id), f"bid:{lid}")
        except Exception:
            continue
        title = str(lot.get("title") or f"Lot #{lid}")
        out.append({"h2": f"Bid on {title}", "bid": {
            "lot_id": lid, "minimum": minimum, "key": key, "csrf": csrf,
            "title": title,
            "hint": (f"{minimum:,}c or more. A bid is a HOLD — the coins stay "
                     "yours, reserved so they cannot be spent twice, and are "
                     "released the moment somebody outbids you.")}})
    return out


# ── Auctions ────────────────────────────────────────────────────────────────
def auctions(user_id: str = "", csrf: str = "") -> dict:
    """ITEM auctions — live lots and your bids. Land is a different page.

    `land_listings` carries both kinds; this one takes `kind='item'`. Showing
    both put goods and ground in one table under one price column, which reads
    as one market and is two.

    A BID IS A HOLD, NOT A DEBIT — the coins stay yours until a lot settles, and
    that is the one thing every screen showing a bid has to say rather than imply.
    The balance block says it; so does the note.
    """
    if abex_live is None:
        return _empty("auctions", "The exchange is not reachable from this process.")
    try:
        db = abex_live._db()
        lots = [l for l in (db.get_active_land_listings() or [])
                if str(l.get("kind") or "item") == "item"]
    except Exception as exc:
        log.warning("[livescreens] lots unreadable: %s", exc)
        return _empty("auctions", "The auction exchange is not answering.")

    uid = str(user_id or "")
    rows, mine, held = [], [], 0.0
    for lot in lots:
        lid = int(lot.get("id") or 0)
        title = str(lot.get("title") or f"Lot #{lid}")
        seller = abex_live._owner_name(db, lot.get("seller_id"))
        top = float(lot.get("current_bid") or lot.get("reserve") or 0)
        leader = str(lot.get("current_bidder") or "")
        try:
            bids = db.get_land_bids(lid) or []
        except Exception:
            bids = []
        yours = max((float(b.get("amount") or 0) for b in bids
                     if str(b.get("bidder_id") or "") == uid), default=0.0)
        if yours:
            held += yours
            mine.append([("Leading, " if leader == uid else "Outbid, ") + title,
                         f"{yours:,.0f}c",
                         "held until the lot closes"])
        if leader == uid:
            position = "g|You lead"
        elif yours:
            position = "l|Outbid"
        else:
            position = "m|no bid"
        rows.append([title, seller, f"{top:,.0f}c",
                     (f"{yours:,.0f}c" if yours else DASH), str(len(bids)),
                     _closes(lot.get("ends_at")), position])

    band = [("Item lots", str(len(rows)), "open for bidding"),
            ("Held in bids", f"{held:,.0f}c", "released when a lot closes"),
            ("Your bids", str(len(mine)), "lots you are in"),
            ("Sellers", str(len({r[1] for r in rows})), "with a lot open")]

    table = {"h2": "Live lots", "ac": 1,
             "c": _cols("auctions", 0) or ["Lot", "Seller", "Current bid#",
                                           "Your bid#", "Bids#", "Closes",
                                           "Your position"],
             "r": rows, "mine": [i for i, r in enumerate(rows) if r[3] != DASH],
             "n": ("A bid is held from your wallet until the lot closes — the "
                   "coins stay yours until a lot settles. Land is auctioned "
                   "separately, under Claims."
                   if rows else "No item lots are open. Land is auctioned "
                   "separately, under Claims.")}
    blocks = [table]
    if mine:
        blocks.append({"h2": "Your bids", "bal": mine,
                       "tot": ["Held in bids", f"{held:,.0f}c"],
                       "n": "Held, not spent."})
    blocks += _bid_blocks("auctions", str(user_id), csrf)
    return _shell("auctions", f"{len(rows)} item lot"
                  f"{'' if len(rows) == 1 else 's'} live.", band, blocks)


# ── Messages ────────────────────────────────────────────────────────────────
def _reply_blocks(user_id: str, csrf: str, threads: list) -> list:
    """A reply box per conversation, newest first, unread ones first.

    THE KEY IS RESUMED, NOT MINTED, when the last send has not come back from the
    write. `messages_web._resume_key` hands back the same key with the reason in
    words; minting a fresh one would produce a key the claim table has never
    seen, and the whole point of the claim is that the retry collides with it.

    Capped at eight boxes. Every box costs a key row, and a player with sixty
    threads does not want sixty textareas on one screen — the messenger is still
    there for the long tail, and the note says which threads are shown.
    """
    if not (user_id and csrf and threads):
        return []
    try:
        import messages_web as MW
    except Exception as exc:                          # pragma: no cover
        log.warning("[livescreens] messages module unavailable: %s", exc)
        return []

    ordered = sorted(threads, key=lambda t: (0 if int(t.get("unread") or 0) else 1))
    boxes = []
    for t in ordered[:8]:
        tid = int(t.get("id") or 0)
        if not tid:
            continue
        try:
            key, note = MW._resume_key(str(user_id), f"message:t:{tid}")
        except Exception as exc:
            log.warning("[livescreens] no message key for thread %s: %s", tid, exc)
            continue
        if not key:
            continue
        other = str(t.get("other_name") or "this conversation")
        unread = int(t.get("unread") or 0)
        boxes.append({"thread_id": tid, "key": str(key), "csrf": csrf,
                      "label": f"Reply to {other}",
                      "newest": int(t.get("last_message_id") or 0),
                      "unread": unread,
                      "max": int(getattr(MW, "BODY_MAX", 2000)),
                      "placeholder": f"Write to {other}…",
                      "hint": note or (f"{unread} unread in this thread."
                                       if unread else
                                       "Sent as you, from this page.")})
    if not boxes:
        return []
    shown = len(boxes)
    return [{"h2": "Reply", "reply": boxes,
             "n": (f"The {shown} most recent conversation"
                   f"{'' if shown == 1 else 's'}, unread first. Sending happens "
                   f"here — there is no second page to open, and no second copy "
                   f"of what you are replying to.")}]


def messages(user_id: str = "", csrf: str = "") -> dict:
    """Unread and earlier, sender and subject only.

    The "subject" is the newest message's first line, because these threads have
    no subject field. That is the honest rendering of a chat thread in a table
    the design drew for mail — it is a preview, and the note says so.
    """
    uid = str(user_id or "")
    if not uid:
        return _empty("messages", "Sign in to read your messages.")
    try:
        import messages_web as MW
        threads = MW._threads_for(uid)
    except Exception as exc:
        log.warning("[livescreens] messages unreadable: %s", exc)
        return _empty("messages", "Messages are not readable right now.")

    unread, earlier = [], []
    for t in threads:
        body = str(t.get("last_body") or "").strip().replace("\n", " ")
        preview = (body[:90] + "…") if len(body) > 90 else (body or "no messages yet")
        try:
            when = MW._stamp(t.get("last_message_at"))
        except Exception:
            when = DASH
        # The sender's name IS the way into the conversation. The reply box
        # below answers a thread; reading what was said before it is the one
        # thing this screen genuinely cannot show, so the row links to it rather
        # than a button somewhere else offering "the messenger".
        who = str(t.get("other_name") or DASH)
        tid = int(t.get("id") or 0)
        row = [(f"A|/messages/t/{tid}|{who}" if tid else who), preview, when or DASH]
        (unread if int(t.get("unread") or 0) else earlier).append(row)

    total_unread = sum(1 for t in threads if int(t.get("unread") or 0))
    a = {"h2": "Unread", "ac": 1,
         "c": _cols("messages", 0) or ["From", "Subject", "Received"], "r": unread,
         "n": (f"{len(unread)} thread{'' if len(unread) == 1 else 's'} with "
               "something you have not read, newest first. The subject is the "
               "newest message — these are threads, not mail, and they carry no "
               "subject line." if unread else "Nothing unread.")}
    b = {"h2": "Earlier",
         "c": _cols("messages", 1) or ["From", "Subject", "Received"], "r": earlier,
         "n": (f"{len(earlier)} thread{'' if len(earlier) == 1 else 's'}, newest "
               "first." if earlier else "No earlier threads.")}
    # REPLYING HAPPENS HERE. "Open the messenger" was the last button on the site
    # that answered a question by sending somebody somewhere else, and a second
    # page meant a second copy of the thread being answered.
    reply = _reply_blocks(uid, csrf, threads)
    if not reply:
        reply = [{"h2": "Reply", "ac": 1,
                  "act": ("There is nothing to reply to yet. A conversation "
                          "starts when somebody writes to you, or from a player's "
                          "own page."),
                  "btns": [],
                  "n": "Replies are written on this page once a thread exists."}]
    head = dict(reply[0])
    head["ac"] = 1
    reply[0] = head
    asof = (f"{total_unread} unread." if total_unread else "Nothing unread.")
    return _shell("messages", asof, None, reply + [a, b])


# ── History ─────────────────────────────────────────────────────────────────
def history(user_id: str = "") -> dict:
    """Your wallet, as the ledger recorded it.

    `balance_after` IS READ, NEVER RECOMPUTED, and this screen inherits that from
    `history_web.read_coin_ledger` rather than doing its own arithmetic: on the
    production copy a fifth of the checkable rows disagree with
    previous-balance-plus-delta, because movements were written outside the coin
    ledger. Recomputing would print balances the bot never wrote.
    """
    uid = str(user_id or "")
    if not uid:
        return _empty("history", "Sign in to see your history.")
    try:
        import history_web as HW
        entries = HW.read_coin_ledger(uid)
    except Exception as exc:
        log.warning("[livescreens] history unreadable: %s", exc)
        return _empty("history", "Your history is not readable right now.")

    import time as _t
    month_start = _t.time() - 30 * 86400
    week_start = _t.time() - 7 * 86400
    money_in = money_out = 0.0
    month_count = 0
    rows = []
    for e in entries:
        at = e.get("event_at")
        delta = float(e.get("coin_delta") or 0)
        if at and at >= month_start:
            month_count += 1
            if delta >= 0:
                money_in += delta
            else:
                money_out += -delta
        if at and at < week_start and len(rows) >= 8:
            continue
        if len(rows) >= 25:
            continue
        try:
            when = HW._date(at)
        except Exception:
            when = DASH
        # Counterparty, honestly. `coin_ledger` stores a reason string, not a
        # party, so the only counterparty it can name is the market a reason
        # mentions. Everything else is an em dash rather than the entry's own
        # detail text wearing the Counterparty heading.
        mid = str(e.get("market_id") or "")
        try:
            other = HW.market_name(mid) if mid else ""
        except Exception:
            other = mid
        head = str(e.get("headline") or DASH)
        detail = str(e.get("detail_text") or "")
        rows.append([when or DASH, (f"{head} · {detail}" if detail else head),
                     other or DASH,
                     ("g|%s c" % f"{delta:,.2f}" if delta > 0 else DASH),
                     ("l|%s c" % f"{-delta:,.2f}" if delta < 0 else DASH)])

    band = [("Entries, last 30 days", str(month_count),
             f"{len(entries)} on record"),
            ("Money in", f"{money_in:,.0f}c", "last 30 days", "g"),
            ("Money out", f"{money_out:,.0f}c", "last 30 days", "l")]
    table = {"h2": "Recent", "ac": 1,
             "c": _cols("history", 0) or ["Date", "Entry", "Counterparty",
                                          "In#", "Out#"],
             "r": rows,
             "n": (f"{len(rows)} of {len(entries)} entries, newest first. Balances "
                   "are the figures the ledger stored, never recomputed here."
                   if rows else "No wallet movements on record.")}
    act = {"h2": "The full record",
           "act": ("This is the wallet ledger. The full history also carries "
                   "exchange trades, dividends and settlements from their own "
                   "sources, each with the reason the bot stored."),
           "btns": [["Open the full history", "s", "/history"]],
           "n": "Nothing here is recomputed — every balance is the figure the "
                "ledger wrote."}
    return _shell("history", f"{month_count} entries in the last 30 days.",
                  band, [table, act])


# ── Banking ─────────────────────────────────────────────────────────────────

#: purpose -> the endpoint that carries it out. One table, so a box and its
#: commit route cannot drift apart the way the /banking copy and this one could.
_MONEY_URL = {
    "deposit": "/api/banking/deposit",
    "withdraw": "/api/banking/withdraw",
    "repay": "/api/banking/repay",
    "bond_buy": "/api/banking/bond/buy",
    "bond_redeem": "/api/banking/bond/redeem",
}


def _in_flight_note(action: str, flight: dict) -> str:
    """What a player is told about an instruction the bank has not answered.

    Not "try again". The key is still claimed, so a second press can only 409 —
    and the first instruction MAY HAVE BEEN APPLIED, which is exactly why it is
    closed rather than retryable. Nothing clears this automatically today, so it
    says so and names who can.
    """
    label = {"deposit": "A deposit", "withdraw": "A withdrawal",
             "repay": "A repayment", "bond_buy": "A bond purchase",
             "bond_redeem": "A redemption"}.get(action, "An instruction")
    age = int((flight or {}).get("age_seconds") or 0)
    when = ("%d minutes" % (age // 60)) if age >= 60 else "less than a minute"
    return (f"{label} you sent {when} ago has not been confirmed by the bank. It "
            f"may already have been applied, so the same confirmation key is "
            f"still held for it and it cannot be sent twice. Ask staff to settle "
            f"it against your bank record — nothing clears it automatically.")


def _bank_keys(user_id: str, acct: dict) -> tuple:
    """`(keys, in_flight)` for this player, minted ONCE per page render.

    Called once and shared, not once per block: `mint_form_key` issues a fresh
    key each time, so asking twice leaves one of the pair claimed and unused in
    `web_idempotency` — and the in-flight lookup would then find a key the
    browser was never given.
    """
    if not (user_id and acct):
        return {}, {}
    try:
        import banking_web
        return banking_web._keys_for(str(user_id), acct)
    except Exception as exc:
        log.warning("[livescreens] bank form keys unavailable: %s", exc)
        return {}, {}


def _money_boxes(user_id: str, csrf: str, acct: dict, available: float,
                 keys: dict, in_flight: dict) -> list:
    """Every bank instruction this player can give, on the page showing his money.

    THIS IS THE CENTRALISATION. `/banking` mints its keys at render time and
    hands them to its own script; so does this, from the same `_keys_for`, so
    there is one minting rule rather than two that must be kept in step. What is
    NOT duplicated is the arithmetic: no figure here is computed for the confirm
    screen. The preview endpoint re-reads the account when the button is pressed
    and returns the rows; this only carries the instruction and its key.

    A missing key is not an error to hide. `_keys_for` declines to mint for a
    subject it cannot sign unambiguously (an opaque bond id from the bank), and a
    box with no key would submit and be refused as `bad_form_key`. Those are
    dropped, and the block's note says a bond is missing rather than showing a
    button that cannot work.
    """
    if not (user_id and csrf and acct and keys):
        return []

    savings = acct.get("savings") or {}
    loan = acct.get("loan") or None
    principal = float(savings.get("balance") or 0)
    avail = int(available)

    def flight(action: str, subject: str = ""):
        f = in_flight.get(action) or {}
        if not f:
            return None
        subs = f.get("subjects") or {}
        if subject:
            return subs.get(str(subject))
        return subs.get("") or f

    def box(action, subject, title, cta, hint, cap=None, amount=True, extra=None,
            field="Amount", quiet=False):
        k = keys.get(action)
        key = k.get(str(subject)) if isinstance(k, dict) else k
        if not key:
            return None
        stuck = flight(action, str(subject) if isinstance(k, dict) else "")
        return {"action": action, "subject": subject, "url": _MONEY_URL[action],
                "key": str(key), "csrf": csrf, "title": title, "cta": cta,
                "hint": hint, "cap": cap, "amount": amount, "field": field,
                "quiet": quiet, "extra": extra or {},
                "stuck": _in_flight_note(action, stuck) if stuck else ""}

    out = []
    out.append(box("deposit", "", "Deposit into savings", "Deposit",
                   f"{avail:,}c available. Coins held by an open bid or order are "
                   f"not depositable — a hold reserves them, it does not spend them.",
                   cap=avail, field="Coins"))
    if principal > 0:
        out.append(box("withdraw", "", "Withdraw from savings", "Withdraw",
                       f"{principal:,.0f}c in savings. Interest accrued since the "
                       f"last credit is not forfeited by withdrawing today.",
                       cap=int(principal), field="Coins", quiet=True))
    if loan:
        payoff = float(loan.get("payoff_today") or 0)
        out.append(box("repay", "", f"Repay loan #{loan.get('id')}", "Pay",
                       f"{payoff:,.0f}c settles it in full today. Payment goes to "
                       f"interest first, then principal.",
                       cap=int(min(avail, payoff)), field="Coins"))
    return [b for b in out if b]


def _bond_blocks(user_id: str, csrf: str, acct: dict, available: float,
                 keys: dict, in_flight: dict) -> list:
    """The bond ladder and its two instructions, as blocks.

    A bond is the one bank product with a SUBJECT — which term, which bond — and
    a key that did not bind it once let a player who read one bond's figures
    redeem another. The key is minted per term and per bond id, and the server
    checks it against the id in the body, so the confirm screen and the
    instruction cannot be about different bonds.
    """
    if not (user_id and csrf and acct and keys):
        return []

    bonds = acct.get("bonds") or []
    terms = acct.get("bond_terms") or []
    avail = int(available)
    blocks = []

    if bonds:
        rows = []
        for b in bonds:
            matured = bool(b.get("matured"))
            rows.append([str(b.get("id") or DASH),
                         f"{float(b.get('face') or 0):,.0f}c",
                         f"{float(b.get('apr') or 0):,.2f}%",
                         str(b.get("matures") or "")[:10] or DASH,
                         ("matured" if matured else
                          f"{float(b.get('early_redemption_penalty') or 0):,.0f}c penalty"),
                         f"{float(b.get('redeem_value_today') or 0):,.0f}c"])
        blocks.append({"h2": "Your bonds",
                       "c": ["Bond", "Face#", "Rate#", "Matures",
                             "Redeem early", "Value today#"],
                       "r": rows,
                       "n": "Redeeming before maturity is allowed and the penalty "
                            "is the figure on the row — the confirm screen shows "
                            "what holding to maturity would have paid instead."})

    boxes = []
    for b in bonds:
        bid = str(b.get("id") or "")
        k = (keys.get("bond_redeem") or {})
        key = k.get(str(bid)) if isinstance(k, dict) else None
        if not key:
            continue
        stuck = ((in_flight.get("bond_redeem") or {}).get("subjects") or {}).get(str(bid))
        matured = bool(b.get("matured"))
        boxes.append({"action": "bond_redeem", "subject": bid,
                      "url": _MONEY_URL["bond_redeem"], "key": str(key),
                      "csrf": csrf, "title": f"Redeem bond {bid}",
                      "cta": ("Redeem " + bid) if matured else ("Redeem " + bid + " early"),
                      "amount": False, "quiet": not matured, "extra": {"bond_id": bid},
                      "hint": ("Matured — redeeming pays the full amount."
                               if matured else
                               f"Not matured until {str(b.get('matures') or '')[:10]}. "
                               f"Redeeming now gives up the interest still to run."),
                      "stuck": _in_flight_note("bond_redeem", stuck) if stuck else ""})
    for t in terms:
        term = int(t.get("term_days") or 0)
        k = (keys.get("bond_buy") or {})
        key = k.get(str(term)) if isinstance(k, dict) else None
        if not key:
            continue
        stuck = ((in_flight.get("bond_buy") or {}).get("subjects") or {}).get(str(term))
        lo = float(t.get("min_face") or 0)
        boxes.append({"action": "bond_buy", "subject": term,
                      "url": _MONEY_URL["bond_buy"], "key": str(key), "csrf": csrf,
                      "title": f"Buy a {term}-day bond at {float(t.get('apr') or 0):,.2f}%",
                      "cta": f"Buy {term}-day", "amount": True, "field": "Face value",
                      "cap": avail, "extra": {"term_days": term},
                      "hint": (f"{term} days at {float(t.get('apr') or 0):,.2f}% APR"
                               + (f", from {lo:,.0f}c" if lo else "")
                               + f". {avail:,}c available."),
                      "stuck": _in_flight_note("bond_buy", stuck) if stuck else ""})
    if boxes:
        blocks.append({"h2": "Bonds", "money": boxes,
                       "n": "A bond locks its face value for the term. The rate is "
                            "fixed when you buy."})
    return blocks


def banking(user_id: str = "", csrf: str = "") -> dict:
    """Wallet, savings, debt and the borrowing limit.

    "Unavailable" ON A BANKING PAGE READS AS "YOUR MONEY IS GONE". So the two
    halves are separated: the wallet comes from the ledger and is nearly always
    answerable, and the bank's own products come from the bank provider, which
    may genuinely not be deployed. A missing bank leaves the wallet standing and
    says the bank is not deployed — it does not take the page down.
    """
    uid = str(user_id or "")
    if not uid:
        return _empty("banking", "Sign in to see your accounts.")
    try:
        import hub_web
        snap = hub_web.money_snapshot(uid) or {}
    except Exception as exc:
        log.warning("[livescreens] wallet unreadable: %s", exc)
        return _empty("banking", "Your wallet is not readable right now.")
    if not snap.get("ledger_ok"):
        return _empty("banking", "The ledger is not answering, so no balance is "
                                 "shown. It is not being estimated.")

    available = float(snap.get("available") or 0)
    held = float(snap.get("held") or 0)
    balance = float(snap.get("balance") or 0)

    acct = {}
    bank_note = ""
    try:
        import bank_local
        got = bank_local.handle("GET", "/api/v1/account", {"user_id": uid}) or {}
        acct = got if got.get("ok") else {}
        bank_note = "" if acct else str(got.get("error") or "The bank is not deployed.")
    except Exception as exc:
        log.warning("[livescreens] bank provider unreadable: %s", exc)
        bank_note = "The bank is not reachable from this process."

    savings = acct.get("savings") or {}
    principal = float(savings.get("balance") or 0)
    loan = acct.get("loan") or None
    limit = acct.get("limit") or {}

    band = [("Available", f"{available:,.0f}c",
             f"{held:,.0f}c held in orders and bids"),
            ("Savings", (f"{principal:,.0f}c" if acct else "not deployed"),
             (f"{float(savings.get('accrued_this_month') or 0):,.0f}c interest this month"
              if acct else bank_note)),
            ("Debt", (f"{float(loan['outstanding']):,.0f}c" if loan else
                      ("nothing drawn" if acct else "not deployed")),
             ("one open loan" if loan else "no loan outstanding")),
            ("Available to borrow",
             (f"{float(limit.get('headroom') or 0):,.0f}c" if limit else DASH),
             (f"{float(limit.get('amount') or 0):,.0f}c limit" if limit
              else "the bank sets this"))]

    due = []
    if loan and loan.get("due"):
        due.append(["Loan repayment", f"l|{float(loan['outstanding']):,.0f}c",
                    str(loan.get("due") or "")[:10] or DASH,
                    "m|collections take savings and bond payouts after three "
                    "days, never your wallet"])
    waiting = {"h2": "Waiting on you", "ac": 1,
               "c": _cols("banking", 0) or ["What is due", "Amount#", "Due", "Note"],
               "r": due,
               "n": ("Missed payments take your savings and bond payouts after a "
                     "three-day grace. Never your wallet, and never your shares "
                     "or land." if due else "Nothing due.")}

    accounts = {"h2": "Accounts",
                "bal": [["Wallet available", f"{available:,.0f}c", ""],
                        ["Held in orders and bids", f"{held:,.0f}c",
                         "reserved, not spent"],
                        ["Savings principal",
                         (f"{principal:,.0f}c" if acct else "not deployed"), ""]],
                "tot": ["Cash and savings", f"{balance + principal:,.0f}c"],
                "n": "Held coins are still yours — a hold reserves, it does not "
                     "debit."}

    blocks = [waiting, accounts]
    if loan:
        blocks.append({"h2": "Debt",
                       "c": _cols("banking", 3) or ["Loan", "Drawn#", "Rate#",
                                                    "Repayment#", "Next payment",
                                                    "Payments left#"],
                       "r": [["Loan from the bank",
                              f"{float(loan.get('principal') or 0):,.0f}c",
                              f"{float(loan.get('apr') or 0):,.2f}%",
                              f"{float(loan.get('payoff_today') or 0):,.0f}c",
                              str(loan.get("due") or "")[:10] or DASH, DASH]],
                       "n": "Collections take savings and bond payouts, never the "
                            "wallet, and there is no seizure of shares or land."})
    components = limit.get("components") or []
    if components:
        blocks.append({"h2": "Credit limit",
                       "bal": [[str(label), f"{float(value):,.0f}c", ""]
                               for label, value in components],
                       "tot": ["Available to borrow",
                               f"{float(limit.get('headroom') or 0):,.0f}c"]})
    # THE INSTRUCTIONS LIVE HERE NOW, not behind a button to a second page.
    # "Read here, act there" was the old rule and it is the /canvas split in
    # miniature: two pages, two copies of the wallet, and the first time they
    # disagreed the one somebody confirmed was the stale one.
    _keys, _flight = _bank_keys(uid, acct) if csrf else ({}, {})
    boxes = _money_boxes(uid, csrf, acct, available, _keys, _flight)
    if boxes:
        blocks.append({"h2": "Moving money", "money": boxes,
                       "n": "Each of these is priced by the bank when you press "
                            "it, not when this page loaded, and you see those "
                            "figures before anything moves."})
    elif acct:
        blocks.append({"h2": "Moving money",
                       "act": ("Sign-in could not be confirmed for a money "
                               "instruction, so no button is offered. Reload the "
                               "page rather than acting anywhere else."),
                       "btns": [],
                       "n": "No coin moves from a page that cannot prove who is "
                            "asking."})
    else:
        blocks.append({"h2": "Moving money",
                       "act": ("The bank is not answering, so nothing can be "
                               "deposited, withdrawn or repaid right now. Your "
                               "wallet above is live and unaffected."),
                       "btns": [],
                       "n": bank_note or "The bank is not deployed."})
    blocks.extend(_bond_blocks(uid, csrf, acct, available, _keys, _flight))
    asof = ("Interest is paid weekly." if acct else
            "Your wallet is live. " + bank_note)
    return _shell("banking", asof, band, blocks)


#: key -> builder. A screen absent here has no live source yet and keeps its
#: shape from `abex_canvas` and nothing else - the design's sample rows are not
#: served anywhere any more.
BUILDERS = {
    "hub": hub, "markets": markets, "stocks": stocks, "work": work,
    "lands": lands, "exchange": exchange,
    "market": market, "filing": filing,
    "auctions": auctions, "messages": messages,
    "history": history, "banking": banking,
}


#: What a signed-out visitor may read AT ALL. Markets, their grades, the listed
#: share prices, the open work and the land register are public facts about the
#: economy - the same things a player can see in Discord without an account here.
#:
#: `stocks` is deliberately absent: that screen IS your positions, and with the
#: personal parts removed there is no page left to serve. Banking, Messages,
#: History, My market and the owner console are absent for the same reason.
PUBLIC = {"hub", "markets", "exchange", "work", "lands"}


def screen(key: str, user_id: str = "", public: bool = False,
           csrf: str = "") -> dict | None:
    """One screen. `public=True` builds it for a reader who is not signed in.

    Two independent halves, both needed. The build is passed NO user id, so
    nothing is ever looked up against an account - there is nothing personal in
    the result to leak even if the stripping were wrong. Then the result is
    stripped, so the page does not advertise columns the reader cannot fill.

    Returns None for a key that is not public, and the caller sends them to sign
    in. None here is "not for strangers", never "does not exist".
    """
    if public and key not in PUBLIC:
        return None
    fn = BUILDERS.get(key)
    if fn is None:
        return None
    try:
        # `stocks` is the trading page and needs the token to draw a ticket.
        # A public build is passed neither, so it cannot carry one.
        if key in ("stocks", "auctions", "lands", "banking",
                   "messages") and not public:
            built = fn(user_id, csrf)
        else:
            built = fn("" if public else user_id)
    except Exception as exc:                        # pragma: no cover
        log.warning("[livescreens] %s failed: %s", key, exc, exc_info=True)
        return _empty(key, "That screen could not be built from live data.")
    return depersonalise(built) if public else built
