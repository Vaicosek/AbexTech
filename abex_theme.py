"""
abex_theme.py — the Abex Tech design system. Tokens and component classes in one place.

Ported to the **Warm Feel** skin, which is `Abex Tech Screens.dc.html`'s own default and
the direction John picked: a bank statement for a Minecraft economy. Flat ground, no panel
fills, serif throughout, one gold accent for anything you can click. The Dark Green skin
this file used to carry is in git history; the class names did not change, so every screen
built against it renders unaltered.

What moved, and why it matters when reading a screen:

* **Nothing is a box.** A panel is a rule and some space. `--surface` is transparent on
  purpose — a fill here would put a card back on the page.
* **No monospace.** Georgia sets figures too, with tabular numerals. `.num` still exists
  and still aligns; it just is not a different face.
* **Uppercase is gone.** Field labels, table headers and section headings are sentence
  case. Caps on every label was the loudest tell in the version John rejected.
* **A grade is text, not a chip.** `grade_chip()` in `abex_shell` renders coloured bold
  text; the filled pill belongs to the other skin.
* `--accent` (#c9b37a) is interactive: links, the active nav mark, primary buttons.
  `--mark` is the section's own hue and appears as a 2px rule on one panel per screen and
  nowhere else.

USE
    from abex_theme import THEME_CSS, DOMAINS, accent
    page = f"<style>{THEME_CSS}</style>" + body
    # per-section accent: put data-domain on <body> or any wrapper
    <body data-domain="banking">
"""
from __future__ import annotations

#: Section hues, from the mockup's warm `WA()` set. These mark a section; they are
#: never a fill and never carry meaning about money.
DOMAINS: dict[str, str] = {
    "hub":      "#eeeeee",
    "banking":  "#26b1ff",
    "exchange": "#81d2ff",
    "markets":  "#18a07b",
    "mymarket": "#52d9b4",
    "stocks":   "#81d2ff",
    "lands":    "#e3dc7d",
    "auctions": "#edaf23",
    "betting":  "#9b6b93",
    "work":     "#c06117",
    "messages": "#d0c2b8",
    "history":  "#6a6a6a",
}

#: The one interactive colour. Links, active nav mark, primary buttons.
ACCENT = "#c9b37a"

#: Reserved semantics — never used decoratively, never per-section. Warm Feel collapses
#: warning into loss deliberately: there is no separate amber in this skin.
GAIN = "#8fbf6a"
LOSS = "#d87a6a"
WARN = "#d87a6a"
HELD = "#c3bdb0"     # money reserved in escrow: parked, not lost — never red
INERT = "#6f6c66"    # a dormant or empty state. Matches --inert in THEME_CSS,
                     # which existed while Python had no name for it, so screens
                     # reached for stray literals (#6A6A6A, #B4B4B4) instead.

#: Grade colour ramp, from the mockup's `gradeColor()`. Investment grade starts at BBB.
#: A and BBB share a colour there and share one here; changing that is John's call.
GRADES: dict[str, str] = {
    "AAA": GAIN,   "AA": "#a3c47a", "A": ACCENT, "BBB": ACCENT,
    "BB":  WARN,   "B":  WARN,      "CCC": LOSS, "CC": LOSS,
    "C":   LOSS,   "D":  LOSS,
}


def accent(domain: str) -> str:
    return DOMAINS.get(domain, DOMAINS["hub"])


#: Money direction by LABEL, from the mockup's `moneyTone()`.
#:
#: The mockup calls this "one rule, shared with the site". It was not shared: the rule
#: existed only in the mockup, and the site colours figures per call site (a hardcoded
#: tone map in `abex_screens`, for one). N call sites deciding the same thing
#: separately is how a figure ends up green on one screen and plain on the next.
#:
#: Ported verbatim, ANCHORING AND ALL. Several of these are exact-match on purpose and
#: the near-misses are not oversights to tidy up: "Owed" is warn but "Owed to you" is
#: money coming TO the reader, and "Vault" is held but "Vault retention (10%)" is a
#: deduction. Where the mockup wanted those coloured it set the tone explicitly on the
#: cell instead. Loosening an anchor here silently recolours the opposite meaning.
#:
#: Returns "" for "no tone" — the caller leaves the figure in the default text colour.
#: An explicit tone on the cell always wins over this.
_MONEY_RULES: tuple[tuple[str, str], ...] = (
    # A deduction line is never coloured: it is already negative in the reading.
    (r"^less\b", ""),
    (r"^held\b|held in|^staked$|^stake$|^vault$|^bonds held$", "HELD"),
    (r"^savings\b|^dividends$|^coupon income$|^estimated", "GAIN"),
    (r"^available|^wallet available$|^revenue$|^confirmed|^money in$|^pa(y|id)\b", "GAIN"),
    (r"^unrealised$|^net for the month$|^to the owner$", "GAIN"),
    (r"^owed$|^bonds issued$|^money out$|^drawn$|^rate$", "WARN"),
)


