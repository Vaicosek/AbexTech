"""
abex_shell.py — the Abex Tech page shell: top bar, sticky header, main column.

Every section page calls `render()` and passes only its own body. The nav, the header
figures and the accent all come from here, so a new section is one NAV entry plus a
handler — not another copy of the chrome.

    from abex_shell import render, NAV
    return web.Response(text=render("banking.accounts", body_html,
                                    who=("Yulen", "Employee"),
                                    stats=[("Next report", "BNL · in 2 days")]),
                        content_type="text/html")
"""
from __future__ import annotations

import html as _h

from abex_theme import THEME_CSS, FONTS_LINK, GRADES

#: THE BADGE IS GONE, and its history is worth keeping in view because the same
#: mistake has now been made twice in opposite directions.
#:
#: First it was `<img src="/static/atech-logo-circle.png">` carrying
#: `onerror="this.style.display='none'"`, with no /static route, no `static/`
#: directory and no such file ever committed. The 404 hid itself — no broken
#: image, no console complaint, just a silent gap. A fallback that conceals its
#: own failure is worse than no fallback.
#:
#: Then a real asset was drawn and shipped: a gold-on-black ring badge with five
#: labelled feature medallions (BANKING / MARKETS / STOCKS / LANDS / AUCTIONS)
#: orbiting a bevelled gradient "A", over a dot-matrix world map. His own players
#: called it — "ai shit", "and it looks weird still" — and the design brief he
#: had already accepted says, in as many words, NO LOGO MEDALLION. Nobody puts a
#: feature list around the rim of a mark.
#:
#: What replaces it is type, which cannot look generated because it is not art:
#: the wordmark over a hairline rule with the tagline beneath, the way a broker's
#: letterhead is set. It needs no asset, so it cannot 404, and it inherits the
#: page's own serif, so it cannot drift from the rest of the site.
#:
#: `FAVICON_SRC` still points at a raster: a favicon has nowhere to put type at
#: 16px. That one is untouched and unreviewed.
FAVICON_SRC = "/static/favicon.png"

#: The site-wide notice. It states what this platform DOES — never converts
#: coins to money — rather than making a claim about what they are worth, which
#: is not something this software can know or keep. Full wording lives in
#: `terms_web.SECTIONS`; this is the one line that rides every page, and it is
#: imported from there so the two cannot drift apart.
try:
    from terms_web import FOOTER_LINE as _FOOTER_LINE
except Exception:  # terms_web must never be able to take the site down
    _FOOTER_LINE = ("Coins are in-game currency for Discord and Minecraft. "
                    "Abex Tech neither sells nor redeems them for money.")

_FOOTER_HTML = ('<footer class="sitefoot"><p>' + _h.escape(_FOOTER_LINE)
                + ' <a href="/terms">Terms</a>.</p></footer>')

_FOOTER_CSS = """
/* The wordmark-over-hairline-over-tagline masthead was drawn for a 326px column
   and there is no column any more. In a 40px bar it is a wordmark; the rule and
   the tagline are gone rather than shrunk, and their CSS with them.

   The footer had NO horizontal padding at all while `main` had 60px, so the one
   line of small print sat 60px to the left of every other thing on the page —
   the most visible misalignment on the site and the cheapest to fix. It takes
   main's own gutter and main's own measure now, so its left edge and its right
   edge are the page's. */
.sitefoot{border-top:1px solid var(--line);margin:4rem auto 0;
  padding:1.1rem var(--gutter) 2rem;
  max-width:calc(var(--measure) + var(--gutter) * 2);width:100%;
  color:var(--inert);font-size:15px;line-height:1.5}
.sitefoot p{margin:0}
.sitefoot a{color:var(--accent);text-decoration:underline;text-underline-offset:3px;
  text-decoration-thickness:1px;text-decoration-color:rgba(201,179,122,.45)}
.sitefoot a:hover{color:var(--dim)}
"""

