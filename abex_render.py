"""abex_render.py — turn a canvas screen (`abex_canvas.SCREENS`) into page HTML.

One renderer, thirteen screens. The design describes a screen as data — a band of
tiles and a list of blocks — and the spec fixes exactly three block shapes (§4)
and the order in which a cell's colour is decided (§5). So the screens do not
each need their own page-builder; they need one that obeys those rules, and then
a screen is a dict.

That is the whole point of doing it this way. Hand-writing thirteen screens is
hours of transcription and every hour is a chance to put a number in the wrong
tone — and in a money UI a wrongly-toned figure reads as a fact, not a bug.

## Tone resolution (spec §5, later wins)

    1. base            identity column = bold text, numeric column = plain
    2. inline tag      'g|' gain, 'l|' loss, 'w|' warn, 'm|' faint, 'k|' action,
                       'G|' grade ramp, 'T|<seconds>' live countdown
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
    m = re.match(r"^([glwmkGT])\|(.*)$", cell, re.S)
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


def _cell(head: str, raw, numeric: bool, identity: bool) -> str:
    text = "" if raw is None else str(raw)
    tag, text = _split_tag(text)

    colour, bold = "", identity
    if tag == "G":                       # grade ramp asked for explicitly
        colour = _grade_colour(text)
        bold = True
    elif tag == "T":                     # countdown; rendered live by the page script
        secs = text.strip()
        cls = ' class="num countdown" data-left="%s"' % _e(secs)
        return f"<td{cls}>—</td>"
    elif tag:
        colour = _TAG.get(tag, "")

    hc, hb = _header_rule(head, text)
    if hc and not colour:                # header rule loses to an explicit tag
        colour = hc
    bold = bold or hb

    style = []
    if colour:
        style.append(f"color:{colour}")
    if bold:
        style.append("font-weight:700")
    st = f' style="{";".join(style)}"' if style else ""
    cls = ' class="num"' if numeric else ""
    return f"<td{cls}{st}>{_e(text)}</td>"


def _table(block: dict, mine=None) -> str:
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
    return ('<div class="tablewrap"><table><thead><tr>' + th + "</tr></thead><tbody>"
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


def _block(block: dict, mine=None) -> str:
    if "bal" in block:
        inner = _balance(block)
    elif "act" in block or "btns" in block:
        inner = _action(block)
    else:
        inner = _table(block, mine)
    h2 = f'<h2>{_e(block["h2"])}</h2>' if block.get("h2") else ""
    # `ac:1` marks the lead block, which takes the accent top-rule (§4).
    cls = "block lead" if block.get("ac") else "block"
    return f'<section class="{cls}">{h2}{inner}</section>'


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
