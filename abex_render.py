"""abex_render.py — turn a canvas screen (`abex_canvas.SCREENS`) into page HTML.

One renderer, thirteen screens. The design describes a screen as data — a band of
tiles and a list of blocks — and the spec fixes three block shapes (§4; a fourth, the price line,
is added here and `_spark` says why)
and the order in which a cell's colour is decided (§5). So the screens do not
each need their own page-builder; they need one that obeys those rules, and then
a screen is a dict.

That is the whole point of doing it this way. Hand-writing thirteen screens is
hours of transcription and every hour is a chance to put a number in the wrong
tone — and in a money UI a wrongly-toned figure reads as a fact, not a bug.

## Tone resolution (spec §5, later wins)

    1. base            identity column = bold text, numeric column = plain
    2. inline tag      'g|' gain, 'l|' loss, 'w|' warn, 'm|' faint, 'k|' action,
                       'G|' grade ramp, 'T|<seconds>' live countdown,
                       'A|<href>|<text>' a link
    3. header rule     Grade / Backing / Coupon / Odds / Stake / Chunks, date
                       columns, pay columns — keyed off the column heading
    4. row wash        "your position" rows, only when holdings are the minority

Layers 1–3 are here. Layer 4 needs to know which rows are yours, which is a
data question, so it is applied by the caller through `mine=`.

## Header conventions the canvas uses

A heading ending in `#` is a numeric column: right-aligned, tabular figures, and
the `#` is not shown. A heading that is only `#` is an action column — no label,
right-aligned. Both come straight from the canvas and are not invented here.
"""
from __future__ import annotations

import html as _h
import re

try:
    from abex_theme import GRADES
except Exception:                                   # pragma: no cover
    GRADES = {}

#: Spec §1: the grade column is graduated through the money-tone family — best
#: grades read as gain, worst as loss — rather than getting a hue of its own.
_GRADE_RAMP = {
    "AAA": "var(--gain)", "AA": "#a3c47a", "A": "var(--accent)",
    "BBB": "var(--accent)", "BB": "#d1906a", "B": "#d1906a",
    "CCC": "var(--loss)", "CC": "var(--loss)", "C": "var(--loss)",
    "D": "var(--loss)",
}

#: Inline tag → CSS colour. `k` is an action word (a link-alike), which is the
#: accent, because §1 reserves the accent for things you can click.
_TAG = {
    "g": "var(--gain)", "l": "var(--loss)", "w": "var(--warn)",
    "m": "var(--faint)", "k": "var(--accent)",
}

#: Column headings whose whole column follows a rule. Keyed loosely: the canvas
#: writes "Backing#" and "Last net#", so the `#` is stripped before matching.
_NUMERIC_HINT = ("c", "×", "%")


def _e(x) -> str:
    return _h.escape(str(x))


def _split_tag(cell: str) -> tuple[str, str]:
    """`('g', '1,240c')` from `'g|1,240c'`; `('', cell)` when untagged.

    Only a single letter followed by `|` counts. A cell whose text legitimately
    contains a pipe — none do today, but copy changes — is left alone rather
    than silently truncated at the first bar.
    """
    m = re.match(r"^([glwmkGTA])\|(.*)$", cell, re.S)
    return (m.group(1), m.group(2)) if m else ("", cell)


def _grade_colour(text: str) -> str:
    g = text.strip().upper()
    return _GRADE_RAMP.get(g, "")


def _backing_colour(text: str) -> str:
    """Ramped gain→warn→loss with a hard cliff under 1.0×; bold under 0.6× (§1)."""
    m = re.search(r"([\d.]+)", text)
    if not m:
        return ""
    try:
        v = float(m.group(1))
    except ValueError:
        return ""
    if v >= 1.2:
        return "var(--gain)"
    if v >= 1.0:
        return "var(--accent)"
    return "var(--loss)"


#: §4, Claims: "Chunk-count column is size-scaled: brightness + font-size
#: log-interpolate from 10 to 1000 chunks." Log, not linear, because the range is
#: two orders of magnitude — linear would leave everything under 200 chunks
#: identically dim and make the column decoration rather than information.
_CHUNK_MIN, _CHUNK_MAX = 10.0, 1000.0


