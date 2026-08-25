"""
abex_shell.py — the Abex Tech page shell: sidebar hierarchy, sticky header, main column.

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

#: The brand badge. There is history here worth keeping in view: this used to be
#: `<img src="/static/atech-logo-circle.png">` carrying `onerror="this.style
#: .display='none'"`, and NO /static route was registered, no `static/` directory
#: existed, and no such file was ever committed. The 404 hid itself -- no broken
#: image, no console complaint, just a sidebar with a silent gap where a logo
#: belonged. It was then replaced with drawn text, which at least always rendered.
#:
#: The asset is real now (`static/atech-logo.png`, served by `Restocker_web`), so
#: the image comes back -- but WITHOUT the self-erasing onerror. The wordmark sits
#: beside it and carries the identity on its own, so if the image ever 404s again
#: the brand still reads, and the browser shows the broken image rather than
#: swallowing the evidence. A fallback that hides its own failure is worse than no
#: fallback; that is the whole lesson of the first version.
LOGO_SRC = "/static/atech-logo.png"
FAVICON_SRC = "/static/favicon.png"
MARK_ALT = "ATech"

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
.brand .mark{display:block;border:0;padding:0;width:46px;height:46px;
  border-radius:50%;object-fit:cover;background:transparent}
@media (max-width:900px){.brand .mark{width:34px;height:34px}}
.sitefoot{border-top:1px solid var(--line);margin:4rem 0 0;padding:1.1rem 0 2rem;
  color:var(--inert);font-size:.82rem;line-height:1.5;max-width:78ch}
.sitefoot p{margin:0}
.sitefoot a{color:var(--inert);text-decoration:none;border-bottom:1px solid var(--line)}
.sitefoot a:hover{color:var(--dim)}
"""

