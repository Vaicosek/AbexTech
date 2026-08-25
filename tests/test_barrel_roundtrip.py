"""A barrel converts to pieces and back to the same number of barrels.

`unit_to_pieces` carries an AUDIT FIX comment: a barrel is 54 SLOTS, so for a
stackable item it is 54 x stack_size pieces, and the flat 54 the old code used
disagreed 64x with the per-barrel payout `_coin_rates_for_order` advertises.

Its inverse, `pieces_to_unit`, never got the same fix. It kept dividing by the
flat 54, so the pair did not close: one barrel became 3,456 pieces and 3,456
pieces came back as "64 barrels". That figure is what `fmt_qty` prints as an
order's REMAINING quantity, on the Discord order card and on Work — a worker
filling a one-barrel order would have been told he still owed 64 of them.

No barrel-unit order exists in the database today, which is the only reason this
never bit anybody. It was live in the code and waiting for the first one.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

# The real `Restocker_main`, not the stub `land_stubs.install_core()` swaps in —
# the point of this file is the arithmetic in the SHIPPED source. Importing the
# whole module needs discord.py, so the three functions under test are lifted
# out of the file by name and executed here. If they are renamed or moved, this
# fails loudly rather than passing against a stub that agrees with itself.
import ast  # noqa: E402

SOURCE = (Path(__file__).resolve().parent.parent / "Restocker_main.py").read_text(
    encoding="utf-8")
WANTED = ("unit_to_pieces", "pieces_to_unit", "fmt_qty", "_coin_rates_for_order",
          "_get_coin_price")

_tree = ast.parse(SOURCE)
_ns = {"BARREL_PIECES": 54}
_found = set()
for _node in _tree.body:
    if isinstance(_node, ast.FunctionDef) and _node.name in WANTED:
        exec(compile(ast.Module([_node], []), "Restocker_main.py", "exec"), _ns)
        _found.add(_node.name)
missing = sorted(set(WANTED) - _found)
assert not missing, f"not found in Restocker_main.py: {missing}"


class core:  # noqa: N801 - stands in for the module
    unit_to_pieces = staticmethod(_ns["unit_to_pieces"])
    pieces_to_unit = staticmethod(_ns["pieces_to_unit"])
    fmt_qty = staticmethod(_ns["fmt_qty"])
    _coin_rates_for_order = staticmethod(_ns["_coin_rates_for_order"])

STACKABLE = {"unit_type": "barrels", "stack_size": 64, "stackable": True}
LOOSE = {"unit_type": "barrels", "stack_size": 1, "stackable": False}


def test_a_barrel_is_54_slots_times_the_stack():
    assert core.unit_to_pieces(1, "barrels", stackable=True, stack_size=64) == 54 * 64
    assert core.unit_to_pieces(1, "barrels", stackable=False, stack_size=1) == 54


def test_the_round_trip_closes_for_stackable_items():
    for n in (1, 3, 54, 100):
        pieces = core.unit_to_pieces(n, "barrels", stackable=True, stack_size=64)
        back, unit = core.pieces_to_unit(STACKABLE, pieces)
        assert unit == "barrels"
        assert back == n, f"{n} barrels came back as {back}"


def test_the_round_trip_closes_for_loose_items():
    for n in (1, 2, 7):
        pieces = core.unit_to_pieces(n, "barrels", stackable=False, stack_size=1)
        back, _unit = core.pieces_to_unit(LOOSE, pieces)
        assert back == n, f"{n} barrels came back as {back}"


def test_the_displayed_remainder_matches_the_order():
    """`fmt_qty` is what a worker reads. One barrel remaining says one."""
    order = dict(STACKABLE)
    order["amount"] = 1
    pieces = core.unit_to_pieces(1, "barrels", stackable=True, stack_size=64)
    assert core.fmt_qty(order, pieces) == "1 barrels", core.fmt_qty(order, pieces)


def test_conversion_agrees_with_what_a_barrel_is_paid():
    """`_coin_rates_for_order` prices a barrel at 54 x stack_size pieces. If the
    quantity function and the pay function disagree about what a barrel is, the
    difference is somebody's wages."""
    order = dict(STACKABLE)
    _piece, _stack, _barrel, pieces_per_barrel = core._coin_rates_for_order(
        order, {"items": {}})
    assert pieces_per_barrel == core.unit_to_pieces(
        1, "barrels", stackable=True, stack_size=64)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("barrel round trip: ok")
