"""No route anybody can reach serves the design's sample money.

This is the line the whole live-screens effort is built on, stated in
`abex_livescreens`: "A live screen never falls back to sample rows... a page
that quietly shows 21,084c because the query failed is worse than an empty one,
because an empty table is obviously empty and a wrong balance is not."

It had been crossed and left crossed. `/abex/banking`, `/abex/banking/loans`
and `/abex/banking/bonds` served `abex_screens.banking_*` — the mockup's
figures, 84,230c available and 156,900c in savings — to anybody signed in. On
banking, of all subjects, where a wrong number does not read as a broken page,
it reads as your money.

They are retired to /hub/banking, which is the same section on the real ledger.
Redirects, not deletions: they were in the nav for weeks.

The builders themselves stay in `abex_screens` — they are the design's own
reference rendering and are still served under /canvas, where every figure is
sample data and the page says so. The rule is not "these functions may not
exist", it is "no route serves them as if they were somebody's balance".
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_web  # noqa: E402

#: Figures that exist only in the design's banking mock.
SAMPLE_BANKING = ("84,230c", "156,900c", "12,400c", "26,800c", "41,600c",
                  "68,400c", "2,850c")


def test_no_banking_screen_is_served_from_sample_data():
    keys = {key for _p, key, _t, _f in abex_web.SCREENS}
    for key in keys:
        assert not key.startswith("banking"), f"{key} is still routed"


def test_the_retired_paths_go_to_the_live_banking_page():
    assert abex_web.RETIRED, "nothing is retired — did the routes come back?"
    for path, target in abex_web.RETIRED.items():
        assert target.startswith("/hub/"), (path, target)


def test_the_retired_paths_are_the_ones_that_showed_fake_balances():
    assert "/banking" in abex_web.RETIRED
    assert "/banking/loans" in abex_web.RETIRED
    assert "/banking/bonds" in abex_web.RETIRED


def test_no_remaining_abex_screen_renders_a_banking_sample_figure():
    """Every still-routed screen with a static builder, rendered and searched."""
    for _path, key, _title, fn in abex_web.SCREENS:
        if fn is None:
            continue                      # needs a session; covered by its own tests
        html = fn()
        for figure in SAMPLE_BANKING:
            assert figure not in html, f"{key} renders the design's {figure}"


def test_the_live_banking_screen_is_the_one_in_the_nav():
    import vt_web_shell
    assert vt_web_shell._NAV_PATHS["banking"].startswith("/hub/"), \
        vt_web_shell._NAV_PATHS["banking"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("no sample money on a route: ok")


# ── /canvas is retired: one site ───────────────────────────────────────────

def test_the_sample_screen_set_is_no_longer_served():
    """`/canvas/*` rendered `abex_canvas`'s rows — the design's invented money —
    beside the real pages while each screen was being wired. Every screen is
    wired, so a second set of pages answering "what do I own" with figures
    nobody has is exactly the /abex/banking mistake with a different prefix."""
    import canvas_web
    assert not hasattr(canvas_web, "_page"), "the sample renderer is back"
    assert not hasattr(canvas_web, "_handler"), "the sample route handler is back"
    assert "SCREENS" not in dir(canvas_web), "sample rows imported again"


def test_every_retired_canvas_path_lands_on_a_live_page():
    import canvas_web
    assert canvas_web._MOVED, "nothing is redirected"
    for key, target in canvas_web._MOVED.items():
        assert target.startswith("/hub"), (key, target)


def test_the_design_file_is_still_read_for_shape():
    """`abex_canvas` stays: a live screen keeps the column headings and block
    order the design gave it. It is the ROWS that are not served."""
    import abex_livescreens
    from abex_canvas import SCREENS
    assert SCREENS, "the design's shape source went away"
    cols = abex_livescreens._cols("markets", 1)
    assert cols, "live screens lost the design's column headings"
