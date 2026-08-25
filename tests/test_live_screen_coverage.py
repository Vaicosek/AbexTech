"""Every designed screen is live, and no live screen carries the design's money.

The canvas set is thirteen screens. This asserts all thirteen build from the
database, that none of them ever renders a figure that exists only in
`abex_canvas`'s sample rows, and that the four screens which are somebody's
private money refuse a public build.

The sample-figure list is the point of the file. `abex_canvas` is a beautiful
fake: GreyHames earns 42,180c, holds 156,900c in savings and bids 4,800c on a
netherite template. Those numbers rendering on a live route would be worse than
an empty page, because an empty table is visibly empty and a wrong balance is
not — and they have got out twice in this codebase already, once as a whole
screen and once as a column read one place to the left.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_livescreens as LS   # noqa: E402
import abex_render as R         # noqa: E402
from abex_canvas import SCREENS as CANVAS  # noqa: E402

#: Figures that exist ONLY in the design's sample rows.
SAMPLE = ("42,180c", "6.62c", "68,940c", "18,220c", "8,540c", "4,800c",
          "6,200c", "12,480c", "9,240c", "84,230c", "156,900c", "313.80c",
          "18,000c", "26,000c", "1,150c", "4,666c", "16,188c", "9,400c")

#: Screens that are one person's money end to end.
PRIVATE = ("stocks", "banking", "messages", "history", "market", "filing")

NOBODY = "000000000000000000"


#: Canvas screens that are deliberately not their own page. `orders` is a
#: section of Work — the same order table read from the poster's side — so it is
#: built by `_order_blocks` into that screen rather than served at a URL.
MERGED = {"orders"}


def test_every_canvas_screen_has_a_live_builder():
    missing = sorted(set(CANVAS) - set(LS.BUILDERS) - MERGED)
    assert not missing, f"no live source for: {missing}"


def test_merged_screens_are_not_mounted_anywhere():
    import canvas_web
    mounted = {k for k, _l, _p, _o in canvas_web.LIVE_SECTIONS}
    assert not (MERGED & mounted), "a merged screen is mounted as its own page"
    assert not (MERGED & set(LS.BUILDERS)), "a merged screen is still a builder"


def test_every_screen_builds_and_renders():
    for key in sorted(LS.BUILDERS):
        screen = LS.screen(key, NOBODY)
        assert screen is not None, key
        assert screen.get("asof"), f"{key} has no as-of line"
        html = R.screen_html(screen, owner=True)
        assert html, key


def test_no_screen_renders_the_designs_money():
    for key in sorted(LS.BUILDERS):
        html = R.screen_html(LS.screen(key, NOBODY), owner=True)
        for figure in SAMPLE:
            assert figure not in html, f"{key} rendered the design's {figure}"


def test_private_screens_refuse_a_public_build():
    for key in PRIVATE:
        assert LS.screen(key, "anyone", public=True) is None, key
        assert key not in LS.PUBLIC, key


def test_public_screens_carry_no_personal_column():
    for key in sorted(LS.PUBLIC):
        screen = LS.screen(key, public=True)
        assert screen is not None, key
        for block in screen.get("blocks") or []:
            for heading in block.get("c") or []:
                bare = str(heading).rstrip("#").strip().lower()
                assert bare not in LS.PERSONAL_COLUMNS, f"{key} advertises {heading}"
            # A stripped column must not leave rows wider than the header.
            width = len(block.get("c") or [])
            for row in block.get("r") or []:
                assert len(row) == width, f"{key}: row width {len(row)} != {width}"


def test_action_links_point_at_routes_that_exist():
    """A button that goes nowhere is worse than no button."""
    import canvas_web
    known = {"/auctions", "/banking", "/messages", "/history", "/lands"}
    known |= {path for _k, _l, path, _o in canvas_web.LIVE_SECTIONS}
    for key in sorted(LS.BUILDERS):
        for block in LS.screen(key, NOBODY).get("blocks") or []:
            for btn in block.get("btns") or []:
                if len(btn) > 2 and btn[2]:
                    assert btn[2] in known, f"{key} links to {btn[2]}"


def test_every_live_section_has_a_builder():
    import canvas_web
    for key, _label, _path, _order in canvas_web.LIVE_SECTIONS:
        assert key in LS.BUILDERS, f"{key} is mounted with no live source"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("live screen coverage: ok")