def _chunk_style(text: str) -> str:
    """Inline style for a chunk count, or "" when the cell is not one.

    A claim of 12 chunks and one of 900 are different kinds of thing, and the
    figure alone reads as two numbers of similar weight. Size and brightness
    carry the difference at a glance, which is what a register is scanned for.
    """
    m = re.search(r"([\d,]+)", text)
    if not m:
        return ""
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:
        return ""
    if n <= 0:
        return ""
    import math
    lo, hi = math.log10(_CHUNK_MIN), math.log10(_CHUNK_MAX)
    t = (math.log10(max(n, 1.0)) - lo) / (hi - lo)
    t = min(1.0, max(0.0, t))
    size = 15.5 + t * 6.5                      # 15.5px -> 22px
    # Between `faint` and `text`, so the smallest claims still read and the
    # biggest do not shout brighter than the primary text tone.
    grey = int(round(0x8A + t * (0xEF - 0x8A)))
    return "font-size:%.1fpx;color:#%02x%02x%02x" % (size, grey, grey, grey)


def _header_rule(head: str, text: str) -> tuple[str, bool]:
    """`(colour, bold)` for a cell, decided by its column heading."""
    h = head.rstrip("#").strip().lower()
    if h == "grade":
        return _grade_colour(text.lstrip("G|")), True
    if h == "backing":
        c = _backing_colour(text)
        m = re.search(r"([\d.]+)", text)
        try:
            bold = bool(m) and float(m.group(1)) < 0.6
        except ValueError:
            bold = False
        return c, bold
    return "", False


