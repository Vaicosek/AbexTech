"""
abex_web.py — mounts the twelve Abex screens.

They existed in the repo and nothing served them: `abex_screens.py` and
`abex_hub.py` render, `abex_shell.py` wraps, and no route pointed at any of it,
so every page a player actually saw was still the old set. This module is the
missing wiring.

## Why /abex and not the real paths

The screens carry the design's sample rows, not live queries. The live pages own
`/banking`, `/lands`, `/messages`, `/history`, `/exchange` and `/markets` today,
and aiohttp raises on a duplicate route, so serving these at the canonical paths
means *removing* a working money page in the same commit. That is a cutover, not
a mount.

So the whole set lives under `/abex/*`, nav included — `abex_shell.render` takes
a `prefix` for exactly this. Promoting a screen is then one screen's worth of
work: wire its rows to real queries, drop the old handler, register this one at
the canonical path. Nothing has to move as a block.

Every page says, in one line, that its figures are the design's. A preview that
looks live is worse than no preview: these numbers are shaped like the real ones
and a player reading them as their own balance would be right to be angry.

## Identity

Same session as the rest of the site (`vt_web_shell.require_page_session`), so a
logged-out visitor gets the same sign-in card and the staff group renders
server-side only for staff — a normal player never receives the markup.
"""
from __future__ import annotations

import logging

try:
    from aiohttp import web
except Exception:  # pragma: no cover - the module is import-safe without aiohttp
    web = None  # type: ignore

import abex_hub
import abex_live
import abex_screens as screens
import abex_data as data
import abex_shell
import vt_web_shell as shell

log = logging.getLogger("abex_web")

ABEX_VERSION = "1.0"

#: Everything here hangs off one prefix. Change it in one place, or drop it for a
#: screen that has been promoted to its canonical path.
PREFIX = "/abex"

#: The line every preview page opens with. One sentence, no box, no icon.
SAMPLE_NOTE = (
    '<p class="empty">Figures on this screen are the design\'s sample data, '
    'not your account. Live data lands screen by screen.</p>')


def _sample(fn):
    """A screen still on the design's rows: say so, once, at the top."""
    return lambda: SAMPLE_NOTE + fn()


def _markets() -> str:
    """Markets, from the live registry.

    Falls back to the design's rows only when the bot's modules are not importable
    — an empty table would read as "no markets", which is a different and wrong
    statement.
    """
    rows = abex_live.markets()
    if rows is None:
        return SAMPLE_NOTE + screens.markets()
    return screens.markets(rows=rows, last_col="Last report")


def _stocks(user_id: str) -> str:
    """Positions, live. A holder with nothing owns nothing — say that in one line
    rather than rendering an empty table under a full set of headers."""
    live = abex_live.stocks(user_id)
    if live is None:
        return SAMPLE_NOTE + screens.stocks()
    if not live["rows"]:
        return ('<div class="pagehead"><div><h1>Stocks</h1>'
                '<div class="sub">What you own, and what the next report will '
                'settle it at.</div></div></div>'
                '<p class="empty">You hold no shares.</p>')
    plural = "position" if len(live["rows"]) == 1 else "positions"
    # A column where every cell says "none declared" is a column of noise. It comes
    # back the moment a market declares one.
    any_dividend = any(row[9] != "none declared" for row in live["rows"])
    return screens.stocks(
        show_dividend=any_dividend,
        holdings=live["rows"], formula=live["formula"],
        market=live["market"] or "your largest holding",
        last_col="Last priced",
        note=f'{len(live["rows"])} {plural}. Prices settle when each market files.')


def _hub(user_id: str) -> str:
    live = abex_live.hub(user_id)
    if live is None:
        return SAMPLE_NOTE + abex_hub.body(tiles=data.HUB_TILES, markets=data.MARKETS,
                                           work=data.WORK)
    return abex_hub.body(**live)


def _investor(user_id: str) -> str:
    live = abex_live.investor(user_id)
    if live is None:
        return SAMPLE_NOTE + screens.investor()
    if not live["is_investor"]:
        return ('<div class="pagehead"><div><h1>Investor</h1><div class="sub">'
                'GEX.PR preferred. A separate class from common shares.</div></div></div>'
                '<p class="empty">You hold no preferred shares.</p>')
    return screens.investor(rows_data=live["rows"], tiles=live["tiles"],
                            pool_pct=live["pool_pct"])


def _exchange() -> str:
    live = abex_live.exchange()
    if live is None:
        return SAMPLE_NOTE + screens.exchange()
    if not live["rows"]:
        return ('<div class="pagehead"><div><h1>Exchange</h1>'
                '<div class="sub">The share side.</div></div></div>'
                '<p class="empty">No market is listed yet.</p>')
    return screens.exchange(listings=live["rows"], tiles=live["tiles"])


def _filings() -> str:
    rows = abex_live.filings()
    if rows is None:
        return SAMPLE_NOTE + screens.filings()
    if not rows:
        return ('<div class="pagehead"><div><h1>Earnings reports</h1>'
                '<div class="sub">Every filing across the exchange.</div></div></div>'
                '<p class="empty">Nothing has been filed yet.</p>')
    return screens.filings(
        rows_data=rows,
        note=f"The {len(rows)} most recent filings, newest first.")


