"""Banking happens on the page that shows the balances.

The second-largest piece of the duplication, and the same argument as bidding:
`/banking` owned every money instruction and the designed screen could only put
a button through to it, so the site had a page to READ your wallet on and a
different page to MOVE it from. Two pages meant two copies of the wallet, the
savings balance and the loan — and the first time they disagree, the figure
somebody confirmed is the stale one.

What these tests hold down.

ONE MINT PER RENDER. `mint_form_key` issues a fresh key every call. Asking twice
for the same instruction leaves one of the pair claimed and unused, and the
in-flight lookup would then find a key the browser was never handed. So the keys
are minted once in `banking()` and shared by both blocks.

AN UNANSWERED INSTRUCTION HAS NO BUTTON. When the bank has not confirmed the last
deposit, a second press can only 409 — and the first one may already have been
applied. The box renders with no button at all and says why.

NO KEY, NO BOX. `_keys_for` declines to mint for a subject it cannot sign
unambiguously. A box without a key would submit and be refused as
`bad_form_key`, so it is dropped instead of shown.

NOTHING IS PRICED HERE. No figure on this page is computed for the confirm
screen. `/api/banking/preview` re-reads the account when the button is pressed;
the box carries the instruction and its key and nothing else of consequence.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_livescreens as LS  # noqa: E402
import abex_render as R        # noqa: E402
import canvas_web              # noqa: E402

ACCT = {
    "ok": True,
    "savings": {"balance": 40000, "apr": 3.0, "accrued_this_month": 120},
    "loan": {"id": 4, "outstanding": 12000, "apr": 9.0, "payoff_today": 12400,
             "accrued_interest": 400, "principal": 15000, "due": "2026-09-01"},
    "bonds": [{"id": "B-201", "face": 10000, "apr": 6.0, "matures": "2026-12-01",
               "matured": False, "redeem_value_today": 10120,
               "early_redemption_penalty": 300, "earned_so_far": 420,
               "interest_at_maturity": 600},
              {"id": "B-77", "face": 5000, "apr": 5.0, "matures": "2026-08-01",
               "matured": True, "redeem_value_today": 5200,
               "early_redemption_penalty": 0, "earned_so_far": 200,
               "interest_at_maturity": 200}],
    "bond_terms": [{"term_days": 30, "apr": 5.0, "min_face": 1000},
                   {"term_days": 90, "apr": 6.5, "min_face": 5000}],
    "limit": {"headroom": 8000, "amount": 20000, "components": []},
}

UID, CSRF = "1234", "csrf-token"


class FakeKeys:
    """Stands in for `banking_web._keys_for`, counting how often it is asked."""

    def __init__(self, in_flight=None, drop=()):
        self.calls = 0
        self.in_flight = in_flight or {}
        self.drop = set(drop)

    def __call__(self, uid, acct):
        self.calls += 1
        keys = {"deposit": "K-dep", "withdraw": "K-wd", "repay": "K-rep",
                "bond_buy": {"30": "K-b30", "90": "K-b90"},
                "bond_redeem": {"B-201": "K-r201", "B-77": "K-r77"}}
        for d in self.drop:
            if ":" in d:
                p, sub = d.split(":", 1)
                keys[p].pop(sub, None)
            else:
                keys.pop(d, None)
        return keys, self.in_flight


def _boxes(fake, available=50000):
    keys, flight = fake(UID, ACCT)
    out = LS._money_boxes(UID, CSRF, ACCT, available, keys, flight)
    for b in LS._bond_blocks(UID, CSRF, ACCT, available, keys, flight):
        out.extend(b.get("money") or [])
    return out


def _by_action(boxes):
    return {(b["action"], str(b.get("subject") or "")): b for b in boxes}


def test_every_instruction_has_a_box():
    got = _by_action(_boxes(FakeKeys()))
    for want in [("deposit", ""), ("withdraw", ""), ("repay", ""),
                 ("bond_buy", "30"), ("bond_buy", "90"),
                 ("bond_redeem", "B-201"), ("bond_redeem", "B-77")]:
        assert want in got, f"no box for {want}"


def test_each_box_carries_its_own_key_and_the_token():
    for b in _boxes(FakeKeys()):
        assert b["key"], f"{b['action']} has no key"
        assert b["csrf"] == CSRF
        assert b["url"].startswith("/api/banking/")


def test_bond_keys_are_bound_to_their_own_bond():
    got = _by_action(_boxes(FakeKeys()))
    assert got[("bond_redeem", "B-201")]["key"] != got[("bond_redeem", "B-77")]["key"]
    assert got[("bond_buy", "30")]["key"] != got[("bond_buy", "90")]["key"]
    # And the id rides in the body, so the server can check the two agree.
    assert got[("bond_redeem", "B-201")]["extra"] == {"bond_id": "B-201"}
    assert got[("bond_buy", "90")]["extra"] == {"term_days": 90}


def test_a_subject_that_cannot_be_signed_gets_no_box():
    got = _by_action(_boxes(FakeKeys(drop=["bond_redeem:B-201"])))
    assert ("bond_redeem", "B-201") not in got
    assert ("bond_redeem", "B-77") in got, "the others must survive"


def test_an_unanswered_instruction_renders_without_a_button():
    flight = {"deposit": {"age_seconds": 600, "subjects": {"": {"age_seconds": 600}}}}
    got = _by_action(_boxes(FakeKeys(in_flight=flight)))
    dep = got[("deposit", "")]
    assert dep["stuck"], "a stuck deposit must say so"
    assert "may already have been applied" in dep["stuck"]
    html = R._moneybox({"money": [dep]})
    assert "mnygo" not in html, "a stuck box must offer no button"
    assert "class=\"moneybox stuck\"" in html
    # The others are untouched.
    assert not got[("withdraw", "")]["stuck"]
    assert "mnygo" in R._moneybox({"money": [got[("withdraw", "")]]})


def test_the_amount_cap_never_exceeds_the_wallet():
    got = _by_action(_boxes(FakeKeys(), available=7000))
    assert got[("deposit", "")]["cap"] == 7000
    assert got[("repay", "")]["cap"] == 7000, "capped by the wallet, not the payoff"
    got = _by_action(_boxes(FakeKeys(), available=99000))
    assert got[("repay", "")]["cap"] == 12400, "and never more than settles the loan"


def test_a_redemption_asks_for_no_amount():
    got = _by_action(_boxes(FakeKeys()))
    assert got[("bond_redeem", "B-201")]["amount"] is False
    html = R._moneybox({"money": [got[("bond_redeem", "B-201")]]})
    assert "<input" not in html, "there is no amount to type for a redemption"
    assert "mnygo" in html


def test_an_unmatured_bond_says_so_before_it_is_pressed():
    got = _by_action(_boxes(FakeKeys()))
    early = got[("bond_redeem", "B-201")]
    assert "Not matured" in early["hint"]
    assert early["quiet"] is True, "the early redemption is not the primary button"
    assert got[("bond_redeem", "B-77")]["quiet"] is False


def test_keys_are_minted_once_per_render(monkeypatch):
    fake = FakeKeys()
    import banking_web
    monkeypatch.setattr(banking_web, "_keys_for", fake)
    monkeypatch.setattr(LS, "_bank_keys",
                        lambda uid, acct: banking_web._keys_for(uid, acct))
    keys, flight = LS._bank_keys(UID, ACCT)
    LS._money_boxes(UID, CSRF, ACCT, 50000, keys, flight)
    LS._bond_blocks(UID, CSRF, ACCT, 50000, keys, flight)
    assert fake.calls == 1, f"minted {fake.calls} times, not once"


def test_no_box_without_a_session_token():
    keys, flight = FakeKeys()(UID, ACCT)
    assert LS._money_boxes(UID, "", ACCT, 50000, keys, flight) == []
    assert LS._bond_blocks(UID, "", ACCT, 50000, keys, flight) == []
    assert LS._money_boxes("", CSRF, ACCT, 50000, keys, flight) == []


def test_no_box_when_the_bank_is_not_answering():
    assert LS._money_boxes(UID, CSRF, {}, 50000, {}, {}) == []
    assert LS._bond_blocks(UID, CSRF, {}, 50000, {}, {}) == []


def test_the_page_no_longer_sends_anyone_to_a_second_bank_page():
    src = Path(HERE.parent / "abex_livescreens.py").read_text(encoding="utf-8")
    banking = src[src.index("def banking("):]
    banking = banking[:banking.index("\n#: key -> builder")]
    assert "Open the bank" not in banking, "the button through to /banking is gone"
    assert '"/banking"' not in banking


def test_the_browser_previews_before_it_commits():
    js = canvas_web.CANVAS_JS
    assert "/api/banking/preview" in js
    i_prev = js.index("/api/banking/preview")
    i_wire = js.index("function wireMoney")
    assert i_prev > i_wire
    # A network failure is unknown, not failed.
    tail = js[i_wire:i_wire + 6000]
    assert "do not re-send" in tail
    assert "X-CSRF-Token" in tail


def test_nothing_priced_by_the_page_is_submitted():
    """The body that commits is the instruction, its key, and its subject.

    Hints quote figures — that is the point of a hint — but no figure the page
    computed is ever SENT. `data-extra` is the whole of what rides along besides
    the amount typed and the key, so it is the thing to hold down: a term or a
    bond id, never a price, a payoff or a balance.
    """
    got = _by_action(_boxes(FakeKeys()))
    allowed = {"bond_id", "term_days"}
    for (action, subject), b in got.items():
        assert set(b["extra"]) <= allowed, (
            f"{action} submits {sorted(set(b['extra']) - allowed)}, "
            f"which the server would have to trust")
    # `data-cap` is the one figure in the markup, and it only disables a button
    # early. The server caps again, and the preview re-reads before that.
    html = R._moneybox({"money": [got[("deposit", "")]]})
    assert 'data-cap="50000"' in html
    assert "12400" not in html and "40000" not in html


def test_every_action_maps_to_a_route_that_exists():
    src = Path(HERE.parent / "banking_web.py").read_text(encoding="utf-8")
    for action, url in LS._MONEY_URL.items():
        assert f'add_post("{url}"' in src, f"{action} points at a route nobody serves"


def test_the_nav_points_at_the_page_that_can_act():
    """`register_section` UPDATES an existing key, so the last writer owns the nav.

    `banking_web` and `messages_web` register first and point at `/banking` and
    `/messages`; `canvas_web` registers last and repoints both at `/hub/*`. That
    is load-bearing ordering, not incidental — reversing the tuple would put the
    nav back on the pages that only read.
    """
    src = Path(HERE.parent / "Restocker_web.py").read_text(encoding="utf-8")
    block = src[src.index('("hub_web",      "register_hub_routes"'):]
    block = block[:block.index("):")]
    order = [line for line in block.splitlines() if '"register_' in line]
    assert "canvas_web" in order[-1], (
        "canvas_web must register last or the nav goes back to the read-only pages")
    for mod in ("banking_web", "messages_web"):
        assert any(mod in line for line in order[:-1])
    import canvas_web as CW
    paths = dict((k, p) for k, _l, p, _o in CW.LIVE_SECTIONS)
    assert paths["banking"] == "/hub/banking"
    assert paths["messages"] == "/hub/messages"
