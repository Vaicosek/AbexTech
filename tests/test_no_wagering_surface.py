"""No betting surface exists, and this file is here to keep it that way.

The platform does no wagering of any kind. That is not a styling preference: an
operator running a book — even a rake-only pari-mutuel one where players stake
against each other and the house never takes a side — is in a materially
different position from somebody running a shop, and this platform is not going
to be in that position.

The surface existed once. `estates_web` served pari-mutuel markets at
`/predictions` with pools, indicative odds, a rake and an escrow stake flow, and
it was in the hub nav. It has been removed: route, nav entry, API, UI, screen
builder, sample rows and the fee-schedule line that advertised a rake. This test
fails if any of it comes back by accident — a re-added nav tuple, a route, a
`_SECTIONS_DEF` entry, a tier key.

The guardrails that remain are guardrails and nothing else: `games` is a
reserved ledger identity with no command surface, and `gambling_blocked` is a
wallet flag so borrowed coins could never fund a wager. A lock on a door the
building does not have is not evidence of the room, and neither is asserted
against here.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import estates_web   # noqa: E402
import vt_web_shell  # noqa: E402
import abex_web      # noqa: E402
import abex_tiers    # noqa: E402
import abex_screens  # noqa: E402
import hub_web       # noqa: E402

BANNED = ("bet", "betting", "wager", "casino", "gamble", "gambling",
          "prediction", "predictions", "odds", "stake", "stakes", "parimutuel",
          "pari-mutuel")


def _looks_like_wagering(text: str) -> bool:
    low = str(text or "").lower()
    return any(w in low for w in BANNED)


def test_no_wagering_entry_in_the_nav():
    for key, label, path in vt_web_shell.NAV:
        assert not _looks_like_wagering(key), key
        assert not _looks_like_wagering(label), label
        assert not _looks_like_wagering(path), path


def test_no_wagering_section_in_estates():
    assert "predictions" not in estates_web._SECTIONS_DEF
    for key, d in estates_web._SECTIONS_DEF.items():
        assert not _looks_like_wagering(key), key
        assert not _looks_like_wagering(d["h1"]), d["h1"]
        assert not _looks_like_wagering(d["label"]), d["label"]


def test_no_wagering_handler_survives():
    for name in ("h_predictions", "h_markets", "h_stake", "h_stake_preview",
                 "_place_stake", "_stake_purpose", "_market_payload"):
        assert not hasattr(estates_web, name), f"estates_web.{name} is back"
    assert not hasattr(abex_screens, "betting"), "abex_screens.betting is back"


def test_no_wagering_route_under_the_designed_prefix():
    for path, key, title, _fn in abex_web.SCREENS:
        assert not _looks_like_wagering(path), path
        assert not _looks_like_wagering(key), key
        assert not _looks_like_wagering(title), title


def test_the_fee_schedule_advertises_no_rake():
    """A fee schedule is a product catalogue."""
    assert "betting" not in abex_tiers.DOMAINS
    for tier in abex_tiers.TIERS:
        for key in tier:
            assert not _looks_like_wagering(key), f"tier carries {key}"


def test_the_hub_nav_has_no_wagering_icon_or_blurb():
    assert "predictions" not in hub_web._ICONS
    for section in hub_web.sections():
        assert not _looks_like_wagering(section["key"]), section
        assert not _looks_like_wagering(section["label"]), section


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("no wagering surface: ok")
