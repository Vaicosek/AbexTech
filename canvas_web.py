"""canvas_web.py — the design's screens, served.

`abex_canvas` holds the canvas as data, `abex_render` turns one screen into HTML,
and this mounts the set at `/canvas/*` inside the normal shell so the two can be
compared with the mockup side by side without disturbing anything already live.

Why a new prefix rather than replacing a page: the screens still carry the
design's SAMPLE rows. Their shape is right - columns, tone rules, copy - and
their numbers are not yours. Putting sample money on `/hub` would be worse than
an ugly page; it would be a lying one. Each screen moves onto its real route as
it is wired to live data, one at a time.
"""
from __future__ import annotations

try:
    from aiohttp import web
except Exception:                                   # pragma: no cover
    web = None

import abex_shell
import abex_render
from abex_canvas import SCREENS

#: The live-data builders. Guarded because this module must still serve the
#: canvas set in a deployment that has no database - and because a missing
#: import here should cost the LIVE routes, not the whole registration. It was
#: referenced without being imported once, and the section died on a NameError
#: at boot with everything else in it.
try:
    import abex_livescreens
except Exception:                                   # pragma: no cover
    abex_livescreens = None

PREFIX = "/canvas"

#: canvas screen key -> the nav key it should light up.
_NAV = {
    "hub": "hub", "banking": "banking", "stocks": "stocks", "markets": "markets",
    "exchange": "exchange", "orders": "work", "work": "work", "lands": "lands",
    "auctions": "auctions", "messages": "messages", "history": "history",
    "market": "mine", "filing": "mine.report",
}

#: Where each nav key lives INSIDE the canvas set. Without this the sidebar
#: carries the design's own hrefs, which the shell prefixes to `/canvas/hub`,
#: `/canvas/my` and so on - and those are not the routes this module registers.
#: The entries that did happen to match walked you back out to the live pages,
#: so browsing the design set meant retyping a URL for every screen.
#:
#: These are prefix-relative: `render(prefix=PREFIX)` prepends `/canvas`, so the
#: Hub entry is the empty string rather than "/canvas".
#: The canvas screens a signed-out visitor may open at all. Taken from the live
#: side's PUBLIC so the two cannot disagree about what "public" means.
try:
    _PUBLIC_CANVAS = set(abex_livescreens.PUBLIC)
except Exception:                                   # pragma: no cover
    _PUBLIC_CANVAS = {"hub", "markets", "exchange", "work", "lands"}

_PATHS = {
    "hub": "", "banking": "/banking", "exchange": "/exchange",
    "stocks": "/stocks", "markets": "/markets", "work": "/work",
    "orders": "/orders", "auctions": "/auctions", "lands": "/lands",
    "mine": "/market", "mine.report": "/filing", "messages": "/messages",
    "history": "/history",
}

