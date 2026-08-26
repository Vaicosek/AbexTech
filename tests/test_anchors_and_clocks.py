"""Blocks are addressable, and a clock on the page is a clock that runs.

Two spec items the site had the machinery for and never used.

§2 — "Every block gets scroll-margin-top equal to the MEASURED header height
(ResizeObserver, not a guessed constant) so sidebar anchor links land below the
sticky header, not under it." The blocks had no ids at all, so there was nothing
to anchor to; and the header wraps its figures on a narrow screen, so any
constant is right at one width and wrong at every other — and wrong means the
heading you jumped to sits underneath the header.

§5 — a countdown cell "live, ticking every second, format Xh XXm -> Xm XXs ->
Xs -> closed; escalates to loss-bold under 60s and 300s". The renderer emitted
the cell and nothing ticked it, and the auctions screen printed a raw timestamp
instead of one. Both halves now, and the server draws the first face itself: a
reader without the script sees a real time, not an em dash where a closing time
belongs, on the one board where that matters most.
"""
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_render as R        # noqa: E402
import abex_livescreens as LS  # noqa: E402
import canvas_web              # noqa: E402
import vt_web_shell            # noqa: E402


# ── anchors ────────────────────────────────────────────────────────────────

def test_a_block_carries_an_id_derived_from_its_heading():
    html = R._block({"h2": "Orders you posted", "c": ["A"], "r": []})
    assert 'id="orders-you-posted"' in html, html[:120]


def test_block_ids_survive_punctuation():
    assert R.block_id("GreyHames · share price") == "greyhames-share-price"
    assert R.block_id("What moves here") == "what-moves-here"
    assert R.block_id("") == ""


def test_the_orders_nav_entry_anchors_onto_work():
    path = vt_web_shell._NAV_PATHS["orders"]
    assert path.startswith("/hub/work#"), path
    fragment = path.split("#", 1)[1]
    # The fragment has to be one the renderer actually emits, from the heading
    # `_order_blocks` actually uses. A hand-written anchor rots the first time
    # somebody edits the heading.
    assert fragment == R.block_id("Orders you posted"), fragment


def test_scroll_margin_is_a_variable_with_a_usable_fallback():
    css = canvas_web.CANVAS_CSS
    assert "scroll-margin-top:var(--headh" in css, "blocks do not clear the header"
    assert "var(--headh, " in css, "no fallback for a page whose script never runs"
    assert "ResizeObserver" in canvas_web.CANVAS_JS, "§2 asks for a measurement"


# ── clocks ─────────────────────────────────────────────────────────────────

def test_the_countdown_faces_match_the_spec():
    assert R._countdown_face(7200) == "2h 00m"
    assert R._countdown_face(2879) == "47m 59s"
    assert R._countdown_face(45) == "45s"
    assert R._countdown_face(0) == "closed"
    assert R._countdown_face(-5) == "closed"


def test_a_countdown_cell_is_drawn_before_any_script_runs():
    cell = R._cell("Closes", "T|2879", False, False)
    assert ">47m 59s<" in cell, cell
    assert 'data-left="2879"' in cell


def test_the_last_five_minutes_escalate():
    assert "var(--loss)" in R._cell("Closes", "T|300", False, False)
    assert "font-weight:700" not in R._cell("Closes", "T|300", False, False)
    under_a_minute = R._cell("Closes", "T|45", False, False)
    assert "var(--loss)" in under_a_minute and "font-weight:700" in under_a_minute


def test_the_client_faces_match_the_server_faces():
    """Both format the same seconds. If they drift, every clock on the page
    visibly rewrites itself one second after load."""
    js = canvas_web.CANVAS_JS
    assert 'return "closed"' in js
    assert '"h " + pad(' in js and '"m " + pad(' in js
    assert 'left <= 300' in js and 'left <= 60' in js


def test_auctions_emits_a_countdown_not_a_timestamp():
    soon = (datetime.now(timezone.utc) + timedelta(minutes=48)).isoformat()
    cell = LS._closes(soon)
    assert re.fullmatch(r"T\|\d+", cell), cell
    secs = int(cell.split("|")[1])
    assert 2800 < secs <= 2880, secs


def test_a_lot_with_no_close_or_a_bad_one_gets_a_dash():
    assert LS._closes(None) == LS.DASH
    assert LS._closes("") == LS.DASH
    assert LS._closes("not a date") == LS.DASH


def test_an_already_closed_lot_reads_closed_not_a_negative():
    cell = LS._closes("2020-01-01T00:00:00Z")
    assert cell == "T|0", cell
    assert ">closed<" in R._cell("Closes", cell, False, False)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("anchors and clocks: ok")


# ── the mobile nav (§2) ────────────────────────────────────────────────────

def _shell(**kw):
    import abex_shell
    kw.setdefault("title", "Markets")
    kw.setdefault("available", {"markets", "hub"})
    kw.setdefault("paths", {"markets": "/hub/markets", "hub": "/hub"})
    return abex_shell.render("markets", "<p>body</p>", **kw)


def test_the_shell_ships_a_toggle_and_a_wrapped_tree():
    html = _shell()
    assert 'class="navtoggle"' in html
    assert 'id="navtree"' in html
    assert 'aria-controls="navtree"' in html
    assert 'aria-expanded="false"' in html, "collapsed is the initial state"


def test_the_toggle_names_the_current_screen():
    """§2: a '▾ current screen name' button, so a collapsed nav still says where
    you are."""
    assert "Markets" in _shell(title="Markets")


def test_the_toggle_is_desktop_invisible_and_the_tree_desktop_visible():
    import abex_theme
    css = abex_theme.CSS if hasattr(abex_theme, "CSS") else ""
    if not css:
        import re as _re
        src = Path(abex_theme.__file__).read_text(encoding="utf-8")
        css = src
    assert ".navtoggle{display:none}" in css, "the button would show on desktop"
    assert ".navtree{display:block}" in css, "the tree would hide on desktop"
    assert ".navtree.open{display:block}" in css


def test_the_nav_expands_inline_and_is_not_a_drawer():
    """§2: the toggle expands the tree in place. No drawer, no overlay.

    Scanned with the COMMENTS STRIPPED. The script's own comment says "no
    drawer, no overlay", which is the rule being enforced — reading it as a
    violation made this test fail on the sentence that states its own intent.
    """
    import re as _re
    js = _re.sub(r"/\*.*?\*/", "", canvas_web.CANVAS_JS, flags=_re.S)
    assert 'classList.toggle("open")' in js
    for drawer in ("position:fixed", "overlay", "backdrop"):
        assert drawer not in js, f"§2 says inline, not a drawer: {drawer}"


def test_following_a_link_collapses_the_tree():
    js = canvas_web.CANVAS_JS
    assert 'tree.addEventListener("click"' in js
    assert 'classList.remove("open")' in js
