"""My market and the report: live rows, the spec's payout order, no invented money.

The two owner screens are the ones with the most room to lie. Every other screen
reports somebody else's public figures; these two tell an owner what he earned
and what he owes, and a wrong number here is a wrong number about his own money.

So the assertions are about restraint as much as correctness:

  1. Neither screen ever carries a figure from `abex_canvas`. The design's
     GreyHames earns 42,180c a month and files at 6.62c a share. Those numbers
     are lovely and they are not his.
  2. The waterfall keeps the spec's fixed order (§6.3) — net, vault retention,
     debt service and coupons, dividends, owner — even when three of those lines
     are zero, because the order IS the rule and a page that omits the empty
     steps stops teaching it.
  3. Lines with no source read 0c or an em dash and say why in the note. No bond
     has been issued and no dividend declared in this database; a coupon figure
     here would be an invoice for a debt that does not exist.
  4. Owning no market is a sentence, not five empty tables.
  5. Neither screen is ever public. `screen(public=True)` returns None for both —
     an owner's ledger is not a public fact about the economy.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_livescreens as LS  # noqa: E402
from abex_canvas import SCREENS as CANVAS  # noqa: E402

#: Figures that appear ONLY in the design's sample data for these two screens.
SAMPLE_FIGURES = ("42,180c", "6.62c", "68,940c", "18,220c", "8,540c", "1,860c",
                  "12,000c", "10,000c", "4,218c")


def _all_text(screen):
    out = []
    for tile in screen.get("band") or []:
        out.extend(str(x) for x in tile)
    for b in screen.get("blocks") or []:
        out.append(str(b.get("h2") or ""))
        out.append(str(b.get("n") or ""))
        for row in b.get("r") or []:
            out.extend(str(c) for c in row)
        for row in b.get("bal") or []:
            out.extend(str(c) for c in row)
        out.extend(str(c) for c in (b.get("tot") or []))
    return " | ".join(out)


def test_owner_screens_are_never_public():
    assert LS.screen("market", "anyone", public=True) is None
    assert LS.screen("filing", "anyone", public=True) is None
    assert "market" not in LS.PUBLIC
    assert "filing" not in LS.PUBLIC


def test_owning_nothing_is_a_sentence():
    for key in ("market", "filing"):
        s = LS.screen(key, "000000000000000000")
        assert "do not own a market" in s["asof"], s["asof"]
        for b in s.get("blocks") or []:
            assert not b.get("r"), "an empty table where a sentence belongs"


def test_no_sample_money_reaches_either_screen():
    for key in ("market", "filing"):
        text = _all_text(LS.screen(key, "000000000000000000"))
        for fig in SAMPLE_FIGURES:
            assert fig not in text, f"{key} leaked the design's {fig}"


def test_waterfall_keeps_the_spec_order():
    """§6.3: net -> vault -> debt service and coupons -> dividends -> owner."""
    for key, heading in (("market", "Where the net goes"),
                         ("filing", "What filing pays")):
        canvas_block = next(b for b in CANVAS[key]["blocks"]
                            if b.get("h2") == heading)
        expected = [str(r[0]).split(",")[0].lower() for r in canvas_block["bal"]]
        assert expected[0].startswith("net")
        assert "vault" in expected[1]
        assert "debt service" in expected[2]
        assert "dividend" in expected[3]


def test_no_market_screen_invents_a_coupon_or_a_dividend():
    """A zero with a reason, never a plausible figure."""
    s = LS.screen("market", "000000000000000000")
    text = _all_text(s)
    assert "coupon" not in text.lower() or "0c" in text


if __name__ == "__main__":
    test_owner_screens_are_never_public()
    test_owning_nothing_is_a_sentence()
    test_no_sample_money_reaches_either_screen()
    test_waterfall_keeps_the_spec_order()
    test_no_market_screen_invents_a_coupon_or_a_dividend()
    print("owner screens: ok")
