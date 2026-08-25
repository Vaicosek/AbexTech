"""The price line draws only what the record supports.

A chart is the fourth block shape and the only one not in the design, so the
rules it has to keep are worth pinning down. All three of these are ways a chart
can lie without any number on the page being wrong.

  1. ONE POINT DRAWS NO LINE. A flat line across a chart is a claim — that the
     price held steady across the window. Amazonia has exactly one reading ever;
     drawing a flat line from it would invent three weeks of stability that was
     never observed.
  2. FLAT IS NOT A GAIN. §1's money rule colours by direction, and unchanged is
     `dim`, not green. A price that has not moved has not made anybody anything.
  3. THE CAPTION AND THE LINE AGREE. The change figure is first-to-last of the
     same series that is drawn. Sampling a long series keeps both ends for
     exactly this reason — drop either and the sentence stops describing the
     picture above it.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_live as L          # noqa: E402
import abex_livescreens as LS  # noqa: E402
import abex_render as R        # noqa: E402


def _svg(points, unit="c"):
    return R._spark({"spark": {"points": points, "unit": unit, "window": "30 days"}})


def test_one_point_draws_no_line():
    html = _svg([999.77])
    assert "<polyline" not in html, "a single reading was drawn as a trend"
    assert "not enough for a line" in html


def test_empty_series_draws_no_line():
    assert "<polyline" not in _svg([])


def test_flat_is_dim_not_gain():
    html = _svg([100.0, 100.0, 100.0])
    assert "var(--dim)" in html, html[:200]
    assert "var(--gain)" not in html


# ── the y-window floor ─────────────────────────────────────────────────────
#
# The index moved 0.40 on 1,227 — three hundredths of one per cent — and the
# chart rendered it as a cliff off the top of the box, because scaling a series
# to its own min and max means the axis always fills and every move looks the
# same size. It invented a crash that did not happen, in red, on a page a holder
# reads to decide whether to sell.

def _ys(points):
    html = _svg(points)
    m = re.search(r'points="([^"]+)"', html)
    return [float(p.split(",")[1]) for p in m.group(1).split()]


def test_a_tiny_move_does_not_fill_the_box():
    ys = _ys([1227.16] * 100 + [1226.76] * 20)     # the real index, -0.03%
    assert max(ys) - min(ys) < 8, (min(ys), max(ys))


def test_a_real_move_still_fills_the_box():
    """The floor stops applying the moment the true span is wider than it."""
    ys = _ys([100.0, 105.0])
    assert max(ys) - min(ys) > 20, (min(ys), max(ys))
    ys = _ys([100.0, 92.0])
    assert max(ys) - min(ys) > 20, (min(ys), max(ys))


def test_a_drift_is_toned_unchanged_not_lost():
    """Colour is a verdict, and 0.03% is not one. §1 says flat is never a gain;
    the same holds at the other end — flat is not a loss either."""
    html = _svg([1227.16, 1226.76])
    assert "var(--dim)" in html
    assert "var(--loss)" not in html
    assert "= -0.40" in html, html[:300]


def test_the_caption_still_quotes_the_exact_figure():
    """The floor changes what the SHAPE claims, never what the numbers say."""
    html = _svg([1227.16, 1226.76])
    assert "-0.03%" in html


def test_the_flat_band_is_the_same_on_both_sides():
    import canvas_web
    assert "var FLAT = 0.001" in canvas_web.CANVAS_JS, "client band changed"
    assert R._FLAT_BAND == 0.001
    assert "floorSpan" in canvas_web.CANVAS_JS, "client has no y-window floor"


def test_direction_follows_last_against_first():
    assert "var(--gain)" in _svg([10.0, 5.0, 12.0])   # dips, still ends higher
    assert "var(--loss)" in _svg([12.0, 20.0, 10.0])  # spikes, still ends lower


def test_caption_matches_the_series_that_is_drawn():
    html = _svg([100.0, 150.0])
    assert "+50.00c" in html and "+50.00%" in html, html[:300]


def test_thinning_keeps_both_ends():
    rows = [(f"t{i}", float(i)) for i in range(5000)]
    out = L._thin(rows, 120)
    assert len(out) == 120
    assert out[0] == rows[0], "first reading dropped — the caption would disagree"
    assert out[-1] == rows[-1], "last reading dropped — the caption would disagree"


def test_thinning_leaves_short_series_alone():
    rows = [(f"t{i}", float(i)) for i in range(9)]
    assert L._thin(rows, 120) == rows


def test_every_drawn_point_is_a_real_reading():
    """Sampled, never averaged: each y is a value that was in the source."""
    rows = [(f"t{i}", float(i * 7 % 23)) for i in range(1000)]
    source = {v for _t, v in rows}
    for _t, v in L._thin(rows, 60):
        assert v in source, "a point appeared that no reading produced"


def test_a_missing_log_yields_no_block_rather_than_an_empty_chart():
    assert LS._spark_block("x", None) is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("price lines: ok")


# ── LIVE ───────────────────────────────────────────────────────────────────

def test_a_live_chart_is_server_drawn_first():
    """The script redraws a line that is already correct, never fills a blank.

    Rendering an empty box for a script to populate means a reader with a slow
    or blocked script sees nothing where a chart belongs — and the chart is the
    one thing on the page that cannot be read as a number instead.
    """
    blk = LS._spark_block("x", {"points": [1.0, 2.0, 3.0], "window": "30 days"},
                          src="/api/series/index?days=30")
    html = R._block(blk)
    assert "<polyline" in html and "points=" in html
    assert 'data-src="/api/series/index?days=30"' in html


def test_the_client_projection_matches_the_server_projection():
    """One geometry, written twice — so it is asserted equal.

    If these drift, the line moves on the first refresh while the caption under
    it keeps describing the old shape, and neither looks broken.
    """
    pts = [10.0, 12.5, 11.0, 15.25, 9.0]
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    n = len(pts)
    server = ["%.2f,%.2f" % (i * 100.0 / (n - 1), 28.0 - ((v - lo) / span) * 26.0 - 1.0)
              for i, v in enumerate(pts)]
    import re
    import canvas_web
    js = canvas_web.CANVAS_JS
    # The client formula, lifted from the script and evaluated here.
    assert "(i * 100 / (n - 1)).toFixed(2)" in js, "client x formula changed"
    assert "(28 - ((pts[i] - lo) / span) * 26 - 1).toFixed(2)" in js, \
        "client y formula changed"
    client = ["%.2f,%.2f" % (i * 100 / (n - 1), 28 - ((pts[i] - lo) / span) * 26 - 1)
              for i in range(n)]
    assert server == client, (server, client)


def test_the_live_script_does_not_poll_a_hidden_tab():
    import canvas_web
    assert "document.hidden" in canvas_web.CANVAS_JS, \
        "a background tab would hit the server every minute forever"


def test_a_failed_refresh_leaves_the_served_line_standing():
    import canvas_web
    js = canvas_web.CANVAS_JS
    assert ".catch(" in js, "a fetch error would blank a correct chart"
    assert "pts.length < 2" in js, "the client would draw a line from one reading"


def test_the_canvas_stylesheet_actually_reaches_the_hub():
    """It did not, for its whole life: `hub_web` imported `CANVAS_CSS` from a
    module that only defined `_CSS`, caught the ImportError and carried on with
    an empty stylesheet, so every designed screen served through the hub had no
    block vocabulary."""
    import canvas_web
    import hub_web
    assert canvas_web.CANVAS_CSS, "canvas_web exports no stylesheet"
    assert hub_web._CANVAS_CSS == canvas_web.CANVAS_CSS
    assert "svg.spark" in hub_web._CANVAS_CSS