#: (key, label, href, domain, meta, [(subkey, label, href, meta), ...])
#:
#: This IS the design's tree - `navTree()` in `Abex Tech Screens.dc.html`, in its
#: order, with its labels and its counts, and the spec's flat shape (§3): one
#: unnamed group, each item optionally expanding to one or two children while it
#: is the active section.
#:
#: It used to be four named groups - Money / Trade / World / You - carrying
#: `Lands` where the design says `Claims`, and no Hub, Exchange, Work, Claims or
#: My market at all. That was a different information architecture, and it is why
#: the live sidebar did not look like the mockup even though the type, the
#: palette and the shell all matched.
#:
#: Betting is deliberately absent: the design has it, the product will not.
#:
#: The hrefs here are the DESIGN's paths. Where a deployment serves a section
#: somewhere else it passes `paths={key: href}` to `render()`, and an entry with
#: no real path is dropped rather than linked to a 404. The counts are the
#: design's too and are overridden by `counts=` wherever the caller knows the
#: live number.
NAV: list[tuple[str, list]] = [
    ("", [
        ("hub",      "Hub",       "/hub",      "hub",      "",   []),
        ("banking",  "Banking",   "/banking",  "banking",  "",   []),
        ("exchange", "Exchange",  "/exchange", "exchange", "", [
            ("stocks", "Stocks", "/stocks", "8"),
        ]),
        ("markets",  "Markets",   "/markets",  "markets",  "13", []),
        ("work",     "Work",      "/work",     "work",     "7", [
            ("orders", "Orders", "/orders", "6"),
        ]),
        # Two auction houses, and the labels have to say which is which: a claim
        # is ground, a lot is goods, and they are separate tables in one listings
        # table (`land_listings.kind`).
        ("auctions", "Auctions",  "/auctions", "auctions", "3",  []),
        ("lands",    "Claims",    "/lands",    "lands",    "2",  []),
        ("mine",     "My market", "/my",       "mymarket", "", [
            ("mine.report", "August report", "/my/report", ""),
        ]),
        ("messages", "Messages",  "/messages", "messages", "3",  []),
        ("history",  "History",   "/history",  "history",  "",   []),
    ]),
]

#: Staff-only group — rendered ONLY for a staff session, server-side. A normal player
#: never receives the markup, so it is not merely hidden with CSS.
STAFF_NAV = ("Staff", [
    ("owner", "Owner console", "/admin", "hub", "4", []),
    ("saleslog", "Sales log", "/admin/sales", "hub", "", []),
])


def domain_for(key: str) -> str:
    root = key.split(".")[0]
    for _g, items in NAV + [STAFF_NAV]:
        for k, _l, _href, dom, _meta, _subs in items:
            if k == root:
                return dom
    return "hub"


def grade_chip(grade: str) -> str:
    """A grade is a fact in a column: coloured bold text, not a filled pill.

    The name is kept because every screen calls it; what it renders changed with
    Warm Feel, the only skin. Sub-investment grades take the loss tone, the only place
    that colour is allowed to appear outside money.
    """
    # A GRADE IS NOT A MONEY FIGURE, SO IT DOES NOT GET THE MONEY COLOURS. Green and
    # red mean "up" and "down"; spending them on a static rating meant a page could
    # carry a green/gold/red grade ramp, a coloured section rule and the gold link
    # accent at once — four colour languages on a page whose brief allows one, and the
    # money colours stopped meaning anything because they were everywhere.
    # `abex_render._GRADE_RAMP` was flattened to `--text` for the live screens; this is
    # the same decision for the static ones, which were rendering the old ramp and
    # making one fact look different depending on which module drew the page.
    # An unknown grade stays muted: "not rated" is not a bad grade, and painting it in
    # the loss tone once told fourteen unlisted markets they were junk.
    colour = "var(--faint)" if str(grade).upper() not in GRADES else "var(--text)"
    return (f'<span class="grade" style="color:{colour}">'
            f'{_h.escape(str(grade))}</span>')


