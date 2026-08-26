"""How full the shelves are — the legacy reading, in the new skin.

The point of this file is that NOTHING WAS REIMPLEMENTED.
`Restocker_web._load_inventory_data` has computed per-market fullness since long
before the redesign, and it does four things the newer `abex_live.shelves` does
not — derive a capacity when the scan stored none (one barrel = 54 slots x stack
size), resolve learned aliases so `Diamond Pickaxe#akQ` merges with the real
item instead of rendering as a phantom 0% row, carry the listing bundle beside
the per-unit price, and include markets nobody has scanned. Writing a third
implementation would have thrown all four away and looked fine on a screenshot.

Two things the tests hold down.

UNKNOWN IS NOT EMPTY. A market with no capacity anywhere has `pct = None`, not
0. A 0% bar beside a genuinely bare shop makes the two look identical.

THE MARKET PERCENTAGE IS A RATIO OF TOTALS, not the mean of the per-line
percentages. One empty barrel and one full chest is not "50% stocked", and
averaging weights a rare item the same as the staple nobody can buy.

And a guard that matters more than either: `_load_inventory_data` does
`import Restocker_main`, and that module RUNS THE BOT at import — its last line
is a bare `asyncio.run(_main())`. In the live server the module is already
loaded and the import is free. Anywhere else it would boot a second Discord
client off a page render and never return, so the reader refuses instead.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_live as L          # noqa: E402
import abex_render as R        # noqa: E402

FIXTURE = {"markets": [
    {"market_id": "greyhames", "name": "GreyHames", "count": 2, "low": 1,
     "items": [{"item": "Honey Bottle", "stock": 100, "capacity": 1000,
                "pct": 10.0, "price": 3.0, "pqty": 64, "lot": 192.0},
               {"item": "Glass", "stock": 900, "capacity": 1000, "pct": 90.0,
                "price": 1.0, "pqty": 1, "lot": 1.0}]},
    {"market_id": "unscanned", "name": "Nobody Scanned This", "count": 0,
     "low": 0, "items": []},
]}


def _levels(fixture=FIXTURE, monkeypatch=None):
    import Restocker_web as RW
    real_cached = RW._cached
    RW._cached = lambda key, producer, ttl=60.0: fixture
    sys.modules.setdefault("Restocker_main", sys.modules[__name__])
    try:
        return L.stock_levels()
    finally:
        RW._cached = real_cached


def test_the_reader_refuses_when_the_bot_module_is_not_loaded():
    """The important one. Importing the reader's dependency starts a Discord
    client; a page render must never be able to do that."""
    saved = sys.modules.pop("Restocker_main", None)
    try:
        assert L.stock_levels() is None
    finally:
        if saved is not None:
            sys.modules["Restocker_main"] = saved


def test_fullness_is_a_ratio_of_totals_not_a_mean_of_percentages():
    got = _levels()
    # 1000 of 2000 in stock. The MEAN of 10% and 90% is also 50 here by luck,
    # so the fixture below is the one that separates them.
    assert abs(got["greyhames"]["pct"] - 50.0) < 0.01


def test_a_big_empty_barrel_outweighs_a_small_full_one():
    fixture = {"markets": [{"market_id": "m", "name": "M", "count": 2, "low": 1,
                            "items": [{"stock": 0, "capacity": 10000},
                                      {"stock": 10, "capacity": 10}]}]}
    got = _levels(fixture)
    assert got["m"]["pct"] < 1.0, (
        "averaging the two lines would read 50%% and hide an empty shop")


def test_a_market_nobody_scanned_is_unknown_not_zero():
    got = _levels()
    assert got["unscanned"]["pct"] is None
    assert got["greyhames"]["pct"] is not None


def test_the_low_count_and_lines_come_through_unchanged():
    """`low` and `count` are the legacy reader's own figures. They are carried,
    not recomputed — recomputing is how the two surfaces start disagreeing."""
    got = _levels()
    assert got["greyhames"]["low"] == 1
    assert got["greyhames"]["lines"] == 2


def test_the_items_are_carried_whole():
    """The bundle price is on them, and it is the thing the legacy page had that
    a fresh implementation would have dropped."""
    got = _levels()
    honey = got["greyhames"]["items"][0]
    assert honey["pqty"] == 64 and honey["lot"] == 192.0


# ── the bar itself ──────────────────────────────────────────────────────────

def test_the_bar_renders_as_a_length_and_a_figure():
    td = R._cell("Stocked", "F|37.5", numeric=False, identity=False)
    assert "fillbar" in td and "width:37.5%" in td
    assert "38%" in td, "the figure stays next to it — a bar cannot be quoted"


def test_the_bar_is_coloured_by_the_sites_own_three_stops():
    low = R._cell("Stocked", "F|12", False, False)
    mid = R._cell("Stocked", "F|40", False, False)
    high = R._cell("Stocked", "F|90", False, False)
    assert "var(--loss)" in low
    assert "var(--warn)" in mid
    assert "var(--gain)" in high


def test_the_bar_cannot_overflow_its_track():
    assert "width:100.0%" in R._cell("Stocked", "F|140", False, False)
    assert "width:0.0%" in R._cell("Stocked", "F|-3", False, False)


def test_a_bar_with_no_number_is_a_dash_not_a_zero():
    td = R._cell("Stocked", "F|", False, False)
    assert "fillbar" not in td and "—" in td


def test_markets_asks_for_the_levels_and_says_unknown_where_it_has_none():
    src = (HERE.parent / "abex_livescreens.py").read_text(encoding="utf-8")
    body = src[src.index("def markets("):src.index("# ── Stocks")]
    assert "stock_levels()" in body
    assert "not scanned" in body, "an unscanned market must say so, not show 0%"
    assert '"Stocked"' in body
