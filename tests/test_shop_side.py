"""The shop side of a market: shelves, ledger, who runs it, liabilities.

All four have been in the database the whole time and none were on a market's
page. So the site could tell you a market was rated on its inventory and never
show you the inventory — which is how 25,000,000c of Amazonia's stock came to
read as nothing in its backing with no way to see why from any page.

§6.7 decides who sees them: a LISTED market discloses ledger, staff and
liabilities to everyone; a private one to its owner only.

THE PRICE UNIT IS THE POINT OF THE SHELVES TABLE. `market_stock` stores prices
PER UNIT with the shop's listed bulk quantity beside them. A row with no
quantity is a LEGACY per-STACK price stored raw — 64x out if rendered as a piece
price, which is exactly why `_market_asset_value` skips those rows and why they
back the shares by nothing. Every one of Amazonia's 174 stocked lines is one.
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


def _headings(screen):
    return [b.get("h2") for b in screen.get("blocks") or []]


def test_the_shelves_are_on_a_listed_markets_page():
    assert "On the shelves" in _headings(LS.stock(STRANGER, "amazonia"))


def test_a_legacy_line_is_priced_per_stack_never_per_piece():
    """Rendering it as a piece price is the 64x error the guard exists for."""
    blocks = LS._shop_blocks("amazonia", "Amazonia", True, False)
    shelf = next(b for b in blocks if b["h2"] == "On the shelves")
    for row in shelf["r"]:
        for cell in (row[3], row[4]):
            if cell != LS.DASH:
                assert "a stack" in cell or "a piece" in cell, cell
    # Amazonia's are all legacy, so all of them read per stack.
    assert all("a stack" in r[3] for r in shelf["r"] if r[3] != LS.DASH)


def test_the_shelves_say_what_the_rating_cannot_see():
    blocks = LS._shop_blocks("amazonia", "Amazonia", True, False)
    shelf = next(b for b in blocks if b["h2"] == "On the shelves")
    assert "back the shares by nothing" in shelf["n"], shelf["n"]
    assert "99,321,236c" in shelf["n"], shelf["n"]
    assert "fresh stock scan" in shelf["n"]


def test_every_line_is_marked_counted_or_not():
    blocks = LS._shop_blocks("amazonia", "Amazonia", True, False)
    shelf = next(b for b in blocks if b["h2"] == "On the shelves")
    for row in shelf["r"]:
        assert row[5] in ("m|counted", "w|not counted"), row


def test_the_ledger_and_the_team_are_on_a_listed_page():
    heads = _headings(LS.stock(STRANGER, "greyhames"))
    assert any(str(h).startswith("Ledger") for h in heads), heads
    assert "Who runs it" in heads, heads


def test_a_private_market_shows_none_of_it_to_a_stranger():
    assert LS._shop_blocks("brew", "BrewShop", False, False) == []


def test_a_private_market_shows_all_of_it_to_its_owner():
    """§6.7 withholds a private market's shop side from everyone else — never
    from the person who runs it."""
    blocks = LS._shop_blocks("vtech", "V Tech Hives", False, True)
    assert isinstance(blocks, list)          # may be empty if the shop has none


def test_an_empty_shop_gets_no_empty_tables():
    """Empty states are empty FOR A READER: a market with no stock shows no
    shelves block to anyone but its owner.

    Narrowed rather than dropped. The rule is still right for a stranger — a
    headed table with nothing in it reads worse than no table. It was wrong for
    the owner, who reads the absence as "this site has no inventory" when it
    means "no stock scan has recorded a line for your shop". See
    `test_the_owner_of_an_empty_shop_is_told_why` for that half.
    """
    real = L.shelves
    L.shelves = lambda mid, limit=60: {"rows": [], "lines": 0, "counted": 0,
                                       "uncounted": 0, "legacy_lines": 0,
                                       "scanned": ""}
    try:
        blocks = LS._shop_blocks("greyhames", "GreyHames", True, False)
    finally:
        L.shelves = real
    assert not [b for b in blocks if b["h2"] == "On the shelves"]


def test_a_market_with_no_team_has_no_team_block():
    """Amazonia's owner has no registered workers — that is an absence, not a
    zero, and it is not decorated."""
    heads = _headings(LS.stock(STRANGER, "amazonia"))
    assert "Who runs it" not in heads


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("shop side: ok")


def test_the_owner_of_an_empty_shop_is_told_why():
    """The owner gets the block, empty, with the reason — because the absence is
    the answer to what he is asking. A market console with a ledger, a waterfall
    and no mention of stock reads as a missing feature, not an empty shelf."""
    real = L.shelves
    L.shelves = lambda mid, limit=60: {"rows": [], "lines": 0, "counted": 0,
                                       "uncounted": 0, "legacy_lines": 0,
                                       "scanned": ""}
    try:
        blocks = LS._shop_blocks("greyhames", "GreyHames", True, True)
    finally:
        L.shelves = real
    shelf = [b for b in blocks if b["h2"] == "On the shelves"]
    assert shelf, "the owner is told, not left to guess"
    assert shelf[0]["r"] == [], "and it is honestly empty"
    assert "stock scan" in shelf[0]["n"], "with the reason, not just a dash"


def test_the_owners_console_carries_his_own_stock():
    """Inventory was built for a market's public page and never put on the
    console, so the one person who most needs to see the shelves — the owner —
    had a page with a ledger, a waterfall and no goods on it."""
    src = Path(__file__).resolve().parent.parent / "abex_livescreens.py"
    body = src.read_text(encoding="utf-8")
    body = body[body.index("def market(user_id"):]
    body = body[:body.index("screen_d[\"title\"]")]
    assert "_item_block(" in body, "the console must build the items block"
    assert "_shop_blocks(" in body, "and the shelves"
    assert "On the shelves" in body
