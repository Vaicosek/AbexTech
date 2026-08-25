"""One market's page: what it shows, and what it refuses to.

A reader deciding whether to buy asks "how has this one done", and neither the
Stocks screen (your positions) nor Markets (everyone's, one row each) answers
it. This page does. Which makes it the page with the most to give away, so the
rules are the disclosure ones.

  * §6.7 — a LISTED market discloses; a private one discloses nothing but its
    grade. A private market still gets a real page: it says it is private and
    shows the grade. A 404 would teach the reader nothing, and the grade is
    scored from the same pillars for everybody, which is why it can be shown.
  * The register is disclosed as SHAPE, never as names. How many accounts hold
    a security and how much of it is in someone else's hands are facts about the
    security. That one account holds 92,863 of GreyHames' 100,000 shares is a
    fact about a person; nothing here asks him to publish it.
  * "Your position" is not built for a signed-out reader rather than built and
    hidden — the same rule the rest of the public screens follow.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_live as L          # noqa: E402
import abex_livescreens as LS  # noqa: E402
import abex_render as R        # noqa: E402

OWNER = "1203738126850461738"

DETAIL = {
    "market_id": "acme", "name": "Acme", "listed": True,
    "grade": "AA", "backing": 1.7, "price": 6.4, "shares_out": 12000.0,
    "pe": 2.01, "treasury": 18400.0, "last_priced_month": "2026-07",
    "holders": 9, "free_float": 4000.0, "owner_holds": 8000.0,
    "your_shares": 0.0,
    "months": [
        {"month": "2026-08", "name": "August 2026", "income": 68940.0,
         "spent": 26760.0, "net": 42180.0, "change": 2280.0, "pct": 5.7},
        {"month": "2026-07", "name": "July 2026", "income": 60000.0,
         "spent": 20100.0, "net": 39900.0, "change": 3500.0, "pct": 9.6},
        {"month": "2026-06", "name": "June 2026", "income": 55000.0,
         "spent": 18600.0, "net": 36400.0, "change": None, "pct": None},
    ],
    "price_rows": [("Growth P/E multiple", "2.01×", "")],
    "series": {"points": [6.1, 6.3, 6.4], "window": "90 days"},
}


def _detail(**over):
    d = dict(DETAIL)
    d.update(over)
    return d


def _patched(detail):
    real = L.stock_detail
    L.stock_detail = lambda mid, uid="": detail
    try:
        return LS.stock("someone", "acme"), LS.stock("", "acme")
    finally:
        L.stock_detail = real


def _text(screen):
    out = []
    for b in screen.get("blocks") or []:
        out.append(str(b.get("h2") or ""))
        out.append(str(b.get("n") or ""))
        for row in (b.get("r") or []) + (b.get("bal") or []):
            out.extend(str(c) for c in row)
    return " | ".join(out)


def test_a_private_market_discloses_its_grade_and_nothing_else():
    signed_in, _public = _patched(_detail(listed=False))
    headings = [b.get("h2") for b in signed_in["blocks"]]
    assert headings == ["Private market"], headings
    text = _text(signed_in)
    for leaked in ("42,180c", "12,000", "6.40c", "2.01×", "August 2026"):
        assert leaked not in text, f"a private market disclosed {leaked}"
    assert "AA" in str(signed_in["band"]), "the grade is disclosed and was not"


def test_a_listed_market_shows_its_months_against_each_other():
    signed_in, _public = _patched(_detail())
    months = next(b for b in signed_in["blocks"] if b.get("h2") == "Month by month")
    aug, jul, jun = months["r"]
    assert aug[4] == "g|+2,280c" and aug[5] == "g|+5.7%", aug
    assert jul[4] == "g|+3,500c", jul
    # The oldest month on the page has nothing before it, and says so rather
    # than reading +0 — which would claim it was flat against a month nobody has.
    assert jun[4] == LS.DASH and jun[5] == LS.DASH, jun


def test_a_falling_month_is_loss_toned():
    d = _detail(months=[{"month": "2026-08", "name": "August 2026",
                         "income": 1.0, "spent": 2.0, "net": -500.0,
                         "change": -900.0, "pct": -69.2}])
    signed_in, _public = _patched(d)
    months = next(b for b in signed_in["blocks"] if b.get("h2") == "Month by month")
    assert months["r"][0][4].startswith("l|"), months["r"][0]
    assert months["r"][0][5].startswith("l|"), months["r"][0]


def test_the_register_is_shape_not_names():
    signed_in, _public = _patched(_detail())
    reg = next(b for b in signed_in["blocks"] if b.get("h2") == "The register")
    labels = [r[0] for r in reg["bal"]]
    assert "Shares outstanding" in labels and "Holder accounts" in labels
    assert "Market capitalisation" in labels
    text = _text(signed_in).lower()
    for word in ("discord", "@", "user_id"):
        assert word not in text, f"the register named somebody: {word}"


def test_your_position_is_not_built_for_a_stranger():
    signed_in, public = _patched(_detail(your_shares=250.0))
    assert any(b.get("h2") == "Your position" for b in signed_in["blocks"])
    assert not any(b.get("h2") == "Your position" for b in public["blocks"]), \
        "a signed-out reader was given a position block"


def test_no_position_block_when_you_hold_nothing():
    signed_in, _public = _patched(_detail(your_shares=0.0))
    assert not any(b.get("h2") == "Your position" for b in signed_in["blocks"])


def test_market_cap_is_price_times_shares():
    signed_in, _public = _patched(_detail())
    reg = next(b for b in signed_in["blocks"] if b.get("h2") == "The register")
    cap = dict((r[0], r[1]) for r in reg["bal"])["Market capitalisation"]
    assert cap == f"{6.4 * 12000.0:,.0f}c", cap


def test_the_page_renders_and_carries_a_live_chart():
    signed_in, _public = _patched(_detail())
    html = R.screen_html(signed_in, owner=True)
    assert "<polyline" in html
    assert 'data-src="/api/series/market/acme?days=90"' in html


def test_a_real_market_page_builds_end_to_end():
    """Against the shipped database, not a fixture."""
    screen = LS.stock(OWNER, "greyhames")
    assert screen["title"] == "GreyHames"
    assert R.screen_html(screen, owner=True)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("stock page: ok")