_CSS = """/* The block vocabulary the canvas uses and this theme did not have yet.
   Everything here is built from existing tokens - no new hue, per spec §1. */

/* A block is separated by space and a rule, never by a fill: the Warm Feel skin
   has `surface: transparent` and "panels have no fill, just a top rule when
   accented". */
.block{border-top:1px solid var(--line);margin:0 0 34px;padding:18px 0 0}
.block>h2{font-size:28px;font-weight:400;letter-spacing:normal;color:var(--text);
  margin:0 0 14px}
/* `ac:1` - the lead block. This is the one place a block gets the accent, and it
   is a rule, not a fill. */
.block.lead{border-top:1px solid var(--accent)}

/* Balance block: two columns, no header row. A `tot` row rules off and bolds. */
.balance table{width:100%;border-collapse:collapse}
.balance td{padding:7px 0;vertical-align:baseline;border:0}
.balance .blabel{color:var(--dim)}
.balance .bnote{display:block;color:var(--faint);font-size:.86em}
.balance tr.btot td{border-top:1px solid var(--line);font-weight:700;
  color:var(--text);padding-top:11px}

/* Action block: a sentence and up to a few buttons. Three kinds, no others. */
.actionblock .act{margin:0 0 12px;color:var(--dim)}
.btnrow{display:flex;gap:10px;flex-wrap:wrap}
.btn{font:inherit;font-size:.95em;padding:8px 16px;border-radius:2px;cursor:pointer;
  background:none;border:1px solid var(--line-up);color:var(--text)}
.btn.p{background:var(--accent);border-color:var(--accent);color:#1b1d20;font-weight:700}
.btn.s{border-color:var(--line-up);color:var(--text)}
.btn.d{border-color:var(--loss);color:var(--loss)}
.btn:hover{border-color:var(--accent)}
.btn.p:hover{filter:brightness(1.08)}

/* "Your position" wash. Deliberately weak: it is a flag on a minority of rows,
   and at any strength that reads as a zebra stripe it has stopped being one. */
tr.mine td{background:var(--raised)}

/* Countdown cells tick client-side; this is only their resting shape. */
td.countdown{font-variant-numeric:tabular-nums}

/* The price line. No script and no library — an inline SVG polyline stretched to
   the column, so it costs one element and cannot fail to load. The box is a
   fixed height and a free width: `preserveAspectRatio:none` is what lets the
   same 0-100 viewBox fill a sidebar-narrow column and a wide one. */
.sparkwrap{margin:2px 0 4px}
svg.spark{display:block;width:100%;height:64px}
.skmeta{display:flex;align-items:baseline;gap:12px;margin-top:6px;
  font-size:12px;color:var(--faint);font-variant-numeric:tabular-nums}
.skmeta .skhi{margin-left:auto}
.skmeta .skhi::before{content:"high ";color:var(--faint)}
.skmeta .sklo::before{content:"low ";color:var(--faint)}

/* The sticky-bottom draft bar. Only present on a screen with work in progress. */
.dockbar{position:sticky;bottom:0;display:flex;align-items:baseline;gap:14px;
  padding:12px 0;border-top:1px solid var(--accent);background:var(--ground);
  flex-wrap:wrap}
.dockbar .dt{font-weight:700}
.dockbar .dk{color:var(--faint)}
.dockbar .dv{font-variant-numeric:tabular-nums}
.dockbar .dn{color:var(--faint)}
.dockbar .dspace{flex:1 1 auto}

@media (max-width:900px){
  .block>h2{font-size:22px}
  .dockbar{gap:8px}
}
"""


def _page(key: str, public: bool = False) -> str:
    """One canvas screen. `public` strips the reader-facing parts.

    These rows are the design's sample data, so nothing here is anyone's - but a
    signed-out visitor should still not be shown "You hold" columns, because the
    page would be teaching them a shape the site will not give them.
    """
    screen = SCREENS.get(key)
    if screen is not None and public and abex_livescreens is not None:
        screen = abex_livescreens.depersonalise(screen)
    body = abex_render.screen_html(screen, owner=not public)
    return abex_shell.render(
        _NAV.get(key, key),
        body,
        title=(screen or {}).get("title", "Canvas"),
        extra_css=_CSS,
        dock=abex_render.dock_html(screen or {}),
        prefix=PREFIX,
        paths=_PATHS,
        available=set(_PATHS),
    )


def _handler(key: str):
    async def handle(request):
        # These pages carry the DESIGN's sample rows, so nothing here belongs to
        # anybody - but they were also the only unauthenticated pages on the
        # site, which was an accident rather than a decision anyone made. A
        # signed-out visitor now gets the same treatment as everywhere else: the
        # public screens with their reader-facing columns stripped, and a
        # sign-in for the ones that are personal end to end.
        signed_in = False
        try:
            import hub_web
            signed_in = bool(hub_web.current_user(request))
        except Exception:                            # pragma: no cover
            pass
        if not signed_in and key not in _PUBLIC_CANVAS:
            try:
                import hub_web
                return hub_web._login_required_page(request)
            except Exception:                        # pragma: no cover
                raise web.HTTPFound("/hub/login")
        return web.Response(text=_page(key, public=not signed_in),
                            content_type="text/html", charset="utf-8")
    handle.__name__ = f"canvas_{key}"
    return handle


