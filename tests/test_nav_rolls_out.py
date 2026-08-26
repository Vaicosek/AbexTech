"""The nav expands to a section's real CHILD PAGES, and to nothing else.

This file used to test the opposite, and the opposite was wrong twice over.

FIRST the nav did not expand at all: `_nav_html` dropped any sub-entry whose key
was not in `paths`, and `paths` is built from REGISTERED SECTIONS, so no sub-key
was ever in it and every child was discarded on every page. That fix stands — an
ANCHOR child needs no route and is never checked against `paths`.

THEN, to give Markets something to open, children were DERIVED from the active
screen's block headings. That was the wrong model and it showed on the Hub,
which expanded to "Today / Markets by grade / Dividends" — three scroll targets
wearing the same clothes as pages. Once Markets got real sub-pages the same slot
meant two different things and nothing distinguished a link that navigates from
one that scrolls.

So children are DECLARED only (`hub_web.SECTION_CHILDREN`). A section with no
sub-pages does not expand, which is the honest rendering of having none.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_shell as SH        # noqa: E402
import hub_web                 # noqa: E402

AVAILABLE = {"hub", "markets", "exchange", "banking", "mine", "messages"}
PATHS = {"hub": "/hub", "markets": "/hub/markets", "exchange": "/hub/exchange",
         "banking": "/hub/banking", "mine": "/hub/market",
         "messages": "/hub/messages"}


def _keys(html, cls):
    return re.findall(r'class="%s" data-k="([^"]+)"' % cls, html)


def _nav(active, subs, paths=None):
    p = dict(paths or PATHS)
    for kids in hub_web.SECTION_CHILDREN.values():
        for k, _l, href in kids:
            p.setdefault(k, href)
    return SH._nav_html(active, False, available=AVAILABLE, paths=p, subs=subs)


def test_a_section_with_no_child_pages_does_not_expand():
    """The Hub bug: it opened to its own block headings, so "Dividends" — a
    block on the page you are already on — read as somewhere to go."""
    for key in ("hub", "banking", "exchange", "work", "messages", "history"):
        assert hub_web.nav_subs(key) is None, f"{key} should have no children"


def test_a_screen_cannot_conjure_children():
    """Passing a screen changes nothing. Blocks are not pages."""
    screen = {"blocks": [{"h2": "Today"}, {"h2": "Dividends"}]}
    assert hub_web.nav_subs("hub", screen) is None
    assert hub_web.nav_subs("banking", screen) is None


def test_markets_expands_to_its_real_pages():
    subs = hub_web.nav_subs("markets")
    labels = [s[1] for s in subs["markets"]]
    assert "Inventory" in labels and "Ledger" in labels, labels
    html = _nav("markets", subs)
    assert _keys(html, "navsub"), "the children were built and then dropped"


def test_a_sub_that_claims_a_real_path_is_still_checked():
    """The original rule survives where it was right: `/markets/shelves` cannot
    be a working link when `/markets` itself is served somewhere else."""
    subs = {"markets": [("nowhere", "Shelves", "/markets/shelves", "")]}
    html = SH._nav_html("markets", False, available=AVAILABLE, paths=PATHS,
                        subs=subs)
    assert _keys(html, "navsub") == []


def test_an_anchor_sub_is_not_checked_against_the_routes():
    """Anchors are still supported by the renderer — nothing declares them
    today, but the check that used to eat them must stay gone."""
    subs = {"markets": [("markets.a", "Filing next", "#filing-next", "")]}
    html = SH._nav_html("markets", False, available=AVAILABLE, paths=PATHS,
                        subs=subs)
    assert _keys(html, "navsub") == ["markets.a"]
    assert 'href="#filing-next"' in html


def test_only_the_active_section_opens():
    html = _nav("banking", hub_web.nav_subs("markets"))
    assert _keys(html, "navsub") == [], "a closed section shows no children"


def test_the_parent_lights_while_you_are_on_a_child():
    html = _nav("markets.inventory", hub_web.nav_subs("markets.inventory"))
    parent = re.search(r'class="navitem" data-k="markets"([^>]*)', html).group(1)
    assert 'aria-current="true"' in parent, parent
    cur = [l for a, l in re.findall(
        r'class="navsub" data-k="[^"]+" href="[^"]+"([^>]*)>([^<]*)', html)
        if "aria-current" in a]
    assert cur == ["Inventory"], cur
