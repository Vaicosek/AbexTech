"""The trade ticket: what it shows, and what it refuses to carry.

The first block on this site that WRITES, so the assertions are about the ways a
ticket can be wrong that do not look wrong.

NO TICKET WITHOUT BOTH HALVES. It needs a user id and a CSRF token, and it is
built with neither for a signed-out reader — so a public build cannot carry a
token even if the stripping were edited away. A token in a page served to a
stranger is the whole of a CSRF defence handed over.

THE FIGURES SHOWN ARE THE FIGURES SENT. The ticket does not re-quote. It carries
the price the page already printed plus a 5% band, and the engine refuses on
slippage rather than filling at whatever the price became. Before that cap
existed a whale moving the mid 100 -> 120 between quote and execute charged
1.22x the displayed figure.

SELLING IS CAPPED AT WHAT YOU HOLD, in the markup as well as on the server —
not because the markup is a control, but because a button that submits an order
the server will refuse is a button that teaches you it is broken.

A NETWORK ERROR IS UNKNOWN, NOT FAILED. The one thing the client must never say
after a dropped connection is "try again": the trade may have gone through, and
retrying is how somebody ends up holding twice what he bought.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_livescreens as LS  # noqa: E402
import abex_render as R        # noqa: E402
import canvas_web              # noqa: E402

OWNER = "1203738126850461738"
LISTED = "greyhames"
PRIVATE = "brew"
TOKEN = "csrf-token-for-the-test"


def _ticket_block(screen):
    for b in screen.get("blocks") or []:
        if "ticket" in b:
            return b
    return None


def test_a_signed_in_reader_gets_a_ticket_on_a_listed_market():
    blk = _ticket_block(LS.stock(OWNER, LISTED, csrf=TOKEN))
    assert blk is not None
    assert blk["ticket"]["market_id"] == LISTED
    assert blk["ticket"]["price"] > 0


def test_no_token_means_no_ticket():
    assert _ticket_block(LS.stock(OWNER, LISTED)) is None


def test_a_signed_out_reader_gets_no_ticket_even_if_a_token_is_passed():
    screen = LS.stock("", LISTED, csrf="SHOULD-NOT-APPEAR")
    assert _ticket_block(screen) is None
    assert "SHOULD-NOT-APPEAR" not in R.screen_html(screen, owner=False)


def test_a_private_market_has_no_ticket():
    """Not listed means not traded."""
    assert _ticket_block(LS.stock(OWNER, PRIVATE, csrf=TOKEN)) is None


def test_the_ticket_carries_the_price_the_page_printed():
    screen = LS.stock(OWNER, LISTED, csrf=TOKEN)
    blk = _ticket_block(screen)
    band = dict((t[0], t[1]) for t in screen["band"])
    shown = float(band["Share price"].rstrip("c").replace(",", ""))
    assert abs(blk["ticket"]["price"] - shown) < 0.005, (blk["ticket"]["price"], shown)


def test_sell_is_disabled_when_you_hold_nothing():
    html = R._ticket({"ticket": {"market_id": "m", "price": 10.0, "you_hold": 0,
                                 "csrf": TOKEN}})
    assert "tksell" in html
    sell = html.split("tksell")[1].split(">")[0]
    assert "disabled" in sell, html


def test_sell_is_enabled_when_you_do():
    html = R._ticket({"ticket": {"market_id": "m", "price": 10.0, "you_hold": 5,
                                 "csrf": TOKEN}})
    sell = html.split("tksell")[1].split(">")[0]
    assert "disabled" not in sell, html


def test_the_client_sends_the_quote_and_a_slippage_band():
    js = canvas_web.CANVAS_JS
    assert "quote_price" in js
    assert "max_total" in js and "min_total" in js
    assert "0.05" in js, "no band means no slippage cap"


def test_the_client_sends_csrf_and_a_stable_request_id():
    js = canvas_web.CANVAS_JS
    assert "X-CSRF-Token" in js
    assert "request_id" in js
    assert "keys[intent]" in js, "the id must be stable across retries of ONE order"


def test_an_undecided_outcome_keeps_the_key_and_a_decided_one_retires_it():
    js = canvas_web.CANVAS_JS
    assert "outcome_unknown" in js
    assert "idempotency_in_progress" in js
    assert "delete keys[intent]" in js


def test_a_network_error_never_tells_him_to_retry():
    js = canvas_web.CANVAS_JS
    # The trade's own catch, not the chart's — the chart may fail freely.
    send = js.split("var send = function(side)")[1].split("if(buy) buy.add")[0]
    catch = send.split(".catch(")[1]
    assert "do not re-send" in catch, catch[:300]
    # "check your holdings before trying again" is the correct advice; a bare
    # "try again" is the dangerous one.
    assert "Reload and check" in catch, catch[:300]


def test_the_confirmation_names_the_figures():
    """He confirms numbers, not intentions."""
    js = canvas_web.CANVAS_JS
    assert "window.confirm" in js
    ask = js.split("window.confirm")[1][:400]
    assert "toFixed(2)" in ask and "total" in ask


# ── the trading page ───────────────────────────────────────────────────────

def test_the_trading_page_gives_every_listed_market_a_ticket():
    screen = LS.stocks(OWNER, csrf=TOKEN)
    tickets = [b for b in screen["blocks"] if "ticket" in b]
    charts = [b for b in screen["blocks"] if "spark" in b]
    assert len(tickets) == 2, "two markets are listed"
    assert len(charts) == 2, "each one carries its own line"


def test_the_trading_page_refuses_a_ticket_without_a_token():
    screen = LS.stocks(OWNER)
    assert not [b for b in screen["blocks"] if "ticket" in b]


def test_the_trading_page_is_never_public():
    assert LS.screen("stocks", "anyone", public=True) is None


def test_a_public_build_cannot_be_handed_a_token():
    """The screen dispatcher passes the token only on a signed-in build."""
    assert LS.screen("stocks", public=True, csrf="SHOULD-NOT-APPEAR") is None


def test_the_price_is_live_and_the_ticket_follows_it():
    screen = LS.stocks(OWNER, csrf=TOKEN)
    html = R.screen_html(screen, owner=True)
    assert "sknow" in html, "no live price above the line"
    assert 'data-mid=' in html
    import canvas_web
    js = canvas_web.CANVAS_JS
    assert "__repice" in js, "the ticket would keep quoting the served price"
    assert "wireTicket" in js, "only the first ticket on the page would work"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("trade ticket: ok")
