"""Orders and Work quote the same pay for the same order.

They read one table and they must not disagree about a number a worker sizes a
job by. The first draft of the Orders screen did: it read `orders.coin_per_piece`
directly, which is NULL on real orders because the rate is derived from the item
book, so Orders printed an em dash for the open Diamond job while Work — which
asks `Restocker_main._coin_rates_for_order` — printed 100.00c a piece and a
691,200c total for the same row.

The rule this locks in is the one `abex_live` states at the top of the file:
call the canonical function, never a parallel one. Both screens now ask the
bot's own rate function, so they cannot drift.

The second assertion is about the unit. `_coin_rates_for_order` returns a second
rate that is per BARREL — 3,456 pieces — and printing it under a label a worker
reads as a stack of 64 overstates the pay 54-fold. Both screens quote per piece,
and per stack of 64 where the item stacks.
"""
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_live       # noqa: E402
import abex_livescreens as LS  # noqa: E402

ORDER = {
    "id": 53, "item": "Diamond", "market_id": "vtech", "shop": "",
    "requested": 6912, "amount": 108, "unit_type": "stacks", "stack_size": 64,
    "stackable": 1, "coin_per_piece": None, "status": "open", "claims": [],
}

PIECE_RATE = 100.0
BARREL_RATE = PIECE_RATE * 3456      # the rate that must never reach a label


class _FakeCore:
    """Only the three calls both screens make."""

    @staticmethod
    def _load_items():
        return {"items": {}}

    @staticmethod
    def _coin_rates_for_order(order, items):
        return (PIECE_RATE, BARREL_RATE)

    @staticmethod
    def _coins_for_pieces(order, pieces, items):
        return PIECE_RATE * int(pieces)


class _FakeDb:
    @staticmethod
    def load_orders():
        return [dict(ORDER)]

    @staticmethod
    def get_markets():
        return {"vtech": {"name": "V Tech Hives"}}


def _with_fakes(fn):
    real_core, real_db = abex_live._core, abex_live._db
    abex_live._core = lambda: _FakeCore
    abex_live._db = lambda: _FakeDb
    try:
        return fn()
    finally:
        abex_live._core, abex_live._db = real_core, real_db


def test_orders_quotes_the_canonical_rate_not_the_null_column():
    screen = _with_fakes(lambda: LS.orders("someone"))
    row = screen["blocks"][0]["r"][0]
    pay, total = row[3], row[4]
    assert pay != LS.DASH, "pay came out blank — the NULL column was read again"
    assert "100.00c a piece" in pay, pay
    assert total == "691,200c", total


def test_orders_never_prints_the_barrel_rate_as_a_stack():
    screen = _with_fakes(lambda: LS.orders("someone"))
    pay = screen["blocks"][0]["r"][0][3]
    assert f"{BARREL_RATE:,.2f}c" not in pay, f"barrel rate reached a label: {pay}"
    assert "per stack of 64" in pay, pay
    assert f"{PIECE_RATE * 64:,.2f}c per stack" in pay, pay


def test_quantity_is_the_unit_the_order_was_written_in():
    """`requested` is pieces, `amount` is stacks. 108 stacks, never 6,912."""
    screen = _with_fakes(lambda: LS.orders("someone"))
    qty = screen["blocks"][0]["r"][0][2]
    assert qty == "108 stacks", qty


def test_no_core_means_a_dash_not_a_wrong_figure():
    real_core = abex_live._core
    real_db = abex_live._db

    def _boom():
        raise RuntimeError("no discord in this process")

    abex_live._core = _boom
    abex_live._db = lambda: _FakeDb
    try:
        screen = LS.orders("someone")
    finally:
        abex_live._core, abex_live._db = real_core, real_db
    row = screen["blocks"][0]["r"][0]
    assert row[3] == LS.DASH and row[4] == LS.DASH, row


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("orders pay: ok")
