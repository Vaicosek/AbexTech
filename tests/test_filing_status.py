"""Who has stopped filing — and why the block asks that instead of "filing next".

§4 leads the Markets screen with a queue of DUE DATES. Nothing in this system
stores one: reports arrive when an owner files them, and a date computed from
nothing looks exactly like a date that means something. So the block asks the
question the record can answer — who is behind, and by how long.

That is also the question that was actually needed. Two markets stopped filing
in mid-July and nobody noticed until a player said so in Discord; both would
have sat at the top of this block from the day they went quiet.

The rule the tests exist for: nobody behind means NO BLOCK. Not an empty table,
not a green "all current" panel. Everything filed is the normal state and does
not earn space — the same rule the rest of this codebase follows for absence.
"""
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_live as L          # noqa: E402
import abex_livescreens as LS  # noqa: E402


def _with_status(rows):
    real = L.filing_status
    L.filing_status = lambda: rows
    try:
        return LS._filing_block()
    finally:
        L.filing_status = real


CURRENT = {"market_id": "a", "name": "Alpha", "last_month": "2026-08",
           "last_month_name": "August 2026", "months_behind": 0,
           "days_since": 2, "current": True}
LATE = {"market_id": "b", "name": "Beta", "last_month": "2026-07",
        "last_month_name": "July 2026", "months_behind": 1,
        "days_since": 34, "current": False}
VERY_LATE = {"market_id": "c", "name": "Gamma", "last_month": "2026-06",
             "last_month_name": "June 2026", "months_behind": 2,
             "days_since": 70, "current": False}


def test_everyone_current_means_no_block_at_all():
    assert _with_status([CURRENT, dict(CURRENT, market_id="a2")]) is None


def test_no_data_means_no_block():
    assert _with_status([]) is None
    assert _with_status(None) is None


def test_only_the_late_markets_appear():
    blk = _with_status([CURRENT, LATE, VERY_LATE])
    names = [r[0] for r in blk["r"]]
    assert all("Alpha" not in n for n in names), names
    assert any("Beta" in n for n in names) and any("Gamma" in n for n in names)
    assert len(blk["r"]) == 2


def test_two_months_behind_is_loss_toned_and_one_is_warn():
    blk = _with_status([LATE, VERY_LATE])
    tones = {r[0].split("|")[-1]: r[2][:2] for r in blk["r"]}
    assert tones["Beta"] == "w|", tones
    assert tones["Gamma"] == "l|", tones


def test_the_market_name_links_to_its_page():
    blk = _with_status([LATE])
    assert blk["r"][0][0] == "A|/hub/stocks/b|Beta", blk["r"][0][0]


def test_the_note_counts_late_against_the_whole_register():
    blk = _with_status([CURRENT, LATE])
    assert "1 of 2 markets" in blk["n"], blk["n"]


def test_days_since_is_absent_not_zero_when_unknown():
    blk = _with_status([dict(LATE, days_since=None)])
    assert blk["r"][0][3] == LS.DASH


def test_the_real_register_flags_the_two_that_stopped():
    """Against the shipped database: Amazonia and ViridianMarket, both July."""
    status = L.filing_status()
    late = {r["name"] for r in status if r["months_behind"] > 0}
    assert late == {"Amazonia", "ViridianMarket"}, late
    for r in status:
        if r["name"] in late:
            assert r["last_month"] == "2026-07", r


def test_months_behind_counts_calendar_months():
    status = L.filing_status()
    for r in status:
        if r["current"]:
            assert r["months_behind"] == 0, r


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("filing status: ok")


# ── the owner's queue ──────────────────────────────────────────────────────

def _with_owned(status, owned):
    real_status, real_owned = L.filing_status, L.owned_markets
    L.filing_status = lambda: status
    L.owned_markets = lambda uid: [{"market_id": m, "name": m} for m in owned]
    try:
        return LS._your_filings_due("someone")
    finally:
        L.filing_status, L.owned_markets = real_status, real_owned


def test_a_late_market_you_own_reaches_your_queue():
    rows = _with_owned([LATE], ["b"])
    assert len(rows) == 1
    assert "File the report for Beta" in rows[0][0]
    assert "1 month behind" in rows[0][0]
    assert "34 days since" in rows[0][0]


def test_somebody_elses_late_market_does_not():
    """Being behind is public on Markets. Being TOLD about it is the owner's."""
    assert _with_owned([LATE], ["other"]) == []


def test_a_market_you_own_that_is_current_does_not():
    assert _with_owned([CURRENT], ["a"]) == []


def test_a_signed_out_reader_has_no_queue():
    assert LS._your_filings_due("") == []


def test_two_months_behind_escalates_in_the_queue_too():
    rows = _with_owned([VERY_LATE], ["c"])
    assert rows[0][1].startswith("l|"), rows[0]
    assert _with_owned([LATE], ["b"])[0][1].startswith("w|")


def test_the_real_owner_of_amazonia_is_told():
    rows = LS._your_filings_due("1080404147368628254")
    assert rows and "Amazonia" in rows[0][0], rows
