"""
abex_theme.py — the Abex Tech design system. Tokens and component classes in one place.

**Warm Feel is the only skin, and that is a decision, not a gap.** The design ships two —
Warm Feel and Dark Green — and John picked Warm Feel and only Warm Feel (25 Aug 2026). Do
not port Dark Green and do not build a switcher: two skins is two of every colour decision
to keep in step, and a token that is right in one and wrong in the other is a wrong figure
on a money page half the time. The old Dark Green port is in git history if it is ever
wanted back.

TYPE SCALE, FOUR SIZES, 30 Aug 2026: 15 / 18 / 23 / 28, and nothing else.
Body 18, secondary 15 (labels, notes, metas, buttons, footers), H2 and every
band or page figure 23, H1 28. `th`, `td`, `.sub`, `.meta`, `.empty` and the
buttons are all set EXPLICITLY, because none of them inherits a size.

The history is worth keeping, because the ramp has now been wrong in both
directions. It was first sized from one screen read in isolation ("bigger and
more readable", 15 -> 18px base) and on a real page — a chart, three tables and
a ticket — that read as shouting; players coped by viewing
the site at 80% browser zoom, which is a measurement and not an opinion. So it came down to a
15px body and a 26px H1. That overshot the other way at the new density, and
the ten-step ramp it left behind was the real problem in both versions: a
stylesheet with ten sizes has no scale, it has ten decisions. Four does.

The live page renders whatever loads LAST. `vt_web_shell._LEGACY_CSS` used to
re-declare h1 at 40px and td at 21px right-aligned, over the top of this file —
so measuring the site measured that sheet, not this one. Those overrides are
being removed; the scale here is the one that is meant to win.

If a page feels cramped the answer is space between blocks, not larger type.

What Warm Feel is: a bank statement for a Minecraft economy. Flat ground, no panel fills,
serif throughout, one gold accent for anything you can click. The class names never
changed across the port, so every screen renders unaltered.

What moved, and why it matters when reading a screen:

* **Nothing is a box.** A panel is a rule and some space. `--surface` is transparent on
  purpose — a fill here would put a card back on the page.
* **No monospace.** Georgia sets figures too, with tabular numerals. `.num` still exists
  and still aligns; it just is not a different face.
* **Uppercase is gone.** Field labels, table headers and section headings are sentence
  case. Caps on every label was the loudest tell in the version John rejected.
* **A grade is text, not a chip.** `grade_chip()` in `abex_shell` renders coloured bold
  text. The filled pill is a Dark Green affordance and this product does not have one.
* `--accent` (#c9b37a) is interactive: links, the active nav mark, primary buttons.
  `--mark` marks the LEAD panel on a screen. It is one neutral tone site-wide: it used
  to be a hue per section (blue Exchange, teal Markets, orange Work), which is an
  Overhaul-A-Ledger affordance the Warm Feel spec supersedes -- the accent changed as
  you navigated and the site stopped reading as one thing. It appears as a 2px rule and
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
    # ONE TONE. These were eleven hues -- blue Banking, sky Exchange, teal Markets,
    # mint My market, orange Work, yellow Claims -- painted as a 2px rule on each
    # screen's lead panel and handed to `abex_data` as literal cell colours. That is
    # an Overhaul-A-Ledger affordance the Warm Feel spec supersedes: the accent
    # changed as you navigated, so Banking read as a different app from Work and the
    # site had no colour identity. The `[data-domain]` CSS overrides are already gone;
    # the dict is kept, and flattened, so a caller that still asks for a section's
    # colour gets the ordinary text tone instead of reintroducing a hue.
    k: "var(--text)" for k in (
        "hub", "banking", "exchange", "markets", "mymarket", "stocks",
        "lands", "auctions", "work", "messages", "history")
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
  --text:#efece5; --dim:#aaa59b; --faint:#aaa59b; --inert:#8b8780;
  --gain:#8fbf6a; --loss:#d87a6a; --held:#c3bdb0; --warn:#d87a6a;
  --accent:#c9b37a;                 /* interactive: links, nav mark, buttons */
  --mark:#6f6c66;                   /* the lead panel's rule. ONE tone, site-wide. */
  --ui:Georgia,'Times New Roman',serif;
  --mono:Georgia,'Times New Roman',serif;
  /* ONE measure for the whole page. `main` used to be 1640px while `table` is
     width:auto, so a short page drew three different right edges: the band rule
     at 1640, a panel rule at 1640 and a table ending 700px short of both.
     1180px is a broker's column — main, the top bar, the header strip, the
     footer and the dock all resolve to this same content box, centred. */
  --measure:1180px; --gutter:40px;
}
/* --mark is not interactive and is deliberately NOT the accent: the accent means
   "you can click this", and spending it on a decorative rule spends that meaning.
   Nothing changes per section any more. Two interactive colours on
   one page means neither of them reads as "you can click this". */

*{box-sizing:border-box;margin:0;padding:0}
html{color-scheme:dark;background:#1b1d20}
body{
  display:block;min-height:100vh;
  background:var(--ground);
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

/* -- top bar -------- */
/* THE 326px RAIL IS GONE. Registries and brokerages — Companies House, Nasdaq,
   Deutsche Boerse, IBKR, Schwab, Finviz, GOV.UK — put sections in a horizontal
   top bar and per-record sub-sections in a tab strip under the record's own
   heading. None of them spends a permanent quarter of the viewport on a list of
   ten words that cannot fill it, and this list cannot either.

   Gone with it: `border-left:3px solid var(--inert)` on every item and the
   `box-shadow:inset 19px 0 0 -18px` fake strip on every sub. Ten strips down the
   rail, one of which encoded state. A decoration that looks like a state marker
   and is not one is worse than no marker.

   What marks the current page now is a 2px accent rule UNDER THE LABEL — the
   same mark `.tab` already uses, so the bar and the sub strip speak once. */
.topbar{border-bottom:1px solid var(--line);padding:0 var(--gutter)}
.topbar .bar{max-width:var(--measure);margin:0 auto;display:flex;
  align-items:baseline;gap:34px;flex-wrap:wrap;padding:15px 0 13px}
/* A wordmark, not a masthead: the hairline-and-tagline lockup was drawn for a
   column 326px wide and has nowhere to sit in a 40px-tall bar. */
.brand{display:flex;align-items:baseline;text-decoration:none;color:inherit}
.brand .wordmark{font-size:23px;font-weight:600;letter-spacing:.01em}
.topbar .navtree{display:flex;align-items:baseline;gap:26px;flex-wrap:wrap}
.navgroup{display:flex;align-items:baseline;gap:26px;flex-wrap:wrap}
.navgroup>.glabel{font-size:15px;color:var(--faint);font-weight:400}
.navitem{display:inline-block;padding:2px 0;font-size:18px;color:var(--dim);
  text-decoration:none;border-bottom:2px solid transparent;
  transition:color .14s ease}
.navitem:hover{color:var(--text);text-decoration:none}
/* The page you are ON takes the accent rule. The SECTION you are inside, when
   the page is one of its children, only lifts to full text colour — the child's
   own tab in the strip below carries the accent, and two accent rules on one
   screen means neither of them says "here". */
.navitem[aria-current="page"]{color:var(--text);border-bottom-color:var(--accent)}
.navitem[aria-current="true"]{color:var(--text)}
.navitem .meta{margin-left:7px;font-variant-numeric:tabular-nums;
  font-size:15px;color:var(--inert)}
.topbar .who{margin-left:auto;font-size:15px;color:var(--dim)}

/* -- sub-section strip -------- */
/* Sub-pages are not rows in the bar. They are a tab strip the page prints under
   its own H1, which is where a record's sub-sections live everywhere this was
   researched. Same vocabulary as `.tabs`, because it is the same object. */
.subnav{display:flex;align-items:center;gap:24px;border-bottom:1px solid var(--line);
  margin:-12px 0 26px;flex-wrap:wrap;max-width:var(--measure)}
.navsub{padding:8px 0;margin-bottom:-1px;font-size:18px;color:var(--dim);
  text-decoration:none;border-bottom:2px solid transparent}
.navsub:hover{color:var(--text);text-decoration:none}
.navsub[aria-current="page"]{color:var(--text);border-bottom-color:var(--accent)}
.navsub .meta{margin-left:7px;font-variant-numeric:tabular-nums;
  font-size:15px;color:var(--inert)}

/* -- main column -------- */
.col{min-width:0;display:flex;flex-direction:column}
/* The header sits on the page ground, not on a blurred panel: there is no second
   surface in this skin to blur against. */
.top{position:sticky;top:0;z-index:20;
  background:var(--ground);
  border-bottom:1px solid var(--line);
  max-width:calc(var(--measure) + var(--gutter) * 2);margin:0 auto;width:100%;
  padding:26px var(--gutter) 22px;display:flex;align-items:center;gap:30px;
  flex-wrap:wrap}
.top .stat{display:flex;flex-direction:column;gap:1px}
.top .stat .k{font-size:15px;color:var(--faint);font-weight:400}
.top .stat .v{font-family:var(--mono);font-variant-numeric:tabular-nums;
  font-size:18px;font-weight:600}
.top .right{margin-left:auto;display:flex;align-items:center;gap:14px}
.who{font-size:15px;color:var(--dim);line-height:1.5}
main{padding:36px var(--gutter) 80px;
  max-width:calc(var(--measure) + var(--gutter) * 2);width:100%;margin:0 auto}

/* -- page head -------- */
.pagehead{display:flex;align-items:flex-start;gap:20px;flex-wrap:wrap;margin-bottom:28px}
h1{font-size:28px;font-weight:400;text-wrap:balance}
.pagehead .sub{font-size:15px;color:var(--dim);margin-top:4px;max-width:78ch;
  text-wrap:pretty}
/* A wrapping flex row with space-between drops this mid-row without the auto margin. */
.pagehead .figure{margin-left:auto;text-align:right}
.pagehead .figure .big{font-family:var(--mono);font-variant-numeric:tabular-nums;
  font-size:23px;font-weight:600}
.pagehead .figure .note{font-size:15px;color:var(--faint)}

/* Sentence case, at heading size. This is the single loudest difference from the
   rejected version, and it costs nothing. */
h2,.h2{font-size:23px;font-weight:400;color:var(--text);margin-bottom:10px}

/* -- stat band: rule-separated, no fills -------- */
.band{display:flex;flex-wrap:wrap;row-gap:20px;align-items:flex-start;
  background:none;border:none;padding-bottom:22px;max-width:var(--measure);
  border-bottom:1px solid var(--line);margin-bottom:34px}
.band.four .tile,.band.three .tile{flex:1 1 200px}
.band .tile{background:none;padding:0 26px;min-width:0;display:flex;
  flex-direction:column;gap:4px;border-right:1px solid var(--line)}
.band .tile:first-child{padding-left:0}
.band .tile:last-child{border-right:none}
.band .k{font-size:15px;color:var(--faint);font-weight:400}
.band .v{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:23px;
  font-weight:600}
.band .n{font-size:15px;color:var(--faint);text-wrap:pretty}

/* -- panels -------- */
.panel{background:none;border:none;padding:0;margin-bottom:34px;
  max-width:var(--measure)}
.panel + .panel{border-top:1px solid var(--line);padding-top:20px}
/* One panel per screen carries the section's hue. More than one and it stops
   meaning "this is the lead". */
.panel.accented{box-shadow:inset 0 2px 0 var(--mark);padding-top:16px;border-top:none}
.grid{display:grid;gap:34px}
/* A table needs 640px before it will sit in a column without clipping, so a
   two-up split only happens when both halves can actually hold one. Since the
   measure came down to 1180px, two halves are ~573px and this NEVER splits any
   more — deliberately. One measure means one column of tables; a page that
   wants two things side by side wants two pages. */
.grid.two{grid-template-columns:repeat(auto-fit,minmax(660px,1fr))}

/* -- tables -------- */
.tablewrap{overflow-x:auto;max-width:var(--measure);scrollbar-width:thin;
  scrollbar-color:var(--line-up) var(--ground)}
/* COLUMNS ARE SIZED TO CONTENT, NOT STRETCHED TO THE PAGE. `width:100%` inside a
   1640px main put a six-column table across ~1520px, which is 100px+ of dead air
   between every pair of columns — the eye has to travel from a label to a figure
   that is nowhere near it, and no amount of type work fixes that. A table is as
   wide as what is in it and sits left. `min-width:640px` went with it: it was
   what forced a narrow viewport to scroll sideways.
   Anchor: IBKR's commission schedule, a vertical stack of small content-width
   tables rather than one wide grid. */
/* ONE MEASURE, HONOURED BY EVERYTHING. `width:auto` left an 8-column table ending
   350px short of the rule drawn above it, so every short page had two right edges and
   the eye read the gap as truncation -- the same fault as the empty sidebar, moved to
   the other side. A rule and the content under it must end together. */
table{border-collapse:collapse;width:100%;max-width:100%;
  /* Georgia serves OLD-STYLE figures by default in several renderers: 3, 4, 7 and
     9 hang below the baseline and 6, 8 rise above it. Mixed-height digits are
     half of why a numeric column reads as ragged even when it is aligned.
     `lining-nums` levels them, `tabular-nums` makes every digit the same width so
     the columns line up down the page. On the whole table, not just `.num` —
     a year, an id or a count in a text column is a figure too. */
  font-variant-numeric:tabular-nums lining-nums}
/* One gutter everywhere, on the right, so every column starts where the eye
   expects. The last cell gets none — trailing padding on the final column is
   invisible air that widens the table for nothing. */
th,td{padding-right:28px}
th:last-child,td:last-child{padding-right:0}
th{text-align:left;font-size:18px;font-weight:400;color:var(--faint);
  padding-top:8px;padding-bottom:8px;padding-left:0;
  border-bottom:1px solid var(--line);white-space:nowrap}
td{padding-top:8px;padding-bottom:8px;padding-left:0;
  border-bottom:1px solid var(--line);font-size:18px;line-height:1.3}
td.num,th.num{text-align:right;font-family:var(--mono);white-space:nowrap}
tbody tr:hover td{background:var(--raised)}
tr.clickable{cursor:pointer}
.tfoot{padding:9px 0 0;font-size:15px;color:var(--faint)}

/* -- grade -------- */
/* Text, not a badge. The colour is the grade; the box was decoration. */
.grade{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:18px;
  font-weight:600;display:inline-block;white-space:nowrap}

/* -- tabs -------- */
.tabs{display:flex;align-items:center;gap:24px;border-bottom:1px solid var(--line);
  margin-bottom:24px;flex-wrap:wrap}
.tab{padding:8px 0;margin-bottom:-1px;font-size:18px;color:var(--dim);
  text-decoration:none;border-bottom:2px solid transparent}
.tab:hover{color:var(--text);text-decoration:none}
.tab[aria-current="page"]{color:var(--text);border-bottom-color:var(--accent)}
.tabs .status{margin-left:auto;font-size:15px;color:var(--faint);padding:8px 0}

/* -- filters -------- */
/* Words you can click. A row of bordered pills is a chip row, and this skin
   does not have chips. */
.chip{padding:0;border:none;font-size:18px;color:var(--dim);text-decoration:none}
.chip:hover{color:var(--text)}
.chip[aria-pressed="true"]{background:none;color:var(--accent);
  text-decoration:underline;text-underline-offset:3px}

/* -- actions -------- */
/* AN ACTION IS A WORD, NOT A SLAB. The Hub already rendered "Claim" as a plain accent
   word while Work rendered the same action as a filled gold block - the same control
   styled two ways, which is the inspection-level giveaway. Gold as a SURFACE is also
   the "gold on dark = casino" case; gold as INK is the sanctioned use, and the accent
   has one job: this is a thing you can click.
   `.btnlink` is that word, and it must work on a <button> as well as an <a>, because
   half the site's actions post a form. So the button's own chrome is stripped back to
   nothing and the text carries the affordance. */
.btnlink{display:inline;padding:0;margin:0;border:none;background:none;
  font:inherit;font-size:inherit;color:var(--accent);cursor:pointer;
  text-decoration:underline;text-underline-offset:3px;
  text-decoration-thickness:1px;text-decoration-color:rgba(201,179,122,.45)}
.btnlink:hover{text-decoration-color:var(--accent)}
.btnlink.quiet{color:var(--dim);text-decoration-color:var(--line)}
.btnlink.quiet:hover{color:var(--text);text-decoration-color:var(--line-up)}
.btnlink.danger{color:var(--loss);text-decoration-color:rgba(216,122,106,.45)}
.btnlink.danger:hover{text-decoration-color:var(--loss)}
/* Every state designed, not just hover: a bare <button> loses the browser's focus ring
   the moment its border goes, and this is the only route to most actions. */
.btnlink:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.btnlink[disabled]{opacity:.45;cursor:not-allowed;text-decoration:none}
.btnlink+.btnlink{margin-left:18px}

/* `.btn` is retired - kept only so an un-migrated caller degrades to the same word
   rather than to an unstyled OS button on a dark page. */
.btn{display:inline;padding:0;border:none;background:none;font:inherit;
  color:var(--accent);cursor:pointer;text-decoration:underline;
  text-underline-offset:3px;text-decoration-thickness:1px;
  text-decoration-color:rgba(201,179,122,.45)}
.btn:hover{text-decoration-color:var(--accent)}
.btn.ghost{color:var(--dim);text-decoration-color:var(--line)}
.btn.ghost:hover{color:var(--text)}
.btn.danger{color:var(--loss);text-decoration-color:rgba(216,122,106,.45)}
.btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.btn[disabled]{opacity:.45;cursor:not-allowed;text-decoration:none}

/* -- docked draft bar -------- */
.dock{position:sticky;bottom:0;z-index:15;background:var(--ground);
  border-top:1px solid var(--line);box-shadow:none;
  max-width:calc(var(--measure) + var(--gutter) * 2);margin:0 auto;width:100%;
  padding:12px var(--gutter);display:flex;align-items:center;gap:26px;
  flex-wrap:wrap}
.dock .kv{display:flex;flex-direction:column;gap:1px}
.dock .kv .k{font-size:15px;color:var(--faint);font-weight:400}
.dock .kv .v{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:18px;
  font-weight:600}
.dock .actions{margin-left:auto;display:flex;align-items:center;gap:9px}

/* Empty is empty: one line, no placeholder rows. */
.empty{padding:6px 0;color:var(--faint);font-size:18px}

/* The toggle exists only on a narrow viewport - on the desktop sidebar the tree
   is simply always there, which is what §2 describes. */
.navtoggle{display:none}
.navtree{display:block}
.topbar .navtoggle{font-size:18px}

@media(max-width:900px){
  /* §2: below the breakpoint the sidebar becomes a single always-visible top bar
     with a "current screen" toggle that expands the full nav INLINE. Not a
     drawer and not an overlay - the design is explicit about that, and an
     overlay on a page of figures hides the figures.

     The wall of tabs this used to become was worse than either: fourteen inline
     entries wrapped over four rows on a phone, so every page opened with a
     screenful of nav above the first number. */
  .navtoggle{display:flex;align-items:center;gap:8px;width:100%;
    margin:2px 0 0;padding:8px 0;background:none;cursor:pointer;
    border:none;border-radius:0;
    color:var(--text);font:inherit;font-size:18px;text-align:left}
  .navtoggle .chev{color:var(--accent);transition:transform .12s ease}
  .navtoggle[aria-expanded="true"] .chev{transform:rotate(180deg)}
  .navtree{display:none;padding-top:6px}
  .navtree.open{display:block}
  .topbar{padding:0 20px}
  .topbar .bar{padding:12px 0 10px;gap:14px}
  /* `.topbar .navtree{display:flex}` above is two classes deep, so the bare
     `.navtree{display:none}` on the line above cannot switch it off — the tree
     would simply always be open on a phone. Matched specificity, both ways. */
  .topbar .navtree{display:none;width:100%}
  .topbar .navtree.open{display:block}
  .topbar .navtree .navgroup{flex-direction:column;align-items:stretch;gap:0}
  .topbar .navtree .navitem{display:block;padding:7px 0}
  .topbar .who{margin-left:0;width:100%}
  .navgroup>.glabel{display:none}
  main{padding:22px 20px 60px}
  .top{padding:18px 20px;gap:22px;row-gap:12px}
  .dock{padding:12px 20px}
  .band .tile{padding:0 18px}
}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

FONTS_LINK = ""  # Georgia is a system serif; nothing to fetch