def money_tone(label: str) -> str:
    """The colour a figure takes from what its label MEANS. "" = leave it plain."""
    import re
    text = str(label or "").strip()
    if not text:
        return ""
    tones = {"HELD": HELD, "GAIN": GAIN, "WARN": WARN, "": ""}
    for pattern, tone in _MONEY_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            return tones[tone]
    return ""


def grade_tone(grade: str) -> str:
    """Colour for a credit grade. Unknown or unrated grades stay plain.

    Unrated is deliberately NOT the loss tone: an unlisted market has no market cap to
    divide by, so it has no grade — and painting fourteen of those red told their
    owners they had failed one.
    """
    return GRADES.get(str(grade or "").strip().upper(), "")


def backing_tone(value) -> str:
    """Colour for a backing multiple, from the mockup's `backingRamp()`.

    Continuous rather than banded, because backing is a ratio and 1.19 vs 1.21 is not
    the difference the colour is there to show.
    """
    try:
        n = float(str(value).strip().rstrip("x×"))
    except (TypeError, ValueError):
        return ""
    if n >= 1.5:
        return GAIN
    if n >= 1.2:
        return "#a3c47a"
    if n >= 1.0:
        return ACCENT
    if n >= 0.6:
        return WARN
    return LOSS


THEME_CSS = r"""
:root{
  /* Warm Feel, from the mockup's own theme() block. */
  --ground:#1b1d20; --surface:transparent; --raised:rgba(239,236,229,.05);
  --line:#3b3e43; --line-up:#4a4e54; --line-hi:#4a4e54;
  --text:#efece5; --dim:#aaa59b; --faint:#aaa59b; --inert:#6f6c66;
  --gain:#8fbf6a; --loss:#d87a6a; --held:#c3bdb0; --warn:#d87a6a;
  --accent:#c9b37a;                 /* interactive: links, nav mark, buttons */
  --mark:#eeeeee;                   /* the section's own hue, one rule per screen */
  --ui:Georgia,'Times New Roman',serif;
  --mono:Georgia,'Times New Roman',serif;
}
/* Only --mark changes per section. --accent never does: two interactive colours on
   one page means neither of them reads as "you can click this". */
[data-domain="hub"]{--mark:#eeeeee}
[data-domain="banking"]{--mark:#26b1ff}
[data-domain="exchange"]{--mark:#81d2ff}
[data-domain="markets"]{--mark:#18a07b}
[data-domain="mymarket"]{--mark:#52d9b4}
[data-domain="stocks"]{--mark:#81d2ff}
[data-domain="lands"]{--mark:#e3dc7d}
[data-domain="auctions"]{--mark:#edaf23}
[data-domain="betting"]{--mark:#9b6b93}
[data-domain="work"]{--mark:#c06117}

*{box-sizing:border-box;margin:0;padding:0}
html{color-scheme:dark;background:#1b1d20}
body{
  display:flex;min-height:100vh;
  background:radial-gradient(#2e3136 1px,transparent 1px) 0 0/22px 22px,var(--ground);
  color:var(--text);font-family:var(--ui);font-size:18px;line-height:1.55;
  -webkit-font-smoothing:subpixel-antialiased;
}
a{color:var(--accent);text-decoration:underline;text-underline-offset:3px;
  text-decoration-thickness:1px;text-decoration-color:rgba(201,179,122,.45)}
a:hover{text-decoration-color:var(--accent)}
button{font:inherit;color:inherit;background:none;border:none;cursor:pointer}
/* Figures are not a different face here — they are the same serif with tabular
   numerals, which is what keeps a column aligned. */
.mono,.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
.gain{color:var(--gain)} .loss{color:var(--loss)} .held{color:var(--held)}
.faint{color:var(--faint)} .dim{color:var(--dim)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* -- sidebar -------- */
.side{width:326px;flex:0 0 326px;background:none;
  border-right:1px solid var(--line);padding:30px 0 18px;position:sticky;top:0;
  height:100vh;overflow-y:auto;scrollbar-width:thin;
  scrollbar-color:var(--line-up) var(--ground)}
.brand{display:flex;flex-direction:column;align-items:center;gap:8px;
  padding:0 18px 20px;text-align:center;text-decoration:none;color:inherit}
.brand .mark{display:block;border:1px solid var(--line-up);padding:7px 13px;
  font-size:19px;font-weight:700;letter-spacing:.10em;color:var(--accent)}
.brand .wordmark{font-size:25px;font-weight:700;letter-spacing:.01em}
.brand .tag{font-size:16px;color:var(--faint)}
.navgroup{padding:14px 0 2px}
.navgroup>.glabel{padding:0 18px 6px;font-size:16px;color:var(--faint);font-weight:400}
.navitem{display:flex;align-items:center;gap:9px;width:100%;text-align:left;
  padding:6px 18px;font-size:21px;color:var(--dim);text-decoration:none;
  border-left:3px solid var(--inert);transition:color .14s ease,background .14s ease}
.navitem:hover{color:var(--text);background:var(--raised);text-decoration:none}
.navitem[aria-current="page"]{color:var(--text);background:none;
  border-left-color:var(--accent)}
.navitem .meta{margin-left:auto;padding-left:10px;font-family:var(--mono);
  font-variant-numeric:tabular-nums;font-size:16px;color:var(--inert)}
/* Sub-entries: the indent MUST live inside the button box, or the sidebar scrolls
   sideways. Hairline is an inset shadow, not a border, for the same reason. */
.navsub{display:flex;align-items:center;width:100%;text-align:left;
  padding:4px 18px 4px 58px;font-size:17px;color:var(--faint);text-decoration:none;
  box-shadow:inset 19px 0 0 -18px var(--line);transition:color .14s ease}
.navsub:hover{color:var(--text);text-decoration:none}
.navsub[aria-current="page"]{color:var(--text);box-shadow:inset 19px 0 0 -18px var(--accent)}
.navsub .meta{margin-left:auto;padding-left:10px;font-family:var(--mono);
  font-variant-numeric:tabular-nums;font-size:14px;color:var(--inert)}

/* -- main column -------- */
.col{flex:1;min-width:0;display:flex;flex-direction:column}
/* The header sits on the page ground, not on a blurred panel: there is no second
   surface in this skin to blur against. */
.top{position:sticky;top:0;z-index:20;
  background:radial-gradient(#2e3136 1px,transparent 1px) 0 0/22px 22px,var(--ground);
  border-bottom:1px solid var(--line);
  padding:30px 60px 24px;display:flex;align-items:center;gap:30px;flex-wrap:wrap}
.top .stat{display:flex;flex-direction:column;gap:1px}
.top .stat .k{font-size:16px;color:var(--faint);font-weight:400}
.top .stat .v{font-family:var(--mono);font-variant-numeric:tabular-nums;
  font-size:18px;font-weight:600}
.top .right{margin-left:auto;display:flex;align-items:center;gap:14px}
.who{font-size:16px;color:var(--dim);line-height:1.5}
main{padding:40px 60px 80px;max-width:1640px;width:100%;margin:0 auto}

/* -- page head -------- */
.pagehead{display:flex;align-items:flex-start;gap:20px;flex-wrap:wrap;margin-bottom:28px}
h1{font-size:34px;font-weight:400;text-wrap:balance}
.pagehead .sub{font-size:17px;color:var(--dim);margin-top:4px;max-width:78ch;
  text-wrap:pretty}
/* A wrapping flex row with space-between drops this mid-row without the auto margin. */
.pagehead .figure{margin-left:auto;text-align:right}
.pagehead .figure .big{font-family:var(--mono);font-variant-numeric:tabular-nums;
  font-size:32px;font-weight:600}
.pagehead .figure .note{font-size:16px;color:var(--faint)}

/* Sentence case, at heading size. This is the single loudest difference from the
   rejected version, and it costs nothing. */
h2,.h2{font-size:24px;font-weight:400;color:var(--text);margin-bottom:10px}

/* -- stat band: rule-separated, no fills -------- */
.band{display:flex;flex-wrap:wrap;row-gap:20px;align-items:flex-start;
  background:none;border:none;padding-bottom:22px;
  border-bottom:1px solid var(--line);margin-bottom:34px}
.band.four .tile,.band.three .tile{flex:1 1 200px}
.band .tile{background:none;padding:0 26px;min-width:0;display:flex;
  flex-direction:column;gap:4px;border-right:1px solid var(--line)}
.band .tile:first-child{padding-left:0}
.band .tile:last-child{border-right:none}
.band .k{font-size:16px;color:var(--faint);font-weight:400}
.band .v{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:28px;
  font-weight:600}
.band .n{font-size:16px;color:var(--faint);text-wrap:pretty}

/* -- panels -------- */
.panel{background:none;border:none;padding:0;margin-bottom:34px}
.panel + .panel{border-top:1px solid var(--line);padding-top:20px}
/* One panel per screen carries the section's hue. More than one and it stops
   meaning "this is the lead". */
.panel.accented{box-shadow:inset 0 2px 0 var(--mark);padding-top:16px;border-top:none}
.grid{display:grid;gap:34px}
/* A table needs 640px before it will sit in a column without clipping, so a
   two-up split only happens when both halves can actually hold one. */
.grid.two{grid-template-columns:repeat(auto-fit,minmax(660px,1fr))}

/* -- tables -------- */
.tablewrap{overflow-x:auto;scrollbar-width:thin;
  scrollbar-color:var(--line-up) var(--ground)}
table{border-collapse:collapse;width:100%;min-width:640px}
th{text-align:left;font-size:18px;font-weight:400;color:var(--faint);
  padding:8px 14px 8px 0;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:8px 14px 8px 0;border-bottom:1px solid var(--line);font-size:18px}
td.num,th.num{text-align:right;font-family:var(--mono);
  font-variant-numeric:tabular-nums;white-space:nowrap;padding-right:24px}
tbody tr:hover td{background:var(--raised)}
tr.clickable{cursor:pointer}
.tfoot{padding:9px 0 0;font-size:16px;color:var(--faint)}

/* -- grade -------- */
/* Text, not a badge. The colour is the grade; the box was decoration. */
.grade{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:18px;
  font-weight:700;display:inline-block;white-space:nowrap}

/* -- tabs -------- */
.tabs{display:flex;align-items:center;gap:24px;border-bottom:1px solid var(--line);
  margin-bottom:24px;flex-wrap:wrap}
.tab{padding:8px 0;margin-bottom:-1px;font-size:18px;color:var(--dim);
  text-decoration:none;border-bottom:2px solid transparent}
.tab:hover{color:var(--text);text-decoration:none}
.tab[aria-current="page"]{color:var(--text);border-bottom-color:var(--accent)}
.tabs .status{margin-left:auto;font-size:16px;color:var(--faint);padding:8px 0}

/* -- filters -------- */
/* Words you can click. A row of bordered pills is a chip row, and this skin
   does not have chips. */
.chip{padding:0;border:none;font-size:18px;color:var(--dim);text-decoration:none}
.chip:hover{color:var(--text)}
.chip[aria-pressed="true"]{background:none;color:var(--accent);
  text-decoration:underline;text-underline-offset:3px}

/* -- buttons -------- */
.btn{padding:7px 14px;font-size:16px;font-weight:700;background:var(--accent);
  color:var(--ground);border:1px solid var(--accent);text-decoration:none;
  display:inline-block}
.btn:hover{background:#d8c48f;border-color:#d8c48f;text-decoration:none}
.btn.ghost{background:none;border:1px solid var(--line);color:var(--dim);font-weight:400}
.btn.ghost:hover{border-color:var(--line-up);color:var(--text);background:none}
.btn.danger{background:none;border:1px solid var(--loss);color:var(--loss);font-weight:400}
.btn[disabled]{opacity:.45;cursor:not-allowed}

/* -- docked draft bar -------- */
.dock{position:sticky;bottom:0;z-index:15;background:var(--ground);
  border-top:1px solid var(--line);box-shadow:none;
  padding:12px 60px;display:flex;align-items:center;gap:26px;flex-wrap:wrap}
.dock .kv{display:flex;flex-direction:column;gap:1px}
.dock .kv .k{font-size:16px;color:var(--faint);font-weight:400}
.dock .kv .v{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:18px;
  font-weight:600}
.dock .actions{margin-left:auto;display:flex;align-items:center;gap:9px}

/* Empty is empty: one line, no placeholder rows. */
.empty{padding:6px 0;color:var(--faint);font-size:18px}

@media(max-width:900px){
  body{display:block}
  .side{position:static;width:auto;height:auto;flex:none;border-right:none;
    border-bottom:1px solid var(--line);padding:14px 0}
  .brand{align-items:flex-start;text-align:left;padding:0 20px 10px}
  .brand .mark{font-size:17px;padding:5px 11px}
  .navgroup{padding:6px 0 0}
  .navgroup>.glabel{display:none}
  .navitem{display:inline-flex;width:auto;border-left:none;
    border-bottom:2px solid transparent;font-size:18px;padding:4px 12px}
  .navitem[aria-current="page"]{border-bottom-color:var(--accent)}
  .navsub{padding-left:32px;font-size:16px}
  main{padding:22px 20px 60px}
  .top{padding:18px 20px;gap:22px;row-gap:12px}
  .dock{padding:12px 20px}
  .band .tile{padding:0 18px}
}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

FONTS_LINK = ""  # Georgia is a system serif; nothing to fetch
