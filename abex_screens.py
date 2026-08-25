"""
abex_screens.py — screen bodies, ported from the approved mockup.

Each function returns the <main> body only; `abex_shell.render()` supplies the chrome.
Content comes from `abex_data`, which holds the mockup's own strings and figures.
"""
from __future__ import annotations

import html as _h

from abex_shell import grade_chip
import abex_data as D
from abex_theme import DOMAINS, GAIN, HELD, INERT, LOSS, WARN, money_tone


def _e(x):
    return _h.escape(str(x))


def _band(tiles, cls="four"):
    """Render a band of tiles: `(label, value, note)` or `(label, value, note, colour)`.

    A three-item tile takes its colour from `money_tone(label)` -- the one rule, shared
    with the bot and the mockup. Every tile here used to carry a hand-picked colour,
    which is how a section hue ended up marking money on two of them (`abex_theme` says
    the domain hues are "never a fill and never carry meaning about money") and how
    three others carried `#F4F4F4`, a literal from the other skin that is not a token
    in this one.

    A fourth item still wins, exactly as an explicit cell tone beats the label rule in
    the mockup. Use it where the label is outside the rule and the meaning is not in
    doubt -- not to re-decide a label the rule already covers.
    """
    out = []
    for tile in tiles:
        k, v, n = tile[0], tile[1], tile[2]
        colour = tile[3] if len(tile) > 3 else money_tone(k)
        # No tone means the default text colour -- not an empty `color:` declaration.
        style = f' style="color:{colour}"' if colour else ""
        out.append(f'<div class="tile"><span class="k">{_e(k)}</span>'
                   f'<span class="v"{style}>{_e(v)}</span>'
                   f'<span class="n">{_e(n)}</span></div>')
    return f'<div class="band {cls}">' + "".join(out) + "</div>"


def _head(title, sub="", figure=""):
    s = f'<div class="sub">{sub}</div>' if sub else ""
    return (f'<div class="pagehead"><div><h1>{_e(title)}</h1>{s}</div>{figure}</div>')


def _tabs(items, active, status=""):
    # `cur` is built outside the f-string: Python 3.11 rejects a backslash inside an
    # f-string expression, and the attribute needs escaped quotes.
    parts = []
    for key, label, href in items:
        cur = ' aria-current="page"' if key == active else ""
        parts.append(f'<a class="tab" href="{href}"{cur}>{_e(label)}</a>')
    t = "".join(parts)
    st = f'<span class="status">{_e(status)}</span>' if status else ""
    return f'<div class="tabs">{t}{st}</div>'


def _table(headers, rows, foot=""):
    th = "".join(f'<th class="{c}">{_e(h)}</th>' for h, c in headers)
    f = f'<div class="tfoot">{_e(foot)}</div>' if foot else ""
    return (f'<div class="tablewrap"><table><thead><tr>{th}</tr></thead>'
            f'<tbody>{rows}</tbody></table></div>{f}')


# ── Markets ─────────────────────────────────────────────────────────────────
def markets(rows=None, last_col: str = "Next report") -> str:
    """The thirteen markets.

    `rows` defaults to the design's sample data so the screen renders before it is
    wired. When live rows are passed, the last column is what the data actually
    knows — the month each market last filed — rather than a due date the system
    does not store.
    """
    legend = " ".join(
        f'{grade_chip(g)} <span class="faint">{_e(req)}</span>'
        for g, req in D.GRADE_LEGEND)
    body_rows = "".join(
        f'<tr class="clickable" onclick="location.href=\'/markets/{t.lower()}\'">'
        f'<td><strong>{_e(name)}</strong></td>'
        f'<td class="faint">{_e(t)}</td>'
        f'<td class="faint">{_e(owner)}</td>'
        f'<td>{grade_chip(grade)}</td>'
        f'<td class="num">{_e(backing)}</td><td class="num">{_e(net)}</td>'
        f'<td class="num">{_e(weight)}</td><td class="num faint">{_e(nxt)}</td></tr>'
        for t, name, owner, grade, backing, net, weight, nxt in (rows or D.MARKETS))
    return (
        _head("Markets",
              "The businesses, not the shopfront. Goods change hands in-game; this records "
              "what each market sold, kept and holds in collateral. Grade is led by "
              "backing &mdash; composite quality alone cannot reach the top bands.") +
        f'<div class="panel"><div class="h2">What a grade requires</div>'
        f'<div style="display:flex;gap:18px;flex-wrap:wrap;align-items:center">{legend}</div></div>' +
        '<div class="panel accented">' +
        _table([("Market", ""), ("Ticker", ""), ("Owner", ""), ("Grade", ""), ("Backing", "num"),
                ("Last net", "num"), ("Index weight", "num"), (last_col, "num")],
               body_rows,
               f"Showing all {len(rows or D.MARKETS)} markets, best grade first.") +
        "</div>")


