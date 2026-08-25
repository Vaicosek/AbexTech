"""What moves through a market: item by item, month by month, in apart from out.

Two rules, both about not collapsing things that mean different things.

DIRECTION. `csn_history_items` records, per item per month, how many the shop
SOLD to players and how many it BOUGHT from them. Those are opposite trades. A
single "movement" figure would render Amazonia's July honeycomb — 4,465 out
against 3,727 in — as one number and hide which way the shop was leaning; and
the month it flipped on honey (300 out, 3,200 in) is the month its net went
from +1.89M to -126k. So they are separate columns, always.

DISCLOSURE (§6.7). A LISTED market discloses its ledger to everyone, so the
table is public on one. A PRIVATE market discloses nothing — except to its own
owner, who is not a stranger to his own shop. Everyone else gets no block at
all, rather than an empty one, because an empty table advertises that there is
something there to see.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_live as L          # noqa: E402
import abex_livescreens as LS  # noqa: E402

OWNER = "1203738126850461738"
STRANGER = "000000000000000000"
LISTED = "amazonia"        # listed on the exchange
PRIVATE = "vtech"          # not listed, owned by OWNER


def _block(screen):
    for b in screen.get("blocks") or []:
        if b.get("h2") == "What moves here":
            return b
    return None


def test_in_and_out_are_separate_columns_per_month():
    data = L.market_items(LISTED, months=3)
    screen = LS.stock(OWNER, LISTED)
    blk = _block(screen)
    assert blk is not None
    # one Item column, two per month, one Net column
    assert len(blk["c"]) == 1 + 2 * len(data["months"]) + 1, blk["c"]
    outs = [c for c in blk["c"] if c.endswith(" out#")]
    ins = [c for c in blk["c"] if c.endswith(" in#")]
    assert len(outs) == len(ins) == len(data["months"])
    for row in blk["r"]:
        assert len(row) == len(blk["c"]), (len(row), len(blk["c"]))


def test_the_two_directions_are_not_summed():
    """Amazonia's July honeycomb: 4,465 out and 3,727 in, both on the row."""
    blk = _block(LS.stock(OWNER, LISTED))
    honey = [r for r in blk["r"] if r[0] == "Honeycomb Block"]
    assert honey, "honeycomb is one of the market's most-moved items"
    row = honey[0]
    assert "4,465" in row and "3,727" in row, row
    assert "8,192" not in row, "in and out were summed into one figure"


def test_items_are_ranked_by_pieces_not_by_coins():
    """A cheap high-volume line must not sink under one expensive sale."""
    data = L.market_items(LISTED, months=3, limit=30)
    moved = [r["moved"] for r in data["rows"]]
    assert moved == sorted(moved, reverse=True), moved[:6]


def test_a_listed_market_shows_this_to_everyone():
    assert _block(LS.stock("", LISTED)) is not None, "§6.7: a listing discloses"
    assert _block(LS.stock(STRANGER, LISTED)) is not None


def test_a_private_market_shows_it_to_its_owner_only():
    assert _block(LS.stock(OWNER, PRIVATE)) is not None, \
        "an owner was locked out of his own shop's ledger"
    assert _block(LS.stock(STRANGER, PRIVATE)) is None
    assert _block(LS.stock("", PRIVATE)) is None


def test_a_private_owner_view_says_it_is_private():
    blk = _block(LS.stock(OWNER, PRIVATE))
    assert "only you can see this" in blk["n"]


def test_a_market_with_no_filings_gets_no_block():
    assert LS._item_block("no_such_market", True, True) is None


def test_the_count_of_hidden_items_is_stated():
    """A truncated table that does not say it is truncated reads as complete."""
    blk = _block(LS.stock(OWNER, LISTED))
    data = L.market_items(LISTED, months=3, limit=30)
    if data["total_items"] > len(blk["r"]):
        assert "further item" in blk["n"], blk["n"]
    assert f"of {data['total_items']} items" in blk["n"], blk["n"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("market items: ok")
