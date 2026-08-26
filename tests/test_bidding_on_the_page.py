"""Bidding happens on the page that shows the lot.

The last of the duplication. `/auctions` and `/lands` owned the bidding flow and
the designed pages could only link to them, so the site had a page to READ a lot
on and a different page to BID on it — the same split as `/canvas`, one level
down.

Two things the tests are here for.

THE FORM KEY IS BOUND TO THE LOT. `money_post` checks it against the thing the
request is actually about, so a key minted for lot 7 cannot be spent on lot 9.
That is a server-side check; minting per lot here is what makes the page able to
satisfy it rather than reusing one key for everything on screen.

A SELLER CANNOT BID ON HIS OWN LOT. The server refuses it in `_validate_bid`;
offering the box anyway would be a button whose only purpose is to be refused.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_live as L          # noqa: E402
import abex_livescreens as LS  # noqa: E402
import abex_render as R        # noqa: E402
import canvas_web              # noqa: E402

LOTS = [
    {"id": 7, "kind": "item", "mode": "auction", "title": "Netherite template",
     "seller_id": "SELLER", "current_bid": 4800, "min_increment_pct": 5.0,
     "reserve": 1000},
    {"id": 9, "kind": "land", "mode": "auction", "title": "Sapidorf plot",
     "seller_id": "SELLER", "current_bid": 0, "reserve": 25000},
    {"id": 11, "kind": "item", "mode": "auction", "title": "My own lot",
     "seller_id": "ME", "current_bid": 100, "reserve": 50},
    {"id": 13, "kind": "item", "mode": "fixed", "title": "Buy it now",
     "seller_id": "SELLER", "buy_now": 500, "reserve": 500},
]


def _blocks(kind, user="ME", csrf="TOKEN"):
    real = L._db

    class _Db:
        @staticmethod
        def get_active_land_listings():
            return LOTS

    L._db = lambda: _Db
    try:
        return LS._bid_blocks(kind, user, csrf)
    finally:
        L._db = real


def test_items_and_land_get_their_own_lots():
    assert [b["bid"]["lot_id"] for b in _blocks("auctions")] == [7]
    assert [b["bid"]["lot_id"] for b in _blocks("lands")] == [9]


def test_a_seller_is_not_offered_a_box_for_his_own_lot():
    assert 11 not in [b["bid"]["lot_id"] for b in _blocks("auctions")]


def test_a_fixed_price_listing_is_not_an_auction():
    assert 13 not in [b["bid"]["lot_id"] for b in _blocks("auctions")]


def test_the_minimum_is_the_engines_minimum():
    """4,800c at a 5% step is 5,040c — computed by `estates_web._min_next_bid`,
    not by a second implementation here."""
    import estates_web
    box = _blocks("auctions")[0]["bid"]
    assert box["minimum"] == int(estates_web._min_next_bid(LOTS[0])) == 5040


def test_each_lot_gets_its_own_form_key():
    import vt_web_shell as shell
    a = _blocks("auctions")[0]["bid"]["key"]
    b = _blocks("lands")[0]["bid"]["key"]
    assert a and b and a != b, "one key would be spendable on the wrong lot"
    # `form_key_subject` returns the subject alone — "7", not "bid:7".
    assert shell.form_key_subject(a) == "7", shell.form_key_subject(a)
    assert shell.form_key_subject(b) == "9", shell.form_key_subject(b)
    # And the server's own check agrees the key belongs to that lot and no other.
    assert not shell.is_subject_mismatch(a, "ME", "bid:7")
    assert shell.is_subject_mismatch(a, "ME", "bid:9"), \
        "lot 7's key was accepted for lot 9"


def test_no_box_without_a_session_and_a_token():
    assert _blocks("auctions", user="", csrf="TOKEN") == []
    assert _blocks("auctions", user="ME", csrf="") == []


def test_the_box_says_a_bid_is_a_hold():
    box = _blocks("auctions")[0]
    assert "HOLD" in box["bid"]["hint"]
    assert "released the moment somebody outbids" in box["bid"]["hint"]
    html = R._block(box)
    assert 'class="bidbox"' in html
    assert 'data-min="5040"' in html


def test_the_flow_previews_before_it_commits():
    js = canvas_web.CANVAS_JS
    assert "/api/estates/bid/preview" in js
    assert "/api/estates/bid" in js
    assert js.index("bid/preview") < js.index('post("/api/estates/bid"'), \
        "it would place the bid before showing the figures"
    assert "window.confirm" in js
    assert "idempotency_key" in js


def test_a_replayed_bid_is_named_as_one():
    assert "one hold exists, not two" in canvas_web.CANVAS_JS


def test_a_network_error_never_says_try_again():
    js = canvas_web.CANVAS_JS
    tail = js.split("function wireBid")[1]
    assert "do not re-send" in tail, tail[-400:]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("bidding: ok")
