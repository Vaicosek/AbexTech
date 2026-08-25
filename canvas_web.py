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

PREFIX = "/canvas"

#: canvas screen key -> the nav key it should light up.
_NAV = {
    "hub": "hub", "banking": "banking", "stocks": "stocks", "markets": "markets",
    "exchange": "exchange", "orders": "work", "work": "work", "lands": "lands",
    "auctions": "auctions", "messages": "messages", "history": "history",
    "market": "mine", "filing": "mine.report",
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


def _page(key: str) -> str:
    screen = SCREENS.get(key)
    body = abex_render.screen_html(screen, owner=True)
    return abex_shell.render(
        _NAV.get(key, key),
        body,
        title=(screen or {}).get("title", "Canvas"),
        extra_css=_CSS,
        dock=abex_render.dock_html(screen or {}),
        prefix=PREFIX,
    )


def _handler(key: str):
    async def handle(request):
        return web.Response(text=_page(key), content_type="text/html",
                            charset="utf-8")
    handle.__name__ = f"canvas_{key}"
    return handle


def register_canvas_routes(app) -> None:
    if web is None:                                 # pragma: no cover
        return
    for key in SCREENS:
        path = PREFIX if key == "hub" else f"{PREFIX}/{key}"
        app.router.add_get(path, _handler(key))
    print(f"     Canvas screens: {len(SCREENS)} under {PREFIX}")