def nav_parts(active: str, staff: bool, available=None, prefix: str = "",
              counts=None, paths=None, subs=None) -> tuple[str, str]:
    """`(top bar row, sub-section strip)` — two separate places on the page.

    THE SUBS ARE NOT ROWS IN THE BAR. A sub-page is a section OF a record, and
    every registry and brokerage that was looked at — Companies House, Nasdaq,
    IBKR, Schwab, GOV.UK — puts those in a tab strip under the record's own
    heading, not in the site nav. So this returns two strings and `render()`
    puts each where it belongs. `_nav_html()` still joins them, because the
    tests and the site's probes address this by `data-k` and both parts carry it.

    The nav tree.

    `available`, when given, is the set of section keys this deployment actually
    mounted. The tree here is the structure and the order; what exists is a
    runtime fact, and a nav that lists a section the server never registered
    sends people to a 404. A group with nothing left in it is dropped entirely
    rather than rendered as an empty heading.

    `paths`, when given, is `{key: href}` — where the deployment actually serves
    that section. The tree's own hrefs are the DESIGN's paths, and the live site
    does not use all of them: the market list is served at `/exchange`, not
    `/markets`, so the tree sent every logged-out visitor who clicked Markets to
    a 404 while `available` happily said the section existed. Being mounted and
    being at the path the design assumed are two different facts, and only the
    second one is a working link.

    `subs`, when given, is `{key: [(subkey, label, href, meta), ...]}` — the
    ACTIVE screen's own blocks, by heading, replacing the design's guesses. §3
    says a section expands to its own block headings, and those are a fact about
    the page being rendered, not a list to keep in step by hand.

    A sub-entry that is an ANCHOR (`#something`) is a jump inside the page that
    is already open, so it needs no route and is never dropped. Only a sub that
    claims a real path is checked against `paths` — `/markets/shelves` cannot be
    right when `/markets` itself is not. That check used to run on every sub, and
    since no sub-key is ever a registered SECTION, it dropped all of them: the
    nav has not expanded anywhere since it was written.
    """
    root = active.split(".")[0]
    out, sub_out = [], []
    groups = NAV + ([STAFF_NAV] if staff else [])
    for label, items in groups:
        if available is not None:
            items = [it for it in items if it[0].split(".")[0] in available]
            if not items:
                continue
        # The design's tree is one UNNAMED group (spec §3, "flat top-level
        # list"). An empty <div class="glabel"> would still take its padding and
        # push the whole nav down by a phantom heading, so a group with no label
        # emits no heading at all. Named groups (the staff tree) keep theirs.
        head = f'<div class="glabel">{_h.escape(label)}</div>' if label else ""
        out.append(f'<div class="navgroup">{head}')
        for key, text, href, _dom, _meta, _subs in items:
            # `page` is the exact page you are on; `true` is the SECTION that
            # page belongs to. Standing on Markets > Inventory, the child is the
            # page and Markets is the section — without the second mark the
            # parent read as unselected while its own children were open under
            # it, which looks like the nav has lost its place.
            if key == active:
                cur = ' aria-current="page"'
            elif key == root and key != active:
                cur = ' aria-current="true"'
            else:
                cur = ""
            # NO COUNTS IN THE NAV. The bar carried 13 / 7 / 3 / 2 next to
            # Markets, Work, Auctions and Claims, and every one of those pages
            # already states its own count in its own heading or band — so the
            # number was said twice, and the nav's copy was the one nobody could
            # see was stale. `counts=` is still accepted so no caller breaks;
            # it is simply not rendered any more.
            _ = counts
            if key == "messages":
                # The one exception, and it is not a decoration: unread is LIVE,
                # filled by the base script every 60s against
                # /api/messages/unread, hidden while it is zero. Removing the
                # element would silently blind that script and the messages
                # probe that asserts on its id.
                m = ('<span class="meta nav-badge" id="navUnread" '
                     'style="display:none"></span>')
            else:
                m = ""
            # data-k is how the rest of the site addresses a tab — page scripts and
            # the site's own probes both look for it. The old shell emitted it, and
            # dropping it in the collapse made every "is my tab there" check blind
            # rather than failing loudly.
            real = (paths or {}).get(key, href)
            out.append(f'<a class="navitem" data-k="{_h.escape(key)}" '
                       f'href="{prefix}{real}"{cur}>'
                       f'{_h.escape(text)}{m}</a>')
            # Sub-entries appear only while their parent section is open.
            kids = (subs or {}).get(key, _subs)
            if kids and key.split(".")[0] == root:
                for skey, stext, shref, smeta in kids:
                    if not str(shref).startswith("#") and (
                            paths is not None and skey not in paths):
                        # The parent is somewhere else than the design assumed,
                        # or this child was never built. Either way the link is
                        # a 404 and an absent entry is the smaller lie.
                        continue
                    shref = shref if str(shref).startswith("#") else \
                        (paths or {}).get(skey, shref)
                    scur = ' aria-current="page"' if skey == active else ""
                    # No meta here either, for the same reason as above.
                    _ = smeta
                    sub_out.append(
                        f'<a class="navsub" data-k="{_h.escape(skey)}" '
                        f'href="{prefix}{shref}"{scur}>'
                        f'{_h.escape(stext)}</a>')
        out.append("</div>")
    strip = ('<nav class="subnav" aria-label="Sections of this page">'
             + "".join(sub_out) + "</nav>") if sub_out else ""
    return "".join(out), strip


def _nav_html(active: str, staff: bool, available=None, prefix: str = "",
              counts=None, paths=None, subs=None) -> str:
    """Both parts, concatenated. Kept because the whole site addresses the nav
    by `data-k` and does not care which of the two elements carries it."""
    row, strip = nav_parts(active, staff, available, prefix, counts, paths, subs)
    return row + strip


#: Where the sub-section strip goes. A page that wants to place it itself puts
#: this comment in its body; everything else gets it directly under `.pagehead`,
#: which every screen in the product opens with (`abex_screens.head()`,
#: `abex_render`, `abex_web`, `abex_hub`). Under the H1 is the whole point — a
#: strip above the heading is a second site nav, which is what it stopped being.
SUBNAV_SLOT = "<!--SUBNAV-->"