# ── Exchange ────────────────────────────────────────────────────────────────
def exchange(listings=None, tiles=None) -> str:
    """The share side. `listings` and `tiles` default to the design's rows."""
    rows = "".join(
        f'<tr class="clickable" onclick="location.href=\'/exchange/{t.lower()}\'">'
        f'<td><strong>{_e(t)}</strong> <span class="faint">{_e(name)}</span></td>'
        f'<td>{grade_chip(grade)}</td><td class="num">{_e(sh)}</td>'
        f'<td class="num">{_e(hold)}</td><td class="num">{_e(px)}</td>'
        f'<td class="num faint">{_e(flt)}</td></tr>'
        for t, name, grade, sh, hold, px, flt in (listings or D.EXCHANGE))
    return (_head("Exchange", "The share side. Every listed market, what it has out and "
                              "who holds it.") +
            _band(tiles or D.EXCHANGE_TILES) +
            '<div class="panel accented">' +
            _table([("Market", ""), ("Grade", ""), ("Shares out", "num"),
                    ("Holders", "num"), ("Last settled", "num"), ("Free float", "num")],
                   rows,
                   f"{len(listings or D.EXCHANGE)} listed "
                   f"{'market' if len(listings or D.EXCHANGE) == 1 else 'markets'}, "
                   "largest register first.") + "</div>")


# ── Stocks ──────────────────────────────────────────────────────────────────
def stocks(holdings=None, formula=None, market: str = "GreyHames",
           last_col: str = "Next", note: str = "", show_dividend: bool = True) -> str:
    """What the viewer owns.

    `holdings` defaults to the design's rows. Live rows come from `abex_live`, and
    with them the last column is the month each market was last priced — a market
    settles when its owner files a report, so there is no next date to show.
    """
    rows = ""
    for t, name, grade, sh, avg, px, val, pl, up, div, nxt in (holdings or D.HOLDINGS):
        arrow = "&#9650;" if up else "&#9660;"
        col = GAIN if up else LOSS
        rows += (f'<tr class="clickable" onclick="location.href=\'/exchange/{t.lower()}\'">'
                 f'<td><strong>{_e(name)}</strong></td>'
                 f'<td>{grade_chip(grade)}</td><td class="num">{_e(sh)}</td>'
                 f'<td class="num faint">{_e(avg)}</td><td class="num">{_e(px)}</td>'
                 f'<td class="num">{_e(val)}</td>'
                 f'<td class="num" style="color:{col}">{arrow} {_e(pl)}</td>'
                 + (f'<td class="num faint">{_e(div)}</td>' if show_dividend else "")
                 + f'<td class="num faint">{_e(nxt)}</td></tr>')
    formula = "".join(
        f'<tr><td>{_e(k)}</td><td class="num" style="color:{c}">{_e(v)}</td></tr>'
        for k, v, c in (formula or D.PRICE_FORMULA))
    return (_head("Stocks", "What you own, and what the next report will settle it at.") +
            '<div class="panel accented">' +
            _table([("Market", ""), ("Grade", ""), ("Shares", "num"), ("Avg cost", "num"),
                    ("Price", "num"), ("Value", "num"), ("Profit or loss", "num")]
                   + ([("Dividend", "num")] if show_dividend else [])
                   + [(last_col, "num")], rows,
                   note or "Five positions. Prices settle when each market files.")
            + "</div>" +
            '<div class="panel"><div class="h2">How the price is set &mdash; '
            f'{_e(market)}</div>'
            f'<div class="tablewrap"><table style="min-width:0"><tbody>{formula}</tbody>'
            '</table></div>'
            '<div class="tfoot">Trailing net &times; growth P/E &divide; shares = price, '
            'floored at book value.</div></div>')


# ── Banking ─────────────────────────────────────────────────────────────────
_BANK_TABS = [("banking.accounts", "Accounts", "/banking"),
              ("banking.loans", "Loans", "/banking/loans"),
              ("banking.bonds", "Bonds", "/banking/bonds")]


