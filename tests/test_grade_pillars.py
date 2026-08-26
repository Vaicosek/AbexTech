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


#: A cached `quality:<mid>` blob, as the engine writes one. The tests below used
#: to read whatever was in the database, which made them pass or fail on the
#: state of somebody's cache rather than on the code.
CACHED = {
    "score": 0.5687, "backing_score": 0.7904, "traffic_score": 0.0,
    "orders_score": 0.41, "history_score": 1.0, "backed_pct": 39.5,
    "target_pct": 50.0, "history_months": 28, "order_value_30d": 205000,
    "visitors_month": 0, "orders_total_30d": 6,
    "pillars_measured": ["backing", "history", "orders"],
}


def _with_cached(blob, mid="greyhames"):
    real = L._db

    class _Db:
        @staticmethod
        def get_config(key):
            import json as _json
            return _json.dumps(blob) if key == f"quality:{mid}" else None

    L._db = lambda: _Db
    try:
        return L.grade_detail(mid)
    finally:
        L._db = real


def test_grade_detail_reports_which_pillars_were_measured():
    d = _with_cached(CACHED)
    assert d is not None
    by = {r["key"]: r for r in d["rows"]}
    assert set(by) == {"backing", "traffic", "orders", "history"}
    assert by["backing"]["measured"] is True
    assert by["history"]["measured"] is True
    # No land is bound to a market and `land_fees` is empty.
    assert by["traffic"]["measured"] is False


def _block_with(blob, grade="BBB", mid="greyhames"):
    detail = _with_cached(blob, mid)          # computed BEFORE the patch goes on,
    real = L.grade_detail                      # or the patch would call itself
    L.grade_detail = lambda m: detail if m == mid else None
    try:
        return LS._grade_block(mid, grade)
    finally:
        L.grade_detail = real


def test_the_block_says_no_data_not_zero():
    blk = _block_with(CACHED)
    assert blk is not None
    traffic = [r for r in blk["r"] if r[0] == "Traffic"][0]
    assert "no data" in traffic[1], traffic
    assert "out of the average" in traffic[2], traffic
    assert "0%" not in traffic[1], "an absent feed was rendered as a score"


def test_the_block_names_the_cap_that_binds():
    blk = _block_with(CACHED)
    assert "0.79x the target" in blk["n"], blk["n"]
    assert "CAPS the grade" in blk["n"]


def test_the_note_agrees_with_itself_on_number():
    """One unmeasured pillar reads 'has ... it'; two read 'have ... them'."""
    one = _block_with(CACHED)["n"]
    assert "has no data feeding it" in one, one
    both_absent = dict(CACHED, orders_score=0.0, orders_total_30d=0,
                       pillars_measured=["backing", "history"])
    two = _block_with(both_absent)["n"]
    assert "have no data feeding them" in two, two


def test_a_market_with_no_cached_quality_gets_no_block():
    assert LS._grade_block("no_such_market", "C") is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("grade pillars: ok")


# ── the backing cap, narrowed (owner's call, 26 Aug 2026) ──────────────────
#
# The cap used to apply at EVERY band: 0.79x backed meant BBB whatever else a
# market did. So the cap decided every grade and the four pillars were
# decorative — GreyHames scored A on composite and read BBB, Amazonia scored AA
# and read A, and the cap bound both times. A rating whose other inputs can only
# ever lower it is a backing ratio wearing a letter.
#
# Collateral now gates AA and AAA only. Everything at A and below is the
# composite's to decide.

RANK = {"C": 0, "BB": 1, "BBB": 2, "A": 3, "AA": 4, "AAA": 5}


def _band(ratio):
    return ("AAA" if ratio >= 1.5 else "AA" if ratio >= 1.0 else "A" if ratio >= 0.75
            else "BBB" if ratio >= 0.5 else "BB" if ratio >= 0.25 else "C")


def _cap(brat):
    """The shipped rule: AAA at 1.6x, AA at 1.2x, otherwise at most A."""
    return "AAA" if brat >= 1.6 else "AA" if brat >= 1.2 else "A"


def _graded(score, brat):
    g = _band(score / 0.60)
    c = _cap(brat)
    return c if RANK[c] < RANK[g] else g


def test_the_shipped_cap_matches_this_rule():
    """Read out of the source, so the test fails if the ladder is edited."""
    src = (Path(__file__).resolve().parent.parent / "Restocker_main.py").read_text(
        encoding="utf-8")
    assert '_cap = "AAA" if _brat >= 1.6 else "AA" if _brat >= 1.2 else "A"' in src


def test_collateral_still_gates_the_top_two_bands():
    perfect = 1.0                       # composite 1.0 -> ratio 1.67 -> AAA
    assert _graded(perfect, 1.7) == "AAA"
    assert _graded(perfect, 1.3) == "AA"
    assert _graded(perfect, 1.19) == "A", "a market bought its way past the gate"
    assert _graded(perfect, 0.0) == "A"


def test_an_ordinary_market_can_now_earn_a():
    """GreyHames: 0.79x backed, composite around 0.70."""
    assert _graded(0.705, 0.79) == "A"


def test_collateral_alone_still_buys_nothing():
    """1.7x backed and nothing else working is a BBB, not an AAA."""
    assert _graded(0.35, 1.7) == "BBB"


def test_the_cap_can_only_lower_a_grade_never_raise_one():
    for score in (0.1, 0.3, 0.5, 0.7, 0.9, 1.0):
        for brat in (0.0, 0.5, 1.0, 1.3, 2.0):
            assert RANK[_graded(score, brat)] <= RANK[_band(score / 0.60)]


def test_a_market_with_no_chests_at_all_can_reach_a_and_no_further():
    """The consequence of the owner's choice, asserted so it is not a surprise:
    perfect traffic, orders and history with zero collateral rates A."""
    zero_backed = (0.25 + 0.25 + 0.15) / 1.0        # backing scores 0
    assert _graded(zero_backed, 0.0) == "A"
    assert _graded(zero_backed, 1.3) == "AA"