#: A live screen's route, its nav label, and where it sits in the sidebar order.
#: Mounted under the hub prefix because that is where a signed-in, money-bearing
#: page belongs - `hub_web.page()` supplies the wallet strip and the session
#: check, and duplicating either here would be a second place for them to drift.
LIVE_SECTIONS = [
    ("stocks",   "Stocks",    "/hub/stocks",   30),
    ("exchange", "Exchange",  "/hub/exchange", 25),
    ("work",     "Work",      "/hub/work",     40),
    ("market",   "My market", "/hub/market",   50),
    ("filing",   "Report",    "/hub/filing",   51),
    ("auctions", "Auctions",  "/hub/auctions", 60),   # items
    ("banking",  "Banking",   "/hub/banking",  20),
    ("messages", "Messages",  "/hub/messages", 70),
    ("history",  "History",   "/hub/history",  80),
]


def register_live_routes(app) -> None:
    """Mount the screens that have a live source at /hub/<key>.

    Only screens in `abex_livescreens.BUILDERS` are mounted, and only ever with
    live rows. A screen with no source keeps its canvas page under /canvas rather
    than appearing here with the design's sample money on it - which is the whole
    line this codebase is trying not to cross.

    `lands` and `markets` are absent on purpose: both already have a live page in
    this shell (`estates_web` and `hub_web`), and two routes for one section is
    how a nav ends up pointing at the staler of them.

    Auctions, Banking, Messages and History are the other way round, and the
    reasoning is worth writing down because it looks like the same situation and
    is not. Each of those DOES have an older page, and that page is where you
    ACT - place a bid, borrow, reply, page through every source. The designed
    screen is the read view, and it carries an action block linking straight to
    the tool. So the nav is consistent everywhere, and the old page stops being
    the thing you land on by surprise and becomes the thing you were sent to.
    If that trade is wrong for a section, the fix is one line: point its key in
    `vt_web_shell._NAV_PATHS` back at the old path.
    """
    if web is None or abex_livescreens is None:      # pragma: no cover
        return
    try:
        import hub_web
    except Exception:                                # pragma: no cover
        return

    mounted = []
    for key, label, path, order in LIVE_SECTIONS:
        if key not in abex_livescreens.BUILDERS:
            continue

        def _make(k):
            async def handle(request):
                user = hub_web.current_user(request)
                if user:
                    snap = hub_web.money_snapshot(user["user_id"])
                    screen = abex_livescreens.screen(k, str(user["user_id"]))
                else:
                    # Public read. `screen(public=True)` is passed no user id, so
                    # nothing is looked up against an account, and then strips
                    # the reader-facing columns. It returns None for a screen
                    # that is personal end to end - the only case that still
                    # asks a stranger to sign in.
                    screen = abex_livescreens.screen(k, public=True)
                    if screen is None:
                        return hub_web._login_required_page(request)
                    snap = None
                body = abex_render.screen_html(screen, owner=bool(user))
                title = f'{screen.get("title", k.title())} · Abex Tech'
                return hub_web._html(hub_web.page(title, k, user, snap, body))
            handle.__name__ = f"live_{k}"
            return handle

        app.router.add_get(path, _make(key))
        try:
            hub_web.register_section(key, label, path, order=order)
        except Exception as exc:                     # pragma: no cover
            print(f"     live {key}: not in the nav ({exc})")
        mounted.append(key)
    if mounted:
        print(f"     Live canvas screens: {', '.join(mounted)}")


async def _orders_moved(request):
    """`/hub/orders` used to be its own page. Orders is a section of Work now —
    same table, two sides of it — so the old path lands on the page that holds
    it rather than 404ing a link somebody has bookmarked."""
    raise web.HTTPFound("/hub/work")


def register_canvas_routes(app) -> None:
    if web is None:                                 # pragma: no cover
        return
    app.router.add_get("/hub/orders", _orders_moved)
    for key in SCREENS:
        path = PREFIX if key == "hub" else f"{PREFIX}/{key}"
        app.router.add_get(path, _handler(key))
    print(f"     Canvas screens: {len(SCREENS)} under {PREFIX}")
    register_live_routes(app)