def banking_accounts() -> str:
    # Same rule as the tiles: the label decides, an explicit colour overrides.
    # "Outstanding" carried the banking section hue, which is not a money colour.
    _gex_rows = [("Original stake", "128 shares"),
                 ("Converted to", "68,400c"),
                 ("Repaid so far", "26,800c", GAIN),
                 ("Outstanding", "41,600c")]
    gex = "".join(
        '<tr><td>{}</td><td class="num"{}>{}</td></tr>'.format(
            _e(r[0]),
            (lambda c: f' style="color:{c}"' if c else "")(
                r[2] if len(r) > 2 else money_tone(r[0])),
            _e(r[1]))
        for r in _gex_rows)
    return (_head("Banking") + _tabs(_BANK_TABS, "banking.accounts",
                                     "Veteran &middot; 0.8% a month on savings") +
            _band(D.BANK_TILES) +
            '<div class="panel accented"><div class="h2">GEX absorption</div>'
            f'<div class="tablewrap"><table style="min-width:0"><tbody>{gex}</tbody></table></div>'
            '<div class="tfoot">Your GEX shares were cancelled and reissued as a debt claim. '
            'It is paid from earnings before any dividend.</div></div>')


def banking_loans() -> str:
    borrow = "".join(
        f'<tr><td>{_e(k)}</td><td class="num" style="color:{c}">{_e(v)}</td></tr>'
        for k, v, c in D.BORROW)
    tiers = "".join(
        f'<tr><td style="color:{c}">{_e(t)}</td><td class="num">{_e(r)}</td>'
        f'<td class="faint">{_e(n)}</td></tr>' for t, r, n, c in D.TIERS)
    return (_head("Banking") + _tabs(_BANK_TABS, "banking.loans",
                                     "Veteran &middot; 18% a year on loans") +
            _band([("Borrowed", "9,400c", "across 2 loans"),
                   ("Due this cycle", "1,200c", "paid before dividends"),
                   ("Headroom", "8,290c", "you can borrow", GAIN)], "three") +
            '<div class="grid two">'
            '<div class="panel accented"><div class="h2">What you can borrow</div>'
            f'<div class="tablewrap"><table style="min-width:0"><tbody>{borrow}</tbody></table></div>'
            '<div class="tfoot">Missed payments take the collateral, they do not touch '
            'your wallet.</div></div>'
            '<div class="panel"><div class="h2">Rate by tier</div>' +
            _table([("Tier", ""), ("Rate", "num"), ("How you get there", "")], tiers) +
            "</div></div>")


def banking_bonds() -> str:
    held = "".join(
        f'<tr><td><strong>{_e(t)}</strong> <span class="faint">{_e(i)}</span></td>'
        f'<td class="faint">{_e(term)}</td><td class="num">{_e(face)}</td>'
        f'<td class="num">{_e(cp)}</td><td class="num">{_e(paid)}</td>'
        f'<td class="num faint">{_e(m)}</td></tr>'
        for t, i, term, face, cp, paid, m in D.BONDS_HELD)
    offered = "".join(
        f'<tr><td><strong>{_e(t)}</strong> <span class="faint">{_e(i)}</span></td>'
        f'<td>{grade_chip(g)}</td><td class="faint">{_e(term)}</td>'
        f'<td class="num">{_e(cp)}</td><td class="num">{_e(left)}</td>'
        f'<td class="faint">{_e(back)}</td></tr>'
        for t, i, g, term, cp, left, back in D.BONDS_OFFERED)
    return (_head("Banking") + _tabs(_BANK_TABS, "banking.bonds") +
            _band(D.BOND_TILES + [("Next maturity", "in 2 cycles", "6,000c returned")], "three") +
            '<div class="panel accented"><div class="h2">Bonds you hold</div>' +
            _table([("Bond", ""), ("Term", ""), ("Face", "num"), ("Coupon", "num"),
                    ("Paid so far", "num"), ("Matures", "num")], held) + "</div>"
            '<div class="panel"><div class="h2">On offer</div>' +
            _table([("Bond", ""), ("Grade", ""), ("Term", ""), ("Coupon", "num"),
                    ("Left to fill", "num"), ("What backs it", "")], offered,
                   "Coupons are paid out of net before dividends.") + "</div>")


# ── Work / Orders ───────────────────────────────────────────────────────────
def work(rows_data=None, note: str = "") -> str:
    """Open production orders. `rows_data` defaults to the design's rows."""
    rows = ""
    for item, mkt, owner, qty, detail, unit, per, total, pts, prio, left in (
            rows_data or D.ORDERS):
        win = (f'<span style="color:{DOMAINS["work"]}">{_e(left)}</span>' if prio
               else '<span class="faint">Open to all</span>')
        rows += (f'<tr><td><strong>{_e(item)}</strong><br>'
                 f'<span class="faint">{_e(qty)} &middot; {_e(detail)}</span></td>'
                 f'<td>{_e(mkt)}<br><span class="faint">{_e(owner)}</span></td>'
                 f'<td class="num">{_e(unit)}<br><span class="faint">{_e(per)}</span></td>'
                 f'<td class="num">{_e(total)}</td>'
                 f'<td class="num faint">{_e(pts)}</td>'
                 f'<td class="num">{win}</td>'
                 f'<td class="num"><button class="btn">Claim</button></td></tr>')
    return (_head("Work", "Claim a production order, deliver it, get paid. Pay is per piece "
                          "unless the order says per stack &mdash; a stack is 64.") +
            '<div class="panel accented">' +
            _table([("Item", ""), ("Market", ""), ("Pay", "num"), ("Total", "num"),
                    ("Points", "num"), ("Window", "num"), ("", "num")], rows,
                   note or f"{len(D.ORDERS)} open orders across all markets.")
            + "</div>")


