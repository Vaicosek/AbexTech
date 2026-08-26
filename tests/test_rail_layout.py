"""The rail: two columns when a screen asks for one, the stack when it does not.

A trading terminal puts what you can DO beside what you are reading — the
watchlist, the positions, the ticket — instead of below it. Stacked, the ticket
pushed the chart off the screen, so a trader had to choose between the line and
the price he was confirming.

What this is NOT is a second layout language. The design describes a screen as a
band and a list of blocks (§4); a grid engine beside that would mean every
future screen has to decide which one it speaks. One flag on a block, two
columns, and it collapses back to the stack under 1100px — a 336px rail beside a
table is a table nobody can read.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_livescreens as LS  # noqa: E402
import abex_render as R        # noqa: E402
import canvas_web              # noqa: E402

OWNER = "1203738126850461738"


def test_a_screen_with_no_rail_block_is_unchanged():
    html = R.screen_html({"title": "X", "asof": "y",
                          "blocks": [{"h2": "A", "c": ["q"], "r": []}]})
    assert "railed" not in html
    assert "railside" not in html


def test_one_side_block_makes_two_columns():
    html = R.screen_html({"title": "X", "asof": "y", "blocks": [
        {"h2": "A", "c": ["q"], "r": []},
        {"h2": "B", "side": 1, "bal": [["x", "1", ""]]}]})
    assert html.count("railmain") == 1
    assert html.count("railside") == 1
    # The rail holds only what asked for it.
    rail = html.split("railside")[1]
    assert "B" in rail and ">A<" not in rail


def test_role_gating_still_applies_inside_the_rail():
    """A `side` block that is also `own` must not leak to a non-owner."""
    html = R.screen_html({"title": "X", "blocks": [
        {"h2": "Secret", "own": 1, "side": 1, "bal": []}]}, owner=False)
    assert "Secret" not in html


def test_the_market_page_reads_left_and_acts_right():
    screen = LS.stock(OWNER, "greyhames", csrf="token")
    main = [b.get("h2") for b in screen["blocks"] if not b.get("side")]
    rail = [b.get("h2") for b in screen["blocks"] if b.get("side")]
    assert any("share price" in str(h) for h in main), main
    assert "Month by month" in main
    assert "Trade" in rail, rail
    assert "The register" in rail, rail


def test_the_chart_is_above_the_fold_not_under_the_ticket():
    """The ticket used to be the first block; it pushed the line off the screen."""
    screen = LS.stock(OWNER, "greyhames", csrf="token")
    html = R.screen_html(screen, owner=True)
    assert html.index("<svg") < html.index("railside"), \
        "the chart renders after the rail — the ticket is back on top"


def test_a_signed_out_market_page_still_renders():
    html = R.screen_html(LS.stock("", "greyhames"), owner=False)
    assert "railmain" in html
    assert "ticket" not in html, "a stranger was given a ticket"


def test_the_rail_collapses_on_a_narrow_viewport():
    css = canvas_web.CANVAS_CSS
    assert ".railed{display:grid" in css
    assert "@media (max-width:1100px)" in css
    tail = css.split("@media (max-width:1100px)")[1][:220]
    assert "grid-template-columns:minmax(0,1fr)" in tail, tail


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("rail layout: ok")
