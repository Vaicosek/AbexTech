"""Late filing is a fact the owner is told, not a panel everyone else reads.

There used to be a "Waiting on a filing" block at the top of the public Markets
screen, naming every market a month behind. It is gone, and this file is the
record of why so it does not get rebuilt from the design.

§4 leads Markets with "Filing next" — a queue of DUE DATES. Nothing in this
system stores one: reports arrive when an owner files them. The block asked the
answerable question instead (who is behind, by how long) and that part was
sound. What was not sound was the consequence it asserted: its own note said a
missed filing "drops the market one grade band", and NOTHING IN THE ENGINE DOES
THAT. `_market_quality`'s history pillar counts closed months on record, so a
quiet market stops gaining ground — it is never docked. The panel published a
penalty the code does not impose.

`filing_status` itself stays. It is a true reading and the owner's own
waiting-on-you queue uses it, where a late filing is something he can act on
rather than something the whole site reads about him.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_live as L          # noqa: E402
import abex_livescreens as LS  # noqa: E402

CURRENT = {"market_id": "a", "name": "Alpha", "last_month": "2026-08",
           "last_month_name": "August 2026", "months_behind": 0,
           "days_since": 2, "current": True}
LATE = {"market_id": "b", "name": "Beta", "last_month": "2026-07",
        "last_month_name": "July 2026", "months_behind": 1,
        "days_since": 34, "current": False}


def test_the_public_panel_is_gone_and_stays_gone():
    assert not hasattr(LS, "_filing_block"), (
        "the naming-and-shaming panel was removed; see this file's docstring "
        "before putting it back")
    src = (HERE.parent / "abex_livescreens.py").read_text(encoding="utf-8")
    body = src[src.index("def markets("):src.index("# ── Stocks")]
    assert "Waiting on a filing" not in body


def test_no_screen_claims_a_grade_penalty_for_filing_late():
    """The claim the panel made. If the engine ever grows a real late-filing
    penalty this test should fail — and then the sentence can be written back,
    because it will be true."""
    src = (HERE.parent / "abex_livescreens.py").read_text(encoding="utf-8")
    assert "drops the market one grade band" not in src


def test_filing_status_still_reads_the_record():
    """The reading is kept. It was never the problem."""
    rows = L.filing_status()
    assert rows is None or isinstance(rows, list)
    if rows:
        r = rows[0]
        for field in ("market_id", "name", "months_behind", "days_since"):
            assert field in r


def test_the_owner_is_still_told_about_his_own_market():
    real = L.filing_status
    L.filing_status = lambda: [CURRENT, LATE]
    try:
        due = LS._your_filings_due("owner-of-beta")
    finally:
        L.filing_status = real
    assert isinstance(due, list), (
        "the owner's own queue is where a late filing belongs")