def _orders() -> str:
    rows = abex_live.orders()
    if rows is None:
        return SAMPLE_NOTE + screens.work()
    if not rows:
        return ('<div class="pagehead"><div><h1>Orders</h1><div class="sub">'
                'Claim a production order, deliver it, get paid.</div></div></div>'
                '<p class="empty">No orders are open.</p>')
    plural = "order" if len(rows) == 1 else "orders"
    return screens.work(rows_data=rows,
                        note=f"{len(rows)} open {plural} across all markets.")


def _lands() -> str:
    rows = abex_live.parcels()
    if rows is None:
        return SAMPLE_NOTE + screens.lands()
    if not rows:
        return ('<div class="pagehead"><div><h1>Lands</h1><div class="sub">'
                'Parcels for sale, and what they went for.</div></div></div>'
                '<p class="empty">No parcels are listed.</p>')
    return screens.lands(rows_data=rows,
                         note="Land is bought outright — there is no rent.")


#: (route, nav key, page title, body builder). The nav key decides which item is
#: marked current and which section hue the page takes.
SCREENS: list[tuple[str, str, str, object]] = [
    # None means "this screen needs to know who is asking" — see `_handler`.
    ("",                 "",                 "Hub",              None),
    ("/markets",         "markets",          "Markets",          _markets),
    ("/exchange",        "exchange",         "Exchange",         _exchange),
    ("/exchange/reports", "exchange.reports", "Earnings reports", _filings),
    ("/stocks",          "stocks",           "Stocks",           None),
    ("/orders",          "orders",           "Orders",           _orders),
    ("/lands",           "lands",            "Lands",            _lands),
    ("/investor",        "investor",         "Investor",         None),
]

#: Only what this module serves. The tree also lists Auctions, My market, Profile,
#: Messages and History; under this prefix those have no handler, and a nav entry
#: that 404s is worse than an absent one.
AVAILABLE = {key.split(".")[0] for _path, key, _title, _fn in SCREENS if key}


def _who(sess) -> tuple[str, str]:
    """Name and role for the header. Real name, never the Discord id."""
    name = str((sess or {}).get("name") or "").strip() or "Signed in"
    role = "owner of GreyHames" if (sess or {}).get("staff") else "investor"
    return name, role


def _render(request, key: str, title: str, body_html: str):
    sess, refusal = shell.require_page_session(request)
    if refusal is not None:
        return refusal
    ctx = shell.page_ctx()
    doc = abex_shell.render(
        key,
        body_html,
        title=title,
        who=_who(sess),
        staff=bool(ctx.get("staff")),
        extra_css=shell._LEGACY_CSS,
        # The live money strip, so the header on these screens is the same header
        # and the same figures as everywhere else on the site. It is the one part
        # of a preview page that is real.
        header=shell._STRIP_HTML,
        tail=shell.page_scripts(),
        available=AVAILABLE,
        prefix=PREFIX,
        counts=abex_live.nav_counts(),
    )
    return web.Response(text=doc, content_type="text/html", charset="utf-8")


def _handler(key: str, title: str, fn):
    async def handle(request):
        if fn is None:                      # a screen that needs to know who is asking
            sess, refusal = shell.require_page_session(request)
            if refusal is not None:
                return refusal
            builder = {"": _hub, "stocks": _stocks, "investor": _investor}[key]
            return _render(request, key, title, builder(str(sess["user_id"])))
        return _render(request, key, title, fn())
    handle.__name__ = f"abex_{(key or 'hub').replace('.', '_')}"
    return handle


#: Paths this module used to serve with the design's SAMPLE money, now sent to
#: the live page instead. `/abex/banking` showed 84,230c available and 156,900c
#: in savings to whoever signed in — the design's figures, on a route anybody
#: could reach, on the one subject where a wrong number reads as your money.
#: Banking went live at /hub/banking, so these were duplicates AND fakes.
#:
#: Redirects rather than deletions: they were linked from the nav for weeks.
RETIRED = {
    "/banking":       "/hub/banking",
    "/banking/loans": "/hub/banking",
    "/banking/bonds": "/hub/banking",
}


def _retired(target: str):
    async def handle(request):
        raise web.HTTPFound(target)
    handle.__name__ = f"abex_retired_{target.strip('/').replace('/', '_')}"
    return handle


def register_abex_routes(app) -> None:
    """Attach the Abex screens. Same shape as every other section module."""
    if web is None:  # pragma: no cover
        log.warning("[abex] aiohttp unavailable — screens not registered.")
        return
    shell.register_shell_routes(app)
    for path, key, title, fn in SCREENS:
        app.router.add_get(f"{PREFIX}{path}" or PREFIX, _handler(key, title, fn))
    for path, target in RETIRED.items():
        app.router.add_get(f"{PREFIX}{path}", _retired(target))
    # The hub link in the sidebar's brand block points at the prefix root.
    log.info("[abex] v%s registered — %d screens under %s",
             ABEX_VERSION, len(SCREENS), PREFIX)
