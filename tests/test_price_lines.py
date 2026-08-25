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