def _countdown_face(secs: int) -> str:
    """`Xh XXm` -> `Xm XXs` -> `Xs` -> `closed` (§5). Mirrored in the page
    script, which takes this cell over a second later; the two formats have to
    agree or the first tick visibly rewrites every clock on the page."""
    if secs <= 0:
        return "closed"
    if secs >= 3600:
        return "%dh %02dm" % (secs // 3600, (secs % 3600) // 60)
    if secs >= 60:
        return "%dm %02ds" % (secs // 60, secs % 60)
    return "%ds" % secs


def _cell(head: str, raw, numeric: bool, identity: bool) -> str:
    text = "" if raw is None else str(raw)
    tag, text = _split_tag(text)

    colour, bold = "", identity
    if tag == "G":                       # grade ramp asked for explicitly
        colour = _grade_colour(text)
        bold = True
    elif tag == "A":                     # a link: 'A|<href>|<text>'
        href, _, label = text.partition("|")
        # §1 reserves the accent for things you can click, so a link cell takes
        # it and nothing else does. The identity column stays bold — it is still
        # the row's name, it is now also its way in.
        st = ' style="font-weight:700"' if identity else ""
        # Built with % rather than an f-string: the escaped quotes inside the
        # class attribute are a backslash in an f-string expression, which is a
        # syntax error on 3.11. This file has hit that twice now.
        cls = ' class="num"' if numeric else ""
        return "<td%s%s><a href=\"%s\">%s</a></td>" % (cls, st, _e(href), _e(label))
    elif tag == "T":                     # countdown; ticked by the page script
        # Server-rendered FIRST, like the price line: the script takes over a
        # cell that already says the right thing. It used to ship an em dash and
        # wait, so a reader without the script — or in the moment before it runs
        # — saw no closing time at all on an auction board.
        secs = text.strip()
        try:
            left = int(secs)
        except ValueError:
            return '<td class="num">%s</td>' % _e("—")
        style = ""
        if left <= 60 and left > 0:
            style = ' style="color:var(--loss);font-weight:700"'
        elif left <= 300:
            style = ' style="color:var(--loss)"'
        return '<td class="num countdown"%s data-left="%d">%s</td>' % (
            style, left, _e(_countdown_face(left)))
    elif tag:
        colour = _TAG.get(tag, "")

    hc, hb = _header_rule(head, text)
    if hc and not colour:                # header rule loses to an explicit tag
        colour = hc
    bold = bold or hb

    style = []
    if head.rstrip("#").strip().lower() in ("chunks", "size", "chunk count"):
        chunk = _chunk_style(text)
        if chunk:
            style.append(chunk)
            colour = ""                   # the ramp IS the colour for this column
    if colour:
        style.append(f"color:{colour}")
    if bold:
        style.append("font-weight:700")
    st = f' style="{";".join(style)}"' if style else ""
    cls = ' class="num"' if numeric else ""
    return f"<td{cls}{st}>{_e(text)}</td>"


def _table(block: dict, mine=None) -> str:
    """A table. `dense:1` on the block tightens row padding (§5).

    Padding only — §5 is explicit that `dense` "does not change font size". A
    column of figures that shrinks when a table gets long is a column that reads
    as less important than the same figures on a short one.
    """
    # A block may name its own "your position" rows. `mine=` on `screen_html` is
    # one set applied to every table on the screen, which is right when a screen
    # has one table and wrong the moment it has two — the indices from the
    # holdings table would wash arbitrary rows of the filings table beside it.
    # A block's own list wins.
    if block.get("mine") is not None:
        mine = set(block["mine"])
    heads = block.get("c") or []
    numeric = [h.endswith("#") or h == "#" for h in heads]
    labels = ["" if h == "#" else h.rstrip("#") for h in heads]

    # Built outside the f-string: the server runs 3.11+ and a backslash inside an
    # f-string expression is a syntax error there, escaped quotes included.
    th = "".join("<th%s>%s</th>" % (' class="num"' if n else "", _e(l))
                 for l, n in zip(labels, numeric))
    body = []
    rows = block.get("r") or []
    # §5: the "your position" wash is a FLAG, so it only reads as one while your
    # rows are the minority. Applied to half a table it is just a zebra stripe.
    wash = mine and len(mine) * 2 < len(rows)
    for i, row in enumerate(rows):
        tds = "".join(_cell(heads[j] if j < len(heads) else "", c, numeric[j] if j < len(numeric) else False,
                            j == 0)
                      for j, c in enumerate(row))
        cls = ' class="mine"' if (wash and i in mine) else ""
        body.append(f"<tr{cls}>{tds}</tr>")

    note, link = block.get("n"), block.get("lk")
    foot = ""
    if note or link:
        lk = f' <a href="#">{_e(link)}</a>' if link else ""
        foot = f'<div class="tfoot">{_e(note or "")}{lk}</div>'
    cls = "dense" if block.get("dense") else ""
    return ('<div class="tablewrap"><table class="%s"><thead><tr>' % cls + th
            + "</tr></thead><tbody>"
            + "".join(body) + "</tbody></table></div>" + foot)


def _balance(block: dict) -> str:
    """Two/three-column plain table, no header row; `tot` gets a rule and bold.

    §5 also says a deduction row is written "Less …" in the copy and is never
    coloured as income. That is a COPY rule, honoured in the canvas data, so the
    renderer does not need to detect it — and must not guess, because a negative
    number is not the same thing as a deduction.
    """
    out = []
    for row in block.get("bal") or []:
        label = row[0] if len(row) > 0 else ""
        value = row[1] if len(row) > 1 else ""
        note = row[2] if len(row) > 2 else ""
        tag, value = _split_tag(str(value))
        st = f' style="color:{_TAG[tag]}"' if tag in _TAG else ""
        n = f'<div class="bnote">{_e(note)}</div>' if note else ""
        out.append(f'<tr><td class="blabel">{_e(label)}{n}</td>'
                   f'<td class="num"{st}>{_e(value)}</td></tr>')
    tot = block.get("tot")
    if tot:
        tag, tv = _split_tag(str(tot[1] if len(tot) > 1 else ""))
        st = f' style="color:{_TAG[tag]}"' if tag in _TAG else ""
        out.append(f'<tr class="btot"><td class="blabel">{_e(tot[0])}</td>'
                   f'<td class="num"{st}>{_e(tv)}</td></tr>')
    return '<div class="balance"><table><tbody>' + "".join(out) + "</tbody></table></div>"


#: §5: three button kinds and no others.
_BTN = {"p": "btn p", "s": "btn s", "d": "btn d"}


#: A move smaller than this reads as unchanged: the y-window is never tighter
#: than ±this fraction of the level, and the line is toned `dim` rather than
#: gain or loss. 0.1% — below that on a share price is drift, not a move.
_FLAT_BAND = 0.001


def _spark(block: dict) -> str:
    """A price line. The fourth block shape, and the only one not in the design.

    The spec fixes three (§4: table, balance, action) and a chart is genuinely a
    new thing, so it is worth saying why it is here: a share price is the one
    figure on this site whose SHAPE carries information a number cannot. "999.77c"
    and "999.77c, down from 1,004c over three weeks, and falling all month" are
    different facts, and only the second tells a reader whether to act.

    Drawn as inline SVG with no script and no library — the same reason the rest
    of this file emits markup rather than mounting a component. It is a polyline
    over a 0-100 box with `preserveAspectRatio="none"`, so the box stretches to
    whatever width the column gives it and the line stretches with it.

    Direction sets the colour by §1's money rule: last against first, gain up,
    loss down, `dim` when they are equal — flat is not a gain. A series of one
    point draws NO line and says so. One point is not a trend, and a flat line
    across a chart is a specific claim: that the price was steady over the
    window. Drawing that from a single reading would be inventing the window.
    """
    d = block.get("spark") or {}
    pts = [float(v) for v in (d.get("points") or [])]
    unit = str(d.get("unit") or "")
    note = str(d.get("note") or "")
    if len(pts) < 2:
        why = note or "Only one reading on record — not enough for a line."
        return f'<div class="sparkwrap"><div class="bnote">{_e(why)}</div></div>'

    lo, hi = min(pts), max(pts)
    n = len(pts)
    # THE Y-WINDOW HAS A FLOOR, AND THIS IS THE WHOLE POINT OF IT. Scaling a
    # series to its own min and max means the vertical axis always fills, so a
    # move of any size looks the same size. The index moved 0.40 on 1,227 — three
    # hundredths of one per cent — and rendered as a cliff off the top of the
    # box. The chart invented a crash that did not happen.
    #
    # So the window covers at least ±_FLAT_BAND of the level. A move smaller than
    # that draws as the nearly-flat line it is; a real one still fills the box,
    # because once the true span is wider than the floor the floor stops
    # applying. The caption keeps quoting the exact figures either way — this
    # changes what the SHAPE claims, never what the numbers say.
    level = (hi + lo) / 2.0
    span = hi - lo
    floor = abs(level) * _FLAT_BAND * 2.0
    if span < floor:
        pad = (floor - span) / 2.0
        lo, hi = lo - pad, hi + pad
        span = floor
    span = span or 1.0
    # y is inverted: SVG grows downward and a price does not.
    coords = " ".join(
        "%.2f,%.2f" % (i * 100.0 / (n - 1), 28.0 - ((v - lo) / span) * 26.0 - 1.0)
        for i, v in enumerate(pts))
    first, last = pts[0], pts[-1]
    change = last - first
    pct = (change / first * 100.0) if first else 0.0
    # Colour is a verdict, and a drift of a few hundredths of a per cent is not
    # one. Under the flat band it reads unchanged — §1's rule that flat is never
    # a gain, applied to the other end: flat is not a loss either. A red line
    # for -0.03% tells a holder something is wrong when nothing is.
    if abs(pct) < _FLAT_BAND * 100.0:
        tone, arrow = "var(--dim)", "="
    elif change > 0:
        tone, arrow = "var(--gain)", "▲"
    else:
        tone, arrow = "var(--loss)", "▼"
    caption = (f"{arrow} {change:+,.2f}{unit} ({pct:+,.2f}%) "
               f"over {_e(str(d.get('window') or f'{n} readings'))}")
    scale = (f'<span class="skhi">{hi:,.2f}{unit}</span>'
             f'<span class="sklo">{lo:,.2f}{unit}</span>')
    # `src` makes the chart LIVE: the page re-fetches that endpoint and redraws
    # in place. Server-rendered first, always — the line is correct before any
    # script runs, so a reader with a blocked or slow script sees a real chart
    # rather than an empty box that would have been filled in.
    src = f' data-src="{_e(str(d["src"]))}"' if d.get("src") else ""
    unit_attr = f' data-unit="{_e(unit)}"' if unit else ""

    # MARKED POINTS ARE TRADES. Everything else on this line is the model
    # repricing the share — a filed report, a reversion, a parameter change. On
    # an exchange where every print is a trade the distinction never comes up;
    # here three of GreyHames' eighty-two points are trades, so an unmarked line
    # implies eighty of them.
    def _y(v):
        return 28.0 - ((v - lo) / span) * 26.0 - 1.0

    dots = []
    for m in (d.get("marks") or []):
        try:
            i = int(m["i"])
            if not (0 <= i < n):
                continue
            colour = "var(--gain)" if m.get("kind") == "buy" else "var(--loss)"
            dots.append('<circle cx="%.2f" cy="%.2f" r="0.9" fill="%s" '
                        'vector-effect="non-scaling-stroke"/>'
                        % (i * 100.0 / (n - 1), _y(pts[i]), colour))
        except (KeyError, TypeError, ValueError):
            continue

    rules = "".join(
        '<line x1="0" y1="%.1f" x2="100" y2="%.1f" stroke="var(--line)" '
        'stroke-width="0.4" vector-effect="non-scaling-stroke"/>' % (y, y)
        for y in (1.0, 14.0, 27.0))

    svg = (f'<svg class="spark" viewBox="0 0 100 28" preserveAspectRatio="none" '
           f'role="img" aria-label="{_e(caption)}"{src}{unit_attr}>'
           f'{rules}'
           f'<polyline points="{coords}" fill="none" stroke="{tone}" '
           f'stroke-width="1.2" vector-effect="non-scaling-stroke" '
           f'stroke-linejoin="round" stroke-linecap="round"/>'
           f'{"".join(dots)}</svg>')
    foot = f'<div class="bnote">{_e(note)}</div>' if note else ""

    # The legend only appears where a trade actually did, so a market nobody has
    # traded does not carry a key to marks it has none of.
    legend = ""
    trades = int(d.get("trades") or 0)
    if trades:
        legend = ('<div class="sklegend">'
                  '<span><i style="background:var(--gain)"></i>a buy</span>'
                  '<span><i style="background:var(--loss)"></i>a sell</span>'
                  '<span class="skdim">%d trade%s in this window · every other step '
                  'is the model repricing</span></div>'
                  % (trades, "" if trades == 1 else "s"))

    # Filled by the page script on hover: the point under the pointer, and what
    # moved it. Server-rendered empty rather than absent, so the row does not
    # appear and shift the page down on first hover.
    read = ('<div class="skread"><span class="skwhen">&nbsp;</span>'
            '<span class="skprice"></span><span class="skwhy"></span></div>')

    # The live price, above the line, updated by the same refresh that redraws
    # it. Rendering it into the block HEADING instead would mean the heading
    # says one price and the chart's last point says another the moment one
    # refreshes and the other cannot.
    now = ""
    if d.get("live"):
        now = ('<div class="sknow" data-mid="%s"><span class="sknowv">%s%s</span>'
               '<span class="sknowl">a share</span></div>'
               % (_e(str(d.get("mid") or "")), f"{last:,.2f}", _e(unit)))

    tf = ""
    if d.get("src"):
        # Timeframes re-fetch the same endpoint with a different window. The
        # served one is marked so the page opens on a range that is already
        # drawn rather than blank until the first fetch returns.
        served = int(d.get("days") or 0)
        spans = [(7, "1W"), (30, "1M"), (90, "3M"), (365, "1Y")]
        tf = '<div class="sktf">' + "".join(
            '<button type="button" class="sktfb%s" data-days="%d">%s</button>'
            % (" on" if days == served else "", days, label)
            for days, label in spans) + "</div>"

    # The series the page was SERVED, so hovering works before the first refresh
    # rather than after sixty seconds. JSON in a script tag, not a data
    # attribute: eighty points of timestamps and reasons is not an attribute.
    import json as _json
    payload = _json.dumps({"points": pts, "at": d.get("at") or [],
                           "why": d.get("why") or [],
                           "marks": d.get("marks") or []},
                          separators=(",", ":"))
    # `</` cannot appear inside a script element; nothing here should contain it,
    # and escaping it costs nothing if a reason string ever does.
    payload = payload.replace("</", "<\\/")
    data = f'<script type="application/json" class="skdata">{payload}</script>'

    return (f'<div class="sparkwrap">{now}{tf}{svg}'
            f'<div class="skmeta"><span style="color:{tone}">{_e(caption)}</span>'
            f'{scale}</div>{read}{legend}{foot}{data}</div>')


def _action(block: dict) -> str:
    """An action block. A button may carry a third element: where it goes.

    The design's buttons are inert, because the design is a picture. A live
    screen that offers "Open the auction room" and does nothing when clicked is
    worse than one that offers nothing, so `[label, kind, href]` renders an
    anchor styled as the same button. Two elements still render a plain button —
    every screen written against the old shape is unchanged.
    """
    out = []
    for btn in (block.get("btns") or []):
        label, kind = btn[0], btn[1]
        href = btn[2] if len(btn) > 2 else ""
        cls = _BTN.get(kind, "btn s")
        if href:
            out.append(f'<a class="{cls}" href="{_e(href)}">{_e(label)}</a>')
        else:
            out.append(f'<button class="{cls}" type="button">{_e(label)}</button>')
    btns = "".join(out)
    act = f'<p class="act">{_e(block.get("act", ""))}</p>' if block.get("act") else ""
    note = f'<div class="bnote">{_e(block["n"])}</div>' if block.get("n") else ""
    return f'<div class="actionblock">{act}<div class="btnrow">{btns}</div>{note}</div>'


def block_id(heading) -> str:
    """A stable anchor for a block, from its heading.

    The nav's sub-entries are anchor jumps "to that screen's own blocks, by
    block heading" (§3), which needs the heading and the anchor to be derivable
    from each other without a second list to keep in step. Lowercase, spaces to
    hyphens, everything else dropped.
    """
    out = []
    for ch in str(heading or "").lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")


def _ticket(block: dict) -> str:
    """The buy/sell ticket. The fifth block shape, and the first one that WRITES.

    Why it is a block rather than a page: the figures a trader confirms are the
    figures already on the screen — the price, what he holds, the grade. Sending
    him to a separate ticket means re-deriving those somewhere else, and the
    first time the two disagree the one he confirmed is the wrong one.

    THE FIGURES SHOWN ARE THE FIGURES SENT. `quote_price` and a 5% band go with
    the order, and the engine refuses on slippage rather than filling at whatever
    the price became — there was no cap at all before that existed, and a whale
    moving the mid 100 -> 120 between quote and execute charged 1.22x the
    displayed figure. This ticket does not re-quote; it hands over what the page
    already said.

    No markup here decides anything. Every check is the server's: session, CSRF,
    the bounds, the idempotency key, and whether the shares exist to sell.
    """
    t = block.get("ticket") or {}
    price = float(t.get("price") or 0)
    held = float(t.get("you_hold") or 0)
    mid = str(t.get("market_id") or "")
    return (
        '<div class="ticket" data-mid="%s" data-price="%s" data-held="%s" '
        'data-csrf="%s">'
        '<div class="tkrow">'
        '<label class="tklab" for="tkq-%s">Shares</label>'
        '<input class="tkq" id="tkq-%s" type="number" min="1" step="1" value="1" '
        'inputmode="numeric">'
        '<button class="btn p tkbuy" type="button">Buy</button>'
        '<button class="btn s tksell" type="button"%s>Sell</button>'
        '</div>'
        '<div class="tkest"></div>'
        '<div class="tkhint">%s</div>'
        '</div>'
    ) % (
        _e(mid), _e("%.4f" % price), _e("%.4f" % held), _e(str(t.get("csrf") or "")),
        _e(mid), _e(mid),
        "" if held > 0 else " disabled",
        _e(str(t.get("hint") or "")),
    )


def _bidbox(block: dict) -> str:
    """A bid. Same shape as the trade ticket and the same rule behind it: the
    figures a bidder confirms are the ones on the row above.

    A BID IS A HOLD. The coins stay in the wallet, reserved so they cannot be
    spent twice, and are released the moment somebody outbids. Every surface that
    shows a bid has to say that rather than imply it, so the button's own hint
    does — and the preview says it again as arithmetic, available before against
    available after.
    """
    b = block.get("bid") or {}
    lot = str(b.get("lot_id") or "")
    return (
        '<div class="bidbox" data-lot="%s" data-min="%s" data-key="%s" '
        'data-csrf="%s" data-title="%s">'
        '<div class="tkrow">'
        '<label class="tklab" for="bid-%s">Your bid</label>'
        '<input class="tkq" id="bid-%s" type="number" min="%s" step="1" value="%s" '
        'inputmode="numeric">'
        '<button class="btn p bidgo" type="button">Place a bid</button>'
        '</div><div class="tkhint">%s</div></div>'
    ) % (_e(lot), _e(str(int(b.get("minimum") or 1))), _e(str(b.get("key") or "")),
         _e(str(b.get("csrf") or "")), _e(str(b.get("title") or "")),
         _e(lot), _e(lot), _e(str(int(b.get("minimum") or 1))),
         _e(str(int(b.get("minimum") or 1))),
         _e(str(b.get("hint") or "")))


def _block(block: dict, mine=None) -> str:
    if "ticket" in block:
        inner = _ticket(block)
    elif "bid" in block:
        inner = _bidbox(block)
    elif "spark" in block:
        inner = _spark(block)
    elif "bal" in block:
        inner = _balance(block)
    elif "act" in block or "btns" in block:
        inner = _action(block)
    else:
        inner = _table(block, mine)
    h2 = f'<h2>{_e(block["h2"])}</h2>' if block.get("h2") else ""
    # `ac:1` marks the lead block, which takes the accent top-rule (§4).
    cls = "block lead" if block.get("ac") else "block"
    # Every block is addressable. `scroll-margin-top` is set from the MEASURED
    # header height by the page script (§2 asks for the measurement, not a
    # guessed constant), so a jump lands below the sticky header rather than
    # under it.
    bid = block_id(block.get("h2"))
    idattr = f' id="{_e(bid)}"' if bid else ""
    return f'<section class="{cls}"{idattr}>{h2}{inner}</section>'


def band_html(tiles, three: bool = False) -> str:
    out = []
    for tile in tiles or []:
        k = tile[0] if len(tile) > 0 else ""
        v = tile[1] if len(tile) > 1 else ""
        n = tile[2] if len(tile) > 2 else ""
        tag = tile[3] if len(tile) > 3 else ""
        st = f' style="color:{_TAG[tag]}"' if tag in _TAG else ""
        out.append(f'<div class="tile"><span class="k">{_e(k)}</span>'
                   f'<span class="v"{st}>{_e(v)}</span>'
                   f'<span class="n">{_e(n)}</span></div>')
    cls = "band three" if three else "band four"
    return f'<div class="{cls}">' + "".join(out) + "</div>"


def screen_html(screen: dict, *, owner: bool = False, mine=None) -> str:
    """The body for one canvas screen. `owner` gates `own:1` blocks (§7)."""
    if not screen:
        return '<section class="block"><h2>Not found</h2></section>'
    head = (f'<div class="pagehead"><div><h1>{_e(screen.get("title", ""))}</h1>'
            f'<div class="sub">{_e(screen.get("asof", ""))}</div></div></div>')
    band = ""
    if screen.get("band"):
        band = band_html(screen["band"])
    elif screen.get("band3"):
        band = band_html(screen["band3"], three=True)
    # A SCREEN IS A BAND AND A STACK OF BLOCKS (§4), on every screen. A terminal
    # layout was built here and taken out again: two columns on Exchange and a
    # market page made those two pages read unlike the other eleven, which is a
    # worse cost than the scrolling it saved.
    blocks = "".join(_block(b, mine) for b in screen.get("blocks", [])
                     if owner or not b.get("own"))
    return head + band + blocks


def dock_html(screen: dict) -> str:
    """The sticky-bottom bar, for the one screen that has an in-progress draft."""
    d = screen.get("dock")
    if not d:
        return ""
    pairs = "".join(f'<span class="dk">{_e(k)}</span><span class="dv">{_e(v)}</span>'
                    for k, v in (d.get("kv") or []))
    btns = "".join(f'<button class="{_BTN.get(k, "btn s")}" type="button">{_e(l)}</button>'
                   for l, k in (d.get("btns") or []))
    note = f'<span class="dn">{_e(d.get("n", ""))}</span>' if d.get("n") else ""
    return (f'<div class="dockbar"><span class="dt">{_e(d.get("t", ""))}</span>'
            f'{pairs}{note}<span class="dspace"></span>{btns}</div>')
