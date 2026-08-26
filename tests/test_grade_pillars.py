"""The rating discriminates again, and the page says why.

Every listed market read BBB. Not because they were alike — GreyHames backs
0.79x and Amazonia 1.03x — but because half the composite was structurally zero:

  * ORDER FLOW read `orders.coin_per_piece`, which is NULL on all 29 orders in
    the database. The rate is derived from the item book, not stored on the row.
    GreyHames filled six orders in thirty days and scored 0.000. (This is the
    same NULL column that made the Orders screen show no pay — one bug, two
    surfaces, and the second one was invisible.)
  * TRAFFIC reads teleport fees on lands bound to a market. `land_fees` is empty
    and the only `land_map:` bindings point at `main`, so the pillar has never
    had a row to read for any market.

Together that is 50% of a 100% composite, permanently zero, giving a ceiling of
0.50 — a ratio of 0.83 — so nothing could rate above A and everything with
ordinary backing landed on BBB.

The fix is one principle applied twice: an absent feed is UNMEASURED, not zero.
Its weight leaves the denominator instead of dragging the average down. Scoring a
feed that has never delivered a row as zero is the same mistake as printing 0c
for a figure nobody has — it looks like a measurement and it is not one.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_live as L          # noqa: E402
import abex_livescreens as LS  # noqa: E402

W = {"backing": 0.35, "traffic": 0.25, "orders": 0.25, "history": 0.15}


def _composite(scores, measured):
    """The engine's rule, restated: measured pillars only, renormalised."""
    total = sum(W[k] for k in measured) or 1.0
    return sum(W[k] * scores[k] for k in measured) / total


def test_an_absent_feed_does_not_drag_the_score_to_zero():
    scores = {"backing": 1.0, "traffic": 0.0, "orders": 0.0, "history": 1.0}
    old = sum(W[k] * scores[k] for k in W) / sum(W.values())
    new = _composite(scores, {"backing", "history"})
    assert old == 0.50, old
    assert new == 1.0, new


def test_a_measured_zero_still_counts():
    """Bound lands with no visitors is a real zero and must not be discarded."""
    scores = {"backing": 1.0, "traffic": 0.0, "orders": 0.0, "history": 1.0}
    new = _composite(scores, {"backing", "history", "traffic"})
    assert new < 1.0, new


def test_the_ceiling_was_the_bug():
    """With half the weight stuck at zero nothing could rate above A."""
    perfect_on_what_worked = {"backing": 1.0, "traffic": 0.0,
                              "orders": 0.0, "history": 1.0}
    old = sum(W[k] * perfect_on_what_worked[k] for k in W) / sum(W.values())
    assert old / 0.60 < 1.0, "a market with perfect backing AND history rated below AA"


def test_grade_detail_reports_which_pillars_were_measured():
    d = L.grade_detail("greyhames")
    assert d is not None
    by = {r["key"]: r for r in d["rows"]}
    assert set(by) == {"backing", "traffic", "orders", "history"}
    assert by["backing"]["measured"] is True
    assert by["history"]["measured"] is True
    # No land is bound to a market and `land_fees` is empty.
    assert by["traffic"]["measured"] is False


def test_the_block_says_no_data_not_zero():
    blk = LS._grade_block("greyhames", "BBB")
    assert blk is not None
    traffic = [r for r in blk["r"] if r[0] == "Traffic"][0]
    assert "no data" in traffic[1], traffic
    assert "out of the average" in traffic[2], traffic
    assert "0%" not in traffic[1], "an absent feed was rendered as a score"


def test_the_block_names_the_cap_that_binds():
    blk = LS._grade_block("greyhames", "BBB")
    assert "0.79x the target" in blk["n"], blk["n"]
    assert "CAPS the grade" in blk["n"]


def test_the_note_agrees_with_itself_on_number():
    """One unmeasured pillar reads 'has ... it'; two read 'have ... them'."""
    one = LS._grade_block("greyhames", "BBB")["n"]
    assert "has no data feeding it" in one, one
    two = LS._grade_block("amazonia", "BBB")["n"]
    assert "have no data feeding them" in two, two


def test_a_market_with_no_cached_quality_gets_no_block():
    assert LS._grade_block("no_such_market", "C") is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("grade pillars: ok")