def _place_subnav(body: str, strip: str) -> str:
    """Put `strip` after the body's opening `.pagehead` block.

    The close is found by COUNTING `<div` against `</div>` from the opening tag,
    not by looking for the next `</div>` — a pagehead contains two or three
    nested divs (`<div><h1>..</h1><div class="sub">..</div></div>`) and the
    naive search lands inside it, which puts a nav strip in the middle of a
    heading. A body whose divs do not balance gets the strip prepended rather
    than mangled: a strip in the wrong place is a design bug, a truncated body
    is a broken page.
    """
    if not strip:
        return body
    if SUBNAV_SLOT in body:
        return body.replace(SUBNAV_SLOT, strip, 1)
    at = body.find('<div class="pagehead"')
    if at < 0:
        return strip + body
    depth, i, n = 0, at, len(body)
    while i < n:
        if body.startswith("<div", i):
            depth += 1
            i += 4
        elif body.startswith("</div>", i):
            depth -= 1
            i += 6
            if depth == 0:
                return body[:i] + strip + body[i:]
        else:
            i += 1
    return strip + body


def _stats_html(stats) -> str:
    if not stats:
        return ""
    out = []
    for item in stats:
        k, v = item[0], item[1]
        colour = item[2] if len(item) > 2 else ""
        style = f' style="color:{colour}"' if colour else ""
        out.append(f'<div class="stat"><span class="k">{_h.escape(k)}</span>'
                   f'<span class="v"{style}>{v}</span></div>')
    return "".join(out)


def render(active: str, body: str, *, title: str = "", who=None, stats=None,
           staff: bool = False, dock: str = "", extra_css: str = "",
           header: str = "", tail: str = "", available=None,
           prefix: str = "", counts=None, paths=None, subs=None) -> str:
    """Wrap a section's body in the shell. `body` is already-escaped HTML.

    This is the only shell in the product. The older pages — banking, lands,
    messages, history, the owner console and the hub — reach it through thin
    adapters in `vt_web_shell` and `hub_web`, which is why it takes three
    escape hatches:

    `extra_css`   a compatibility stylesheet for a page whose markup still uses
                  the old class vocabulary. It loads AFTER the theme, so those
                  classes can be retired one page at a time instead of in one
                  commit.
    `header`      replaces the sticky header entirely. The transactional pages
                  put their live money strip there — the same row, with a drawer
                  that names what is holding your coins.
    `tail`        markup that must sit at the end of `<body>`: the confirm modal
                  and the page scripts.
    """
    dom = domain_for(active)
    who_html = ""
    if who:
        name, role = who
        who_html = (f'<div class="who">{_h.escape(str(name))}, '
                    f'{_h.escape(str(role))}</div>')
    page_title = title or active.split(".")[0].title()
    # Built before the template: an f-string cannot nest one of its own quote
    # style, and Python 3.11 is what this runs on.
    # The viewer's name lives in the TOP BAR now, flush right, where every
    # registry and brokerage puts it. The default header keeps its money strip
    # and loses its right-hand block; a page that passes its own `header=`
    # owns both sides of that row and is not touched here.
    head_row = header or (f'<header class="top">{_stats_html(stats)}</header>'
                          if stats else "")
    nav_row, nav_strip = nav_parts(active, staff, available, prefix, counts,
                                   paths, subs)
    css_extra = f"<style>{extra_css}</style>" if extra_css else ""
    dock_html = f'<div class="dock">{dock}</div>' if dock else ""
    return f"""<!DOCTYPE html>
<html lang="en" data-domain="{dom}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_h.escape(page_title)} &middot; Abex Tech</title>
<link rel="icon" type="image/png" href="{FAVICON_SRC}">
{FONTS_LINK}
<style>{THEME_CSS}</style>
<style>{_FOOTER_CSS}</style>
{css_extra}
</head><body data-domain="{dom}">
<header class="topbar">
  <div class="topbar-inner">
    <a class="brand" href="{prefix or '/hub'}"><span class="wordmark">Abex Tech</span></a>
    <button class="navtoggle" type="button" aria-expanded="false" aria-controls="navtree">
      <span class="chev">&#9662;</span> {_h.escape(page_title)}
    </button>
    <nav id="navtree" class="navtree" aria-label="Sections">{nav_row}</nav>
    {who_html}
  </div>
</header>
<div class="col">
  {head_row}
  <main>{_place_subnav(body, nav_strip)}</main>
  {_FOOTER_HTML}
  {dock_html}
</div>
{tail}
</body></html>"""