# ── Lands ───────────────────────────────────────────────────────────────────
def lands(rows_data=None, note: str = "") -> str:
    """Land listings. `rows_data` defaults to the design's rows."""
    # Lease STATE, not money -- money_tone does not apply. But "Expiring" carried the
    # BANKING section's hue on the lands screen, which marks the wrong section, and the
    # other two were stray literals. WARN is the reserved semantic for "attention", and
    # a vacant plot is dormant rather than a loss.
    tone = {"Leased": GAIN, "Expiring": WARN, "Vacant": INERT}
    rows = "".join(
        f'<tr><td><strong>{_e(n)}</strong></td><td class="faint">{_e(o)}</td>'
        f'<td>{_e(t)}</td><td class="num">{_e(r)}</td>'
        f'<td style="color:{tone.get(st, INERT)}">{_e(st)}</td>'
        f'<td class="faint">{_e(term)}</td></tr>'
        for n, o, t, r, st, term in (rows_data or D.PARCELS))
    # Land here is bought outright — there is no rent and no lease anywhere in the
    # code. The design's rent-and-term columns describe a product this economy does
    # not sell, so live rows are headed for what a listing actually has.
    headers = ([("Parcel", ""), ("Seller", ""), ("Buyer", ""), ("Price", "num"),
                ("Status", ""), ("Size", "")] if rows_data else
               [("Parcel", ""), ("Owner", ""), ("Tenant", ""), ("Rent", "num"),
                ("State", ""), ("Term", "")])
    sub = ("Parcels for sale, and what they went for." if rows_data else
           "Parcels, who holds them and what the rent is.")
    return (_head("Lands", sub) +
            '<div class="panel accented">' +
            _table(headers, rows,
                   note or "A lapsed lease returns the parcel to the market at its "
                           "listed price.") +
            "</div>")


# ── Investor ────────────────────────────────────────────────────────────────
def investor(rows_data=None, tiles=None, pool_pct: float = 10.0) -> str:
    """The preferred pool. `rows_data` and `tiles` default to the design's."""
    rows = "".join(
        f'<tr><td><strong>{_e(n)}</strong></td>'
        f'<td class="num">{_e(net)}</td><td class="num">{_e(share)}</td></tr>'
        for t, n, net, share in (rows_data or D.POOL))
    return (_head("Investor", "GEX.PR preferred. A separate class from common shares "
                              "&mdash; common holders take no cut of this pool.") +
            _band(tiles or
                  [("Your stake", "45 / 500", "9.0% of the pool", HELD),
                   ("Pool, July", "11,400c", "10% of group net"),
                   ("Your share", "+1,026c", "paid 09:16", GAIN)], "three") +
            '<div class="panel accented"><div class="h2">Where the pool came from</div>' +
            _table([("Market", ""), ("Net", "num"), ("Share of pool", "num")], rows,
                   f"{pool_pct:,.0f}% of each market's monthly net feeds the preferred "
                   "pool. A market that lost money contributes nothing.") + "</div>")


# ── Earnings reports ────────────────────────────────────────────────────────
def filings(rows_data=None, note: str = "") -> str:
    """Every filing on record. `rows_data` defaults to the design's rows."""
    rows = ""
    for t, name, month, net, ps, div, grade, missed in (rows_data or D.FILINGS):
        style = f' style="color:{LOSS}"' if missed else ""
        rows += (f'<tr><td{style}><strong>{_e(name)}</strong></td>'
                 f'<td>{_e(month)}</td><td class="num"{style}>{_e(net)}</td>'
                 f'<td class="num">{_e(ps)}</td><td class="num"{style}>{_e(div)}</td>'
                 f'<td>{grade_chip(grade)}</td></tr>')
    return (_head("Earnings reports", "Every filing across the exchange.") +
            '<div class="panel accented">' +
            _table([("Market", ""), ("Month", ""), ("Net", "num"), ("Per share", "num"),
                    ("Dividend", "num"), ("Grade after", "")], rows,
                   note or ("Showing the most recent filings. A missed filing keeps "
                            "the last price, pays no dividend and drops a band."))
            + "</div>")
