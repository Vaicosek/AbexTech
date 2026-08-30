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


#: The per-section hues, so a figure can never be painted with one. See `_stats`.
_SECTION_HUES = frozenset(DOMAINS.values())


def _e(x):
    return _h.escape(str(x))


def _stats(items):
    """A page's figures as a definition list: label left, figure right, one ruled line.

    This replaces the band of stat tiles. Items keep the tiles' shape -- `(label, value,
    note)` or `(label, value, note, colour)` -- because the data still ships that way,
    but the note was a caption under the figure and the design carries no captions, so
    it is not rendered.

    A three-item entry takes its colour from `money_tone(label)` -- the one rule, shared
    with the bot and the mockup. A fourth item still wins, exactly as an explicit cell
    tone beats the label rule in the mockup. Use it where the label is outside the rule
    and the meaning is not in doubt -- not to re-decide a label the rule already covers.
    """
    out = []
    for item in items:
        k, v = item[0], item[1]
        colour = item[3] if len(item) > 3 else money_tone(k)
        # A SECTION hue is not a money colour. `abex_theme` says the domain hues are
        # "never a fill and never carry meaning about money", and the banking figures
        # still arrive painted with the banking hue -- which is also the blue the
        # palette no longer has. An explicit tone still wins; a section hue does not.
        if colour in _SECTION_HUES:
            colour = money_tone(k)
        # No tone means the default text colour -- not an empty `color:` declaration.
        style = f' style="color:{colour}"' if colour else ""
        out.append(f'<tr><td>{_e(k)}</td>'
                   f'<td class="num"{style}>{_e(v)}</td></tr>')
    return ('<div class="panel"><div class="tablewrap"><table><tbody>'
            + "".join(out) + "</tbody></table></div></div>")


def _head(title, figure=""):
    return f'<div class="pagehead"><div><h1>{_e(title)}</h1></div>{figure}</div>'


def _how(label, href):
    """A plain-word link to the page that carries the rule.

    Rules used to be written into a sentence under the heading or a footnote under the
    table. The rule itself is not deleted -- it moves to its own page, and the screen
    keeps one link to it.
    """
    return f'<p class="meta"><a href="{href}">{_e(label)}</a></p>'


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
        _head("Markets") +
        _how("How grades work", "/help/grades") +
        '<div class="panel accented">' +
        _table([("Market", ""), ("Ticker", ""), ("Owner", ""), ("Grade", ""), ("Backing", "num"),
                ("Last net", "num"), ("Index weight", "num"), (last_col, "num")],
               body_rows) +
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
    # The number of listed markets belongs in ONE place: the table's own summary
    # line. A figure reading "Markets listed 13" above a table of eight rows is two
    # answers to the same question, and the tile was the one that was wrong.
    figures = [t for t in (tiles or D.EXCHANGE_TILES)
               if "listed" not in str(t[0]).lower()]
    return (_head("Exchange") +
            _stats(figures) +
            '<div class="panel accented">' +
            _table([("Market", ""), ("Grade", ""), ("Shares out", "num"),
                    ("Holders", "num"), ("Last settled", "num"), ("Free float", "num")],
                   rows,
                   f"{len(listings or D.EXCHANGE)} listed "
                   f"{'market' if len(listings or D.EXCHANGE) == 1 else 'markets'}"
                   ) + "</div>")


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
        arrow = ""          # the sign and the colour already say it
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
    n = len(holdings or D.HOLDINGS)
    return (_head("Stocks") +
            '<div class="panel accented">' +
            _table([("Market", ""), ("Grade", ""), ("Shares", "num"), ("Avg cost", "num"),
                    ("Price", "num"), ("Value", "num"), ("Profit or loss", "num")]
                   + ([("Dividend", "num")] if show_dividend else [])
                   + [(last_col, "num")], rows,
                   note or f"{n} {'position' if n == 1 else 'positions'}")
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
                                     "Veteran · 0.8% a month on savings") +
            _stats(D.BANK_TILES) +
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
                                     "Veteran · 18% a year on loans") +
            _stats([("Borrowed", "9,400c", ""),
                    ("Due this cycle", "1,200c", ""),
                    ("Headroom", "8,290c", "", GAIN)]) +
            '<div class="grid two">'
            '<div class="panel accented"><div class="h2">What you can borrow</div>'
            f'<div class="tablewrap"><table style="min-width:0"><tbody>{borrow}</tbody></table></div>'
            + _how("How borrowing works", "/help/borrowing") + "</div>"
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
            _stats(D.BOND_TILES + [("Next maturity", "in 2 cycles", "")]) +
            '<div class="panel accented"><div class="h2">Bonds you hold</div>' +
            _table([("Bond", ""), ("Term", ""), ("Face", "num"), ("Coupon", "num"),
                    ("Paid so far", "num"), ("Matures", "num")], held) + "</div>"
            '<div class="panel"><div class="h2">On offer</div>' +
            _table([("Bond", ""), ("Grade", ""), ("Term", ""), ("Coupon", "num"),
                    ("Left to fill", "num"), ("What backs it", "")], offered) +
            _how("How bonds work", "/help/bonds") + "</div>")


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
    n = len(rows_data or D.ORDERS)
    return (_head("Work") +
            _how("How pay works", "/help/pay") +
            '<div class="panel accented">' +
            _table([("Item", ""), ("Market", ""), ("Pay", "num"), ("Total", "num"),
                    ("Points", "num"), ("Window", "num"), ("", "num")], rows,
                   note or f"{n} open {'order' if n == 1 else 'orders'}")
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
    return (_head("Claims") +
            _how("How claims work", "/help/claims") +
            '<div class="panel accented">' +
            _table(headers, rows, note) +
            "</div>")


# ── Investor ────────────────────────────────────────────────────────────────
def investor(rows_data=None, tiles=None, pool_pct: float = 10.0) -> str:
    """The preferred pool. `rows_data` and `tiles` default to the design's."""
    rows = "".join(
        f'<tr><td><strong>{_e(n)}</strong></td>'
        f'<td class="num">{_e(net)}</td><td class="num">{_e(share)}</td></tr>'
        for t, n, net, share in (rows_data or D.POOL))
    figures = list(tiles or
                   [("Your stake", "45 / 500", "", HELD),
                    ("Pool, July", "11,400c", ""),
                    ("Your share", "+1,026c", "", GAIN),
                    ("Paid", "Sat 29 Aug 09:16", "", "")])
    # The pool's cut of net was a caption under one figure and a sentence under the
    # table. It is a figure, so it is a line in the list once; the rule that goes with
    # it is on the linked page.
    figures.append(("Pool share of net", f"{pool_pct:,.0f}%", "", ""))
    return (_head("Investor") +
            _how("How the preferred pool works", "/help/preferred") +
            _stats(figures) +
            '<div class="panel accented"><div class="h2">Where the pool came from</div>' +
            _table([("Market", ""), ("Net", "num"), ("Share of pool", "num")], rows) +
            "</div>")


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
    return (_head("Earnings reports") +
            _how("How filings work", "/help/filings") +
            '<div class="panel accented">' +
            _table([("Market", ""), ("Month", ""), ("Net", "num"), ("Per share", "num"),
                    ("Dividend", "num"), ("Grade after", "")], rows, note)
            + "</div>")