#: (key, label, href, domain, [(subkey, label, href), ...])
#: Groups follow the approved information architecture: the shop side lives under
#: Markets, the share side under Exchange, and the owner's own market under My market.
NAV: list[tuple[str, list]] = [
    # Exactly the mockup's navGroups, metas included. Hub is NOT a nav item — it is the
    # brand block at the top of the sidebar, same as the mockup.
    ("Money", [
        ("banking", "Banking", "/banking", "banking", "", [
            ("banking.accounts", "Accounts", "/banking", ""),
            ("banking.loans", "Loans", "/banking/loans", "2"),
            ("banking.bonds", "Bonds", "/banking/bonds", "3"),
        ]),
        ("stocks", "Stocks", "/stocks", "stocks", "5", []),
        ("investor", "Investor", "/investor", "banking", "", []),
    ]),
    ("Trade", [
        ("markets", "Markets", "/markets", "markets", "13", [
            ("markets.shelves", "On the shelves", "/markets/shelves", ""),
            ("markets.ledger", "Ledger", "/markets/ledger", ""),
            ("markets.teams", "Who runs it", "/markets/teams", ""),
            ("markets.liabilities", "Liabilities", "/markets/liabilities", ""),
        ]),
        ("exchange", "Exchange", "/exchange", "stocks", "", [
            ("exchange.price", "Price and report", "/exchange/price", ""),
            ("exchange.earnings", "Earnings", "/exchange/earnings", ""),
            ("exchange.reports", "All earnings reports", "/exchange/reports", ""),
            ("exchange.register", "Shares register", "/exchange/register", ""),
        ]),
        ("orders", "Orders", "/orders", "work", "6", []),
        ("auctions", "Auctions", "/auctions", "auctions", "1", []),
        ("betting", "Betting", "/betting", "betting", "", []),
    ]),
    ("My market", [
        ("mine", "GreyHames", "/my", "mymarket", "", [
            ("mine.overview", "Overview", "/my", ""),
            ("mine.inventory", "Inventory", "/my/inventory", "42"),
            ("mine.ledger", "Ledger", "/my/ledger", ""),
            ("mine.orders", "Orders", "/my/orders", "6"),
            ("mine.teams", "Teams", "/my/teams", "4"),
            ("mine.liabilities", "Liabilities", "/my/liabilities", "2"),
        ]),
        ("mine.report", "July report", "/my/report", "mymarket", "", []),
    ]),
    ("World", [
        ("work", "Work", "/work", "work", "7", []),
        ("lands", "Lands", "/lands", "lands", "2", []),
    ]),
    ("You", [
        ("profile", "Profile", "/profile", "hub", "", []),
        ("messages", "Messages", "/messages", "hub", "3", []),
        ("history", "History", "/history", "hub", "", []),
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
    the skin. Sub-investment grades take the loss tone, which is the only place
    that colour is allowed to appear outside money.
    """
    # An unknown grade is not a bad grade. Falling back to C's colour painted
    # "not rated" in the loss tone, which told fourteen unlisted markets they were
    # junk. Anything off the ladder is muted text.
    colour = GRADES.get(str(grade).upper(), "var(--faint)")
    return (f'<span class="grade" style="color:{colour}">'
            f'{_h.escape(str(grade))}</span>')


def _nav_html(active: str, staff: bool, available=None, prefix: str = "",
              counts=None, paths=None) -> str:
    """The nav tree.

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
    second one is a working link. A sub-entry under a remapped parent is dropped
    unless it too has a real path — `/markets/shelves` cannot be right when
    `/markets` itself is not.
    """
    root = active.split(".")[0]
    out = []
    groups = NAV + ([STAFF_NAV] if staff else [])
    for label, items in groups:
        if available is not None:
            items = [it for it in items if it[0].split(".")[0] in available]
            if not items:
                continue
        out.append('<div class="navgroup">'
                   f'<div class="glabel">{_h.escape(label)}</div>')
        for key, text, href, _dom, meta, subs in items:
            cur = ' aria-current="page"' if key == active else ""
            if counts is not None and key in counts:
                # A count in a nav is a fact about the data. The tree's numbers are
                # the design's; where the caller knows the real one it wins, and
                # where nobody knows it the entry carries none rather than a stale
                # one — the tree said 13 markets while the page listed 19.
                meta = str(counts[key] or "")
            if key == "messages":
                # The unread count is live data, filled by the base script every
                # 60s. A hardcoded number in a nav is decoration, and a wrong one
                # is worse than none; this starts hidden and stays hidden for a
                # reader with nothing unread.
                m = ('<span class="meta nav-badge" id="navUnread" '
                     'style="display:none"></span>')
            else:
                m = f'<span class="meta">{_h.escape(meta)}</span>' if meta else ""
            # data-k is how the rest of the site addresses a tab — page scripts and
            # the site's own probes both look for it. The old shell emitted it, and
            # dropping it in the collapse made every "is my tab there" check blind
            # rather than failing loudly.
            real = (paths or {}).get(key, href)
            out.append(f'<a class="navitem" data-k="{_h.escape(key)}" '
                       f'href="{prefix}{real}"{cur}>'
                       f'{_h.escape(text)}{m}</a>')
            # Sub-entries appear only while their parent section is open.
            if subs and key.split(".")[0] == root:
                for skey, stext, shref, smeta in subs:
                    if paths is not None and skey not in paths:
                        # The parent is somewhere else than the design assumed,
                        # or this child was never built. Either way the link is
                        # a 404 and an absent entry is the smaller lie.
                        continue
                    shref = (paths or {}).get(skey, shref)
                    scur = ' aria-current="page"' if skey == active else ""
                    sm = f'<span class="meta">{_h.escape(smeta)}</span>' if smeta else ""
                    out.append(f'<a class="navsub" data-k="{_h.escape(skey)}" '
                               f'href="{prefix}{shref}"{scur}>'
                               f'{_h.escape(stext)}{sm}</a>')
        out.append("</div>")
    return "".join(out)


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
           prefix: str = "", counts=None, paths=None) -> str:
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
    head_row = header or (f'<header class="top">{_stats_html(stats)}'
                          f'<div class="right">{who_html}</div></header>')
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
<nav class="side" aria-label="Sections">
  <a class="brand" href="{prefix or '/hub'}">
    <img class="mark" src="{LOGO_SRC}" alt="{MARK_ALT}" width="46" height="46">
    <span class="wordmark">Abex Tech</span>
    <span class="tag">One economy</span>
  </a>
  {_nav_html(active, staff, available, prefix, counts, paths)}
</nav>
<div class="col">
  {head_row}
  <main>{body}</main>
  {_FOOTER_HTML}
  {dock_html}
</div>
{tail}
</body></html>"""
