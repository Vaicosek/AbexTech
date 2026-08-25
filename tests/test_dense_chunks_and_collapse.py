"""Three §4/§5/§3 details: the chunk ramp, `dense`, and collapsing the active item.

Small things, and each is a rule about not letting a display choice say something
the data does not.

§4 — "Chunk-count column is size-scaled: brightness + font-size log-interpolate
from 10 to 1000 chunks." LOG, because the range is two orders of magnitude; a
linear ramp leaves everything under 200 chunks identically dim, which turns the
column into decoration. A claim of 12 chunks and one of 900 are different kinds
of thing and the figures alone read as two numbers of similar weight.

§5 — `dense` "toggles table row padding (7px vs 10px); does not change font
size". A column of figures that shrinks when its table gets long reads as less
important than the same figures on a short one, which is a claim about the data
made by the layout.

§3 — "clicking the active item again collapses it instead of navigating".
Following the link you are already on reloads a page that does not change, which
reads as a dead click.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_render as R   # noqa: E402
import canvas_web         # noqa: E402


def _px(cell):
    m = re.search(r"font-size:([\d.]+)px", cell)
    return float(m.group(1)) if m else None


def _grey(cell):
    m = re.search(r"color:#([0-9a-f]{2})", cell)
    return int(m.group(1), 16) if m else None


def test_the_chunk_ramp_rises_with_the_count():
    sizes = [_px(R._cell("Chunks", n, True, False))
             for n in ("10", "60", "250", "1,000")]
    assert all(s is not None for s in sizes), sizes
    assert sizes == sorted(sizes) and sizes[0] < sizes[-1], sizes
    greys = [_grey(R._cell("Chunks", n, True, False))
             for n in ("10", "60", "250", "1,000")]
    assert greys == sorted(greys) and greys[0] < greys[-1], greys


def test_the_ramp_is_logarithmic_not_linear():
    """Half the ramp should be spent below 100 chunks. Linear would spend 9% of
    it there and leave every small claim looking identical."""
    lo = _px(R._cell("Chunks", "10", True, False))
    hi = _px(R._cell("Chunks", "1000", True, False))
    mid = _px(R._cell("Chunks", "100", True, False))
    half = lo + (hi - lo) / 2
    assert abs(mid - half) < 0.6, (lo, mid, hi, half)


def test_the_ramp_clamps_outside_its_range():
    assert _px(R._cell("Chunks", "1", True, False)) == \
        _px(R._cell("Chunks", "10", True, False))
    assert _px(R._cell("Chunks", "5,000", True, False)) == \
        _px(R._cell("Chunks", "1,000", True, False))


def test_a_non_numeric_chunk_cell_is_left_alone():
    assert "font-size" not in R._cell("Chunks", "m|—", True, False)
    assert "font-size" not in R._cell("Chunks", "", True, False)


def test_only_the_chunk_column_is_ramped():
    assert "font-size" not in R._cell("Shares out", "1,000", True, False)
    assert "font-size" not in R._cell("Price", "1,000c", True, False)


def test_the_claims_table_names_the_column_chunks():
    """The ramp keys off the heading, so a column called 'Size' loses it."""
    import abex_livescreens as LS
    screen = LS.lands()
    table = next(b for b in screen["blocks"] if b.get("c"))
    assert any(c.rstrip("#").lower() == "chunks" for c in table["c"]), table["c"]


def test_dense_changes_padding_and_not_font_size():
    assert 'class="dense"' in R._table({"c": ["A"], "r": [["x"]], "dense": 1})
    assert 'class=""' in R._table({"c": ["A"], "r": [["x"]]})
    css = canvas_web.CANVAS_CSS
    assert "table.dense td" in css
    rule = css.split("table.dense td")[1].split("}")[0]
    assert "padding" in rule
    assert "font-size" not in rule, "§5: dense must not touch type size"


def test_the_active_nav_item_collapses_instead_of_navigating():
    js = canvas_web.CANVAS_JS
    assert 'aria-current="page"' in js
    assert "preventDefault" in js, "it would navigate instead of collapsing"
    assert "navsub" in js, "it has to find the children it is collapsing"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("dense, chunks and collapse: ok")
