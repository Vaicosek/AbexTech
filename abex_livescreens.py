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
        held[row[1]] = row[3]         # NAME -> shares; row[0] is the ticker

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
        # abex_live.stocks row, in order:
        #   0 ticker  1 name  2 grade  3 shares  4 average cost  5 price
        #   6 value   7 profit  8 profit >= 0  9 dividend  10 month
        # Average cost, not total paid - the total is implied by shares x average,
        # and the column a holder compares against price is the per-share one.
        try:
            v = _coins(r[6])
            c = _coins(r[4]) * _num(r[3])
        except (ValueError, IndexError):
            v = c = 0.0
        value += v
        cost += c
        up = bool(r[8]) if len(r) > 8 else True
        positions.append([r[1], r[3], r[5], r[6], r[4],
                          ("g|" if up else "l|") + str(r[7]),
                          r[9] if len(r) > 9 else DASH])

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
    for ticker, name, grade, shares_out, holders, price, free in rows:
        out.append([name, ticker, "G|" + str(grade), price, shares_out,
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
    table = {"h2": "Listed markets", "ac": 1,
             "c": ["Market", "Ticker", "Grade", "Share price#", "Shares out#",
                   "Holders#", "Free float#", "You hold#"],
             "r": out, "mine": held_rows,
             "n": ("Free float counts shares in someone else's hands - the "
                   "register minus the owner's own holding."
                   if out else "No market is listed.")}
    return _shell("exchange", f"{listed} market{'' if listed == 1 else 's'} listed.",
                  band, [table])


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
    screen_d = _shell("market", asof, band,
                      [ledger, month_bal, waterfall, liab, staff])
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


# ── Orders (the owner's side of Work) ───────────────────────────────────────
def orders(user_id: str = "") -> dict:
    """Open orders with who claimed them, and what was filled this week.

    `work` is the same table read as a worker: what can I claim. This is the
    poster's read: what did I commit, who took it, what have I paid. They share a
    source on purpose — two order lists that disagree about a quantity disagree
    about somebody's pay.
    """
    if abex_live is None:
        return _empty("orders", "The exchange is not reachable from this process.")
    try:
        db = abex_live._db()
        raw = db.load_orders() or []
    except Exception as exc:
        log.warning("[livescreens] orders unreadable: %s", exc)
        return _empty("orders", "Orders are not readable right now.")

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

    band = [("Open orders", str(len(open_rows)), f"{committed:,.0f}c committed"),
            ("Claimed", str(sum(1 for r in open_rows if not str(r[5]).startswith("m|"))),
             "taken, not yet closed"),
            ("Filled on record", str(len(filled)), "most recent first"),
            ("Employee priority", "45 minutes", "before an order opens to all")]

    a = {"h2": "Open orders", "ac": 1,
         "c": _cols("orders", 0) or ["Item", "Market", "Quantity", "Pay#", "Total#",
                                     "Claimed by", "Status"],
         "r": open_rows,
         "n": (f"{len(open_rows)} open, {committed:,.0f}c committed. Pay is per "
               "piece unless the order says per stack; a stack is 64."
               if open_rows else "No open orders.")}
    b = {"h2": "Filled this week",
         "c": _cols("orders", 1) or ["Filled", "Item", "Market", "Worker",
                                     "Quantity", "Paid#"],
         "r": filled,
         "n": ("Paid is the order's rate against the quantity claimed. What was "
               "actually transferred is in History."
               if filled else "Nothing filled on record.")}
    act = {"h2": "Posting work",
           "act": ("Orders are posted and approved from Discord. A new order is "
                   "employee-only for its first 45 minutes, then open to all."),
           "btns": [],
           "n": "Claims are approved on the order card, not here."}
    return _shell("orders", f"{len(open_rows)} open order"
                  f"{'' if len(open_rows) == 1 else 's'}.", band, [a, b, act])


# ── Auctions ────────────────────────────────────────────────────────────────
def auctions(user_id: str = "") -> dict:
    """Live lots and your bids.

    A BID IS A HOLD, NOT A DEBIT — the coins stay yours until a lot settles, and
    that is the one thing every screen showing a bid has to say rather than imply.
    The balance block says it; so does the note.
    """
    if abex_live is None:
        return _empty("auctions", "The exchange is not reachable from this process.")
    try:
        db = abex_live._db()
        lots = db.get_active_land_listings() or []
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
                     str(lot.get("ends_at") or "")[:16] or DASH, position])

    band = [("Live lots", str(len(rows)), "open for bidding"),
            ("Held in bids", f"{held:,.0f}c", "released when a lot closes"),
            ("Your bids", str(len(mine)), "lots you are in"),
            ("Sellers", str(len({r[1] for r in rows})), "with a lot open")]

    table = {"h2": "Live lots", "ac": 1,
             "c": _cols("auctions", 0) or ["Lot", "Seller", "Current bid#",
                                           "Your bid#", "Bids#", "Closes",
                                           "Your position"],
             "r": rows,
             "n": ("A bid is held from your wallet until the lot closes — the "
                   "coins stay yours until a lot settles."
                   if rows else "No lots are open.")}
    act = {"h2": "Bidding", "ac": 1,
           "act": ("Bids are placed in the auction room. A bid reserves the coins "
                   "against your wallet and moves nothing until a lot settles."),
           "btns": [["Open the auction room", "p", "/auctions"]],
           "n": "This page is the board. The room is where you act."}
    blocks = [act, table]
    if mine:
        blocks.append({"h2": "Your bids", "bal": mine,
                       "tot": ["Held in bids", f"{held:,.0f}c"],
                       "n": "Held, not spent."})
    return _shell("auctions", f"{len(rows)} lot{'' if len(rows) == 1 else 's'} live.",
                  band, blocks)


# ── Messages ────────────────────────────────────────────────────────────────
def messages(user_id: str = "") -> dict:
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
        row = [str(t.get("other_name") or DASH), preview, when or DASH]
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
    act = {"h2": "Reading and replying", "ac": 1,
           "act": ("Threads open in the messenger, which is where replies are "
                   "written and where a thread is marked read."),
           "btns": [["Open the messenger", "p", "/messages"]],
           "n": "This page lists what is waiting. It does not mark anything read."}
    asof = (f"{total_unread} unread." if total_unread else "Nothing unread.")
    return _shell("messages", asof, None, [act, a, b])


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
def banking(user_id: str = "") -> dict:
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
    blocks.append({"h2": "Moving money",
                   "act": ("Deposits, withdrawals, borrowing and repayment happen "
                           "in the bank. Nothing on this page moves a coin."),
                   "btns": [["Open the bank", "p", "/banking"]],
                   "n": "Read here, act there — so a page that cannot reach the "
                        "bank can still show you your wallet."})
    asof = ("Interest is paid weekly." if acct else
            "Your wallet is live. " + bank_note)
    return _shell("banking", asof, band, blocks)


#: key -> builder. A screen absent here has no live source yet and keeps its
#: canvas page under /canvas; it is NOT served with sample rows on a live route.
BUILDERS = {
    "hub": hub, "markets": markets, "stocks": stocks, "work": work,
    "lands": lands, "exchange": exchange,
    "market": market, "filing": filing,
    "orders": orders, "auctions": auctions, "messages": messages,
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


def screen(key: str, user_id: str = "", public: bool = False) -> dict | None:
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
        built = fn("" if public else user_id)
    except Exception as exc:                        # pragma: no cover
        log.warning("[livescreens] %s failed: %s", key, exc, exc_info=True)
        return _empty(key, "That screen could not be built from live data.")
    return depersonalise(built) if public else built
