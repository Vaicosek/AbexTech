"""A section's sub-categories are PAGES under it, not blocks inside it.

The mistake this file exists to prevent. Market's console grew to seven blocks —
items, shelves, ledger, month, waterfall, liabilities, staff — because things
that had always been separate pages got stacked onto one screen. Two problems,
and the second one hid the first:

1. Seven things in one scroll is not an information architecture. `/inventory`,
   `/ledger`, `/orders`, `/teams`, `/liabilities` and `/investor` are pages with
   years of behaviour in them and they were still there; the console was a
   duplicate that could only ever be a worse copy.

2. The nav derived a section's children from its BLOCK HEADINGS and capped them
   at four. So the console's own seven became four anchors, and Liabilities and
   Staff were silently not in the nav at all.

Children are DECLARED now, in `hub_web.SECTION_CHILDREN`, because a child page
is a routing fact and cannot be read off a parent's blocks. Declared children
are never capped and never derived — the cap exists to stop a long screen
becoming a table of contents, and a section's real sub-pages are not that.

The pages themselves are unchanged: `abex_reskin` lifts each legacy body into
the hub shell so there is one nav and one skin. The data, the JSON the handler
injects, and the page's own script are all still theirs.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_shell as SH        # noqa: E402
import abex_livescreens as LS  # noqa: E402
import hub_web                 # noqa: E402
import canvas_web              # noqa: E402


def _registered():
    for key, label, path, order in canvas_web.LIVE_SECTIONS:
        hub_web.register_section(key, label, path, order=order)


def _nav(active, subs):
    _registered()
    staff = False
    mounted = {hub_web._NAV_KEY_FOR(s["key"]) for s in hub_web.sections()}
    paths = {hub_web._NAV_KEY_FOR(s["key"]): s["path"] for s in hub_web.sections()}
    for kids in hub_web.SECTION_CHILDREN.values():
        for k, _l, href in kids:
            paths.setdefault(k, href)
    return SH._nav_html(active, staff, available=mounted, paths=paths, subs=subs)


def _subs(html):
    return re.findall(r'class="navsub" data-k="([^"]+)" href="([^"]+)"([^>]*)>([^<]*)',
                      html)


def test_market_opens_to_every_one_of_its_pages():
    subs = hub_web.nav_subs("market", None)
    labels = [s[1] for s in subs["mine"]]
    for want in ("Inventory", "Ledger", "Orders", "Teams", "Liabilities",
                 "Investor"):
        assert want in labels, f"{want} is not under Market: {labels}"


def test_declared_children_are_not_capped():
    """The four-block cap is for anchors. Seven pages is seven pages."""
    subs = hub_web.nav_subs("market", None)
    assert len(subs["mine"]) > hub_web.NAV_SUB_LIMIT


def test_a_child_needs_no_screen_to_be_offered():
    """A re-skinned legacy page passes no screen at all. Asking for one first is
    how those pages rendered with the design's hardcoded child instead of their
    real siblings."""
    assert hub_web.nav_subs("mine.inventory", None) is not None
    assert hub_web.nav_subs("mine.ledger", None) is not None


def test_the_child_you_are_on_is_the_one_marked_current():
    subs = hub_web.nav_subs("mine.teams", None)
    html = _nav("mine.teams", subs)
    current = [label for _k, _h, attrs, label in _subs(html)
               if "aria-current" in attrs]
    assert current == ["Teams"], current


def test_children_only_open_under_their_own_parent():
    subs = hub_web.nav_subs("banking", None)
    html = _nav("banking", subs)
    assert _subs(html) == [], "another section must not show Market's pages"


def test_every_child_points_at_a_route_that_exists():
    src = (HERE.parent / "Restocker_web.py").read_text(encoding="utf-8")
    hub = (HERE.parent / "canvas_web.py").read_text(encoding="utf-8")
    for _k, label, href in hub_web.SECTION_CHILDREN["mine"]:
        served = (f'add_get("{href}"' in src
                  or f'"{href}"' in src
                  or href in hub)
        assert served, f"{label} points at {href}, which nobody serves"


def test_the_console_did_not_swallow_its_own_children():
    """The console is a landing. Inventory belongs at /inventory, where it has
    always been and where the legacy behaviour still lives."""
    src = (HERE.parent / "abex_livescreens.py").read_text(encoding="utf-8")
    body = src[src.index("def market(user_id"):]
    body = body[:body.index('screen_d["title"]')]
    assert "_shop_blocks(" not in body, (
        "the shelves are a child page, not a block on the parent")
    assert "_item_block(" not in body


# ── the re-skin ─────────────────────────────────────────────────────────────

def test_a_legacy_page_comes_back_with_one_nav_and_no_second_header():
    import abex_reskin
    import Restocker_web as RW
    _registered()
    html = abex_reskin.render(
        RW._INVENTORY_HTML, active="mine.inventory", title="Inventory",
        user=None, snap=None,
        replacements={"__TERMINAL_CSS__": RW._TERMINAL_CSS,
                      "__INVENTORY_JSON__": "<script>window.INVENTORY={}</script>"})
    assert html.count("<!DOCTYPE") == 1 and html.count("<body") == 1
    assert 'header class="tshell"' not in html, "the old header bar is gone"
    assert "header.tshell" not in html, "and so are the rules that drew it"
    assert 'class="navsub"' in html, "and the hub nav is what replaced it"


def test_no_placeholder_survives_the_re_skin():
    import abex_reskin
    import Restocker_web as RW
    html = abex_reskin.render(
        RW._TEAMS_HTML, active="mine.teams", title="Teams", user=None, snap=None,
        replacements={"__TERMINAL_CSS__": RW._TERMINAL_CSS,
                      "__TEAMS_JSON__": "<script>window.TEAMS={}</script>"})
    for marker in ("__NAV__", "__TERMINAL_CSS__", "__TEAMS_JSON__"):
        assert marker not in html, marker


def test_the_page_keeps_its_own_script_and_its_own_styles():
    """A skin swap. The body, the stylesheet and the script are the page's."""
    import abex_reskin
    import Restocker_web as RW
    html = abex_reskin.render(
        RW._ORDERS_HTML, active="mine.orders", title="Orders", user=None,
        snap=None,
        replacements={"__TERMINAL_CSS__": RW._TERMINAL_CSS,
                      "__ORDERS_JSON__": "<script>window.ORDERS={x:1}</script>",
                      "__ITEMS_JSON__": "<script>window.ITEMS={}</script>"})
    assert "window.ORDERS" in html, "its data must still reach it"
    assert ".panel" in html, "its own stylesheet must ride along"


def test_the_shell_owns_the_body_rule():
    """The legacy sheet sets a 19px base and its own background. The type scale
    was deliberately brought down; a page-level `body` rule would quietly undo
    that decision on seven pages at once."""
    import abex_reskin
    import Restocker_web as RW
    css = abex_reskin._strip_shell_css(RW._TERMINAL_CSS)
    assert not re.search(r"(^|\})\s*body\s*\{", css), css[:200]
    assert "--accent" in css, "the tokens themselves must survive"


def test_every_legacy_handler_goes_through_the_shell():
    src = (HERE.parent / "Restocker_web.py").read_text(encoding="utf-8")
    for handler in ("_handle_inventory_page", "_handle_ledger_page",
                    "_handle_orders_page", "_handle_teams_page",
                    "_handle_liabilities_page", "_handle_investor_page"):
        body = src[src.index(f"async def {handler}"):]
        body = body[:body.index("\n\n\n")]
        assert "_legacy_page(" in body, f"{handler} still renders its own shell"
        assert "_TERMINAL_NAV" not in body, f"{handler} still draws the old nav"
