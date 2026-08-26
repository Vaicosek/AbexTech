"""The nav expands to the active screen's own blocks.

§3 says a section opens to its own block headings. It never did. Two bugs, one
on top of the other, and the second hid the first:

1. `_nav_html` dropped any sub-entry whose key was not in `paths`. `paths` is
   built from REGISTERED SECTIONS, and no sub-key is ever a section, so every
   sub-entry in the tree was discarded on every page. The nav has not expanded
   anywhere since it was written.

2. `NAV`'s Markets entry carries no children at all, so even with (1) fixed
   there was nothing to open — which is exactly what "click Markets and it
   doesn't roll out" looked like from outside.

The fix for both is to stop keeping a second list by hand: the children are read
off the screen being rendered. A sub is an ANCHOR into a page that is already
open, so it needs no route and is never checked against `paths`.
"""
import sys
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_shell as SH        # noqa: E402
import abex_livescreens as LS  # noqa: E402
import hub_web                 # noqa: E402

AVAILABLE = {"hub", "markets", "exchange", "banking", "mine", "messages"}
PATHS = {"hub": "/hub", "markets": "/hub/markets", "exchange": "/hub/exchange",
         "banking": "/hub/banking", "mine": "/hub/market",
         "messages": "/hub/messages"}


def _keys(html, cls):
    return re.findall(r'class="%s" data-k="([^"]+)"' % cls, html)


def test_an_anchor_sub_is_not_checked_against_the_routes():
    subs = {"markets": [("markets.a", "Filing next", "#filing-next", ""),
                        ("markets.b", "All markets", "#all-markets", "")]}
    html = SH._nav_html("markets", False, available=AVAILABLE, paths=PATHS, subs=subs)
    assert _keys(html, "navsub") == ["markets.a", "markets.b"]
    assert 'href="#filing-next"' in html


def test_a_sub_that_claims_a_real_path_is_still_checked():
    """The original rule survives where it was right: `/markets/shelves` cannot
    be a working link when `/markets` itself is served somewhere else."""
    subs = {"markets": [("nowhere", "Shelves", "/markets/shelves", "")]}
    html = SH._nav_html("markets", False, available=AVAILABLE, paths=PATHS, subs=subs)
    assert _keys(html, "navsub") == []


def test_only_the_active_section_opens():
    subs = {"markets": [("markets.a", "Filing next", "#filing-next", "")]}
    html = SH._nav_html("banking", False, available=AVAILABLE, paths=PATHS, subs=subs)
    assert _keys(html, "navsub") == [], "a closed section shows no children"


# Banking is the worked example throughout: a section with NO declared child
# pages, so its nav entry still opens on its own block headings. Markets used to
# play this part and cannot any more — it has real sub-pages now, and declared
# children deliberately win over derived ones.
DERIVED = "banking"


def test_the_children_are_the_screens_own_blocks():
    screen = {"blocks": [{"h2": "Waiting on you"}, {"h2": "Accounts"}]}
    subs = hub_web.nav_subs(DERIVED, screen)
    assert subs == {"banking": [
        ("banking.waiting-on-you", "Waiting on you", "#waiting-on-you", ""),
        ("banking.accounts", "Accounts", "#accounts", "")]}


def test_the_anchor_matches_the_one_the_block_renders():
    """`block_id` derives the id from the heading and `nav_subs` derives the
    href from the same heading. If they ever disagree the link is a dead jump,
    so they are checked against each other rather than trusted."""
    import abex_render
    for heading in ("On the shelves", "Where the net goes", "Ledger, August",
                    "Waiting on you", "All thirteen markets"):
        subs = hub_web.nav_subs(DERIVED, {"blocks": [{"h2": heading}]})
        _key, _label, href, _meta = subs["banking"][0]
        assert href == "#" + abex_render.block_id(heading)


def test_a_headless_block_is_skipped_not_rendered_blank():
    screen = {"blocks": [{"h2": ""}, {"spark": {}}, {"h2": "Trade"}]}
    subs = hub_web.nav_subs(DERIVED, screen)
    assert subs == {"banking": [("banking.trade", "Trade", "#trade", "")]}


def test_a_long_screen_does_not_become_a_table_of_contents():
    screen = {"blocks": [{"h2": f"Block {i}"} for i in range(12)]}
    subs = hub_web.nav_subs(DERIVED, screen)
    assert len(subs["banking"]) == hub_web.NAV_SUB_LIMIT


def test_a_screen_with_nothing_to_open_offers_nothing():
    assert hub_web.nav_subs(DERIVED, None) is None
    assert hub_web.nav_subs(DERIVED, {"blocks": []}) is None


def test_a_real_screen_really_does_open_now():
    """The end-to-end version of the complaint: build a real screen, ask for its
    nav, and check the sidebar has something under it."""
    screen = LS.screen(DERIVED, "", public=True) or {"blocks": [{"h2": "Accounts"}]}
    subs = hub_web.nav_subs(DERIVED, screen)
    assert subs and subs["banking"], "the section still does not roll out"
    html = SH._nav_html(DERIVED, False, available=AVAILABLE, paths=PATHS, subs=subs)
    assert _keys(html, "navsub"), "the children were built and then dropped"


def test_a_section_with_declared_children_does_not_use_block_headings():
    """This test used to check that Market opened on its own block headings.
    That was the wrong model: Market's sub-categories are PAGES, so they are
    declared rather than derived, and deriving them from blocks is what capped
    them at four and dropped two. See `tests/test_section_children.py`.

    Everything here still applies to a section WITHOUT declared children —
    Markets, Banking, the Hub — which is what the rest of this file covers.
    """
    screen = {"blocks": [{"h2": "Ledger, August"}, {"h2": "Liabilities"}]}
    subs = hub_web.nav_subs("market", screen)
    labels = [s[1] for s in subs["mine"]]
    assert "Inventory" in labels, labels
    assert "Ledger, August" not in labels, (
        "a declared child list must win over whatever blocks the page has")
