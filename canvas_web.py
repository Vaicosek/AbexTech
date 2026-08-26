"""canvas_web.py — the live site's designed screens, and the API behind them.

ONE SITE. This module used to mount two sets of pages: the design's screens with
the design's SAMPLE money under `/canvas/*`, and the same screens on live data
under `/hub/*`. The sample set existed so a screen could be looked at before it
was wired. Every screen is wired now, so it is gone — `/canvas/*` redirects to
the live page it was a picture of.

Keeping it would have been the same mistake as `/abex/banking`, which showed
everybody the same invented 84,230c balance: a second set of pages answering
"what do I own" with figures nobody has.

What it serves:

  * `/hub/<screen>` — the designed screens on live rows, through `hub_web.page`
    so the shell, the nav and the money strip are the site's own.
  * `/hub/stocks/<market>` — one market's page.
  * `/api/series/*` — the points behind a chart, public because an index and a
    share price are public facts about this economy.

`abex_canvas.py` stays and is NOT a set of pages. It is the design itself —
column headings, screen titles, block order — which `abex_livescreens` reads so
a live screen keeps the shape the design gave it. Nothing serves its rows.
"""
from __future__ import annotations

try:
    from aiohttp import web
except Exception:                                   # pragma: no cover
    web = None

import abex_shell
import abex_render

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

#: The same stylesheet under a public name. `hub_web` imports `CANVAS_CSS` and
#: falls back to "" when the import fails — and it has been failing silently
#: since the day it was written, because the only name here was the private
#: `_CSS`. Every designed screen served through the hub (Hub, Markets, Stocks,
#: Work, Exchange, My market, the report) has been rendering WITHOUT the block
#: vocabulary: balance rows, buttons and the accent lead-rule unstyled. A
#: `try/except ImportError` that returns a working-looking default is exactly
#: how a bug like this survives — nothing errors, the page just looks wrong.
_CSS = """/* The block vocabulary the canvas uses and this theme did not have yet.
   Everything here is built from existing tokens - no new hue, per spec §1. */

/* A block is separated by space and a rule, never by a fill: the Warm Feel skin
   has `surface: transparent` and "panels have no fill, just a top rule when
   accented". */
.block{border-top:1px solid var(--line);margin:0 0 34px;padding:18px 0 0}
.block>h2{font-size:22px;font-weight:400;letter-spacing:normal;color:var(--text);
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

/* The trade ticket. Plain controls on the page's own type — a ticket that looks
   like a separate app is a ticket a trader reads separately from the figures
   above it. */
.ticket,.bidbox,.moneybox,.replybox{margin:2px 0 4px}
.ticket .tkrow,.bidbox .tkrow,.moneybox .tkrow,.replybox .tkrow{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ticket .tklab,.bidbox .tklab,.moneybox .tklab,.replybox .tklab{color:var(--faint);font-size:11.5px}
.ticket .tkq,.bidbox .tkq,.moneybox .tkq{width:120px;padding:8px 10px;background:none;color:var(--text);
  border:1px solid var(--line);border-radius:2px;font:inherit;
  font-variant-numeric:tabular-nums}
.ticket .tkq:focus,.bidbox .tkq:focus,.moneybox .tkq:focus{outline:none;border-color:var(--accent)}
.ticket .tkest{margin-top:9px;font-variant-numeric:tabular-nums;font-size:14px}
.replybox+.replybox{margin-top:12px;padding-top:12px;border-top:1px solid var(--line)}
.replybox .rpbody{display:block;width:100%;box-sizing:border-box;margin:6px 0 8px;
  padding:8px 10px;background:none;color:var(--text);border:1px solid var(--line);
  border-radius:2px;font:inherit;font-size:13px;resize:vertical}
.replybox .rpbody:focus{outline:none;border-color:var(--accent)}
.replybox .rpcount{color:var(--faint);font-size:10.5px;margin-left:auto}
.moneybox+.moneybox{margin-top:12px;padding-top:12px;border-top:1px solid var(--line)}
.moneybox.stuck .tkhint{color:var(--loss)}
.ticket .tkhint,.bidbox .tkhint,.moneybox .tkhint,.replybox .tkhint{margin-top:6px;color:var(--faint);font-size:10.5px}
.ticket button[disabled]{opacity:.45;cursor:not-allowed}

/* §5: `dense` toggles row padding and NOTHING else - "does not change font
   size". The theme's own rows are 10px; dense is 7px. */
table.dense td, table.dense th{padding-top:7px;padding-bottom:7px}

/* §2: the measured header height, set by the page script. The fallback matters —
   without a script the jump still needs to clear a sticky header, and 96px is
   nearer right than 0. */
.block{scroll-margin-top:var(--headh, 96px)}

/* The price line. No script and no library — an inline SVG polyline stretched to
   the column, so it costs one element and cannot fail to load. The box is a
   fixed height and a free width: `preserveAspectRatio:none` is what lets the
   same 0-100 viewBox fill a sidebar-narrow column and a wide one. */
.sparkwrap{margin:2px 0 4px}
svg.spark{display:block;width:100%;height:64px}
.skmeta{display:flex;align-items:baseline;gap:12px;margin-top:6px;
  font-size:10px;color:var(--faint);font-variant-numeric:tabular-nums}
.skmeta .skhi{margin-left:auto}
.skmeta .skhi::before{content:"high ";color:var(--faint)}
.skmeta .sklo::before{content:"low ";color:var(--faint)}

/* Timeframes. Text with an underline when current — the nav's own grammar, not
   a row of pills. */
.sknow{display:flex;align-items:baseline;gap:9px;margin-bottom:6px}
.sknow .sknowv{font-size:21px;font-variant-numeric:tabular-nums}
.sknow .sknowl{color:var(--faint);font-size:12.5px}
.sktf{display:flex;gap:18px;margin-bottom:8px}
.sktf button{background:none;border:none;padding:2px 0 3px;cursor:pointer;
  color:var(--faint);font:inherit;font-size:12.5px;border-bottom:2px solid transparent}
.sktf button.on{color:var(--text);border-bottom-color:var(--accent)}
.sktf button:hover{color:var(--text)}

/* The crosshair readout. Reserved on load so the first hover does not shift the
   page. */
.skread{display:flex;gap:14px;align-items:baseline;margin-top:8px;min-height:24px;
  font-size:12.5px;font-variant-numeric:tabular-nums}
.skread .skwhen{color:var(--faint)}
.skread .skprice{font-size:15px}
.skread .skwhy{color:var(--faint)}
.sklegend{display:flex;gap:20px;align-items:baseline;margin-top:6px;font-size:12.5px;
  flex-wrap:wrap}
.sklegend i{display:inline-block;width:9px;height:9px;border-radius:50%;
  margin-right:7px}
.sklegend .skdim{color:var(--faint)}
svg.spark{cursor:crosshair}

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
  .block>h2{font-size:18px}
  .dockbar{gap:8px}
}
"""

CANVAS_CSS = _CSS



#: Where each retired `/canvas/*` page goes. There is one site.
_MOVED = {
    "hub": "/hub", "markets": "/hub/markets", "stocks": "/hub/stocks",
    "exchange": "/hub/exchange", "work": "/hub/work", "orders": "/hub/work",
    "market": "/hub/market", "filing": "/hub/filing", "banking": "/hub/banking",
    "auctions": "/hub/auctions", "lands": "/hub/lands",
    "messages": "/hub/messages", "history": "/hub/history",
}


def _moved(target: str):
    async def handle(request):
        raise web.HTTPFound(target)
    handle.__name__ = "canvas_moved_" + target.strip("/").replace("/", "_")
    return handle


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
                    screen = abex_livescreens.screen(
                        k, str(user["user_id"]),
                        csrf=str(user.get("csrf") or ""))
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
                return hub_web._html(hub_web.page(title, k, user, snap, body,
                                                  screen=screen))
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


#: The chart script. No library, no build step, and it redraws the polyline the
#: server already drew rather than replacing it — so the chart is right before
#: this runs and stays right if it never does.
#:
#: The geometry is deliberately the same arithmetic as `abex_render._spark`.
#: Two implementations of one projection drift, and here a drift means the line
#: and the caption under it stop describing the same series.
CANVAS_JS = r"""
(function(){
  /* §2: every block's scroll-margin-top is the MEASURED header height, via a
     ResizeObserver rather than a guessed constant. The header is sticky and its
     height changes with the viewport - it wraps its figures on a narrow screen -
     so a constant is right at one width and wrong at every other, and wrong here
     means an anchor jump lands the heading UNDERNEATH the header. */
  /* §2's mobile nav: the toggle expands the tree INLINE, no drawer, no overlay.
     Wired here rather than with an inline handler so the markup stays free of
     script, and it is harmless on desktop where the button is display:none and
     the tree is always shown. */
  var tog = document.querySelector(".navtoggle");
  var tree = document.getElementById("navtree");
  if(tog && tree){
    tog.addEventListener("click", function(){
      var open = tree.classList.toggle("open");
      tog.setAttribute("aria-expanded", open ? "true" : "false");
    });
    /* Following a link inside the tree collapses it, so the next page does not
       open with the nav already covering its first figures. */
    tree.addEventListener("click", function(e){
      if(e.target.closest("a")){
        tree.classList.remove("open");
        tog.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* §3: "Only the active item's children/subs render - clicking the active item
     again collapses it instead of navigating." Following the link you are
     already on is a page reload that changes nothing, so it reads as a dead
     click; collapsing is at least an answer. */
  var active = document.querySelector('.navitem[aria-current="page"]');
  if(active){
    var group = active.parentNode;
    var kids = [];
    var n = active.nextElementSibling;
    while(n && n.classList.contains("navsub")){ kids.push(n); n = n.nextElementSibling; }
    if(kids.length){
      active.addEventListener("click", function(e){
        e.preventDefault();
        for(var i = 0; i < kids.length; i++){
          kids[i].style.display = kids[i].style.display === "none" ? "" : "none";
        }
      });
    }
  }

  /* The trade ticket. Every check that matters is the server's — this only
     shows the figures being confirmed and carries them over unchanged. */
  var tickets = document.querySelectorAll(".ticket");
  for(var ti = 0; ti < tickets.length; ti++) wireTicket(tickets[ti]);

  function wireTicket(tk){
    if(!tk) return;
    var q = tk.querySelector(".tkq");
    var est = tk.querySelector(".tkest");
    var hint = tk.querySelector(".tkhint");
    var buy = tk.querySelector(".tkbuy");
    var sell = tk.querySelector(".tksell");
    var price = parseFloat(tk.getAttribute("data-price")) || 0;
    var held = parseFloat(tk.getAttribute("data-held")) || 0;
    var mid = tk.getAttribute("data-mid");
    var csrf = tk.getAttribute("data-csrf");
    var keys = {};                    /* intent -> request_id, see below */
    var money = function(n){
      return n.toLocaleString(undefined, {minimumFractionDigits:0,
                                          maximumFractionDigits:0}) + "c";
    };
    var shares = function(){
      var n = parseInt(q.value, 10);
      return (isNaN(n) || n < 1) ? 0 : n;
    };
    var draw = function(){
      var n = shares();
      est.textContent = n ? (n.toLocaleString() + " x " + price.toFixed(2) +
                             "c = " + money(price * n)) : "";
      if(sell) sell.disabled = !(held > 0 && n > 0 && n <= held);
      if(buy) buy.disabled = !n;
    };
    q.addEventListener("input", draw);
    draw();

    var rid = function(intent){
      if(!keys[intent]){
        /* Stable across retries of ONE order and different for the next: the
           server replays a completed order under the same key rather than
           trading twice, which is what makes a double-click safe. */
        keys[intent] = "web-" + intent + "-" +
          (Date.now().toString(36)) + Math.random().toString(36).slice(2, 8);
      }
      return keys[intent];
    };

    var send = function(side){
      var n = shares();
      if(!n) return;
      var total = Math.round(price * n);
      var band = Math.ceil(total * 0.05);
      /* He confirms FIGURES, not intentions — the numbers are in the question. */
      if(!window.confirm(
        (side === "buy" ? "Buy " : "Sell ") + n.toLocaleString() +
        " share" + (n === 1 ? "" : "s") + " at about " + price.toFixed(2) +
        "c each — " + money(total) + " total.\n\nThe price may move; the order " +
        "is refused rather than filled if it moves more than 5%.")) return;

      var intent = side + ":" + mid + ":" + n;
      var body = {action: side, market_id: mid, shares: n, quote_price: price,
                  request_id: rid(intent)};
      if(side === "buy") body.max_total = total + band;
      else body.min_total = Math.max(0, total - band);

      buy.disabled = true; if(sell) sell.disabled = true;
      hint.textContent = "Working…";
      fetch("/api/trade", {method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf || ""},
        body: JSON.stringify(body)})
        .then(function(r){ return r.json(); })
        .then(function(j){
          hint.textContent = (j && (j.message || j.error)) || "Done.";
          /* Keep the key ONLY while the outcome is unknown. Anything decided —
             filled or refused — retires it, so a corrected order is a new one
             and a repeat of a settled one is not silently replayed forever. */
          var undecided = j && (j.code === "outcome_unknown" ||
                                j.code === "idempotency_in_progress" ||
                                j.code === "idempotency_unresolved");
          if(!undecided) delete keys[intent];
          if(j && j.ok) setTimeout(function(){ location.reload(); }, 900);
          else draw();
        })
        .catch(function(){
          /* A network error is UNKNOWN, not failed: the trade may have gone
             through. Telling him to retry here is how somebody ends up holding
             twice what he bought. */
          hint.textContent = "Network error — do not re-send. Reload and check " +
            "your holdings before trying again.";
        });
    };
    if(buy) buy.addEventListener("click", function(){ send("buy"); });
    if(sell) sell.addEventListener("click", function(){ send("sell"); });

    /* Called when the chart refreshes: requote at the new price so the figure
       being confirmed is the figure on screen. */
    tk.__repice = function(next){ price = next; draw(); };
  }

  /* Bidding, on the designed pages. Preview then confirm, with the figures in
     the question — a bid is a hold and the preview proves it as arithmetic. */
  var bids = document.querySelectorAll(".bidbox");
  for(var bi = 0; bi < bids.length; bi++) wireBid(bids[bi]);

  function wireBid(box){
    var q = box.querySelector(".tkq");
    var go = box.querySelector(".bidgo");
    var hint = box.querySelector(".tkhint");
    if(!q || !go) return;
    var lot = parseInt(box.getAttribute("data-lot"), 10);
    var min = parseInt(box.getAttribute("data-min"), 10) || 1;
    var key = box.getAttribute("data-key") || "";
    var csrf = box.getAttribute("data-csrf") || "";
    var title = box.getAttribute("data-title") || ("lot #" + lot);
    var post = function(path, body){
      return fetch(path, {method:"POST", credentials:"same-origin",
        headers:{"Content-Type":"application/json", "X-CSRF-Token":csrf},
        body: JSON.stringify(body)}).then(function(r){ return r.json(); });
    };
    go.addEventListener("click", function(){
      var amount = parseInt(q.value, 10);
      if(isNaN(amount) || amount < min){
        hint.textContent = "The next bid on this lot is " +
          min.toLocaleString() + "c or more.";
        return;
      }
      go.disabled = true; hint.textContent = "Checking…";
      post("/api/estates/bid/preview", {lot_id: lot, amount: amount})
        .then(function(p){
          if(!p || !p.ok){
            hint.textContent = (p && p.error) || "That bid was refused.";
            go.disabled = false; return;
          }
          var lines = (p.rows || []).map(function(r){ return r[0] + ": " + r[1]; });
          if(!window.confirm("Bid " + amount.toLocaleString() + "c on " + title +
              (lines.length ? "\n\n" + lines.join("\n") : "") +
              "\n\nThis places a HOLD, not a payment. The coins stay yours and " +
              "are released the moment somebody outbids you.")){
            hint.textContent = ""; go.disabled = false; return;
          }
          return post("/api/estates/bid",
                      {lot_id: lot, amount: amount, idempotency_key: key})
            .then(function(j){
              if(j && j.replayed){
                hint.textContent = "That was a repeat of a bid already placed — " +
                  "one hold exists, not two.";
              } else {
                hint.textContent = (j && (j.message || j.error)) || "Done.";
              }
              if(j && j.ok) setTimeout(function(){ location.reload(); }, 900);
              else go.disabled = false;
            });
        })
        .catch(function(){
          hint.textContent = "Network error — do not re-send. Reload and check " +
            "the lot before bidding again.";
        });
    });
  }

  /* Banking, on the page that shows the balances. Preview then confirm, the
     same two-step as a bid: the server prices it fresh at the moment of asking
     (a week's interest may have accrued since the page loaded), the player sees
     those figures, and only then does the commit go. The commit carries the key
     minted when the page was BUILT — pressing twice repeats one instruction, it
     does not send two. */
  var moneys = document.querySelectorAll(".moneybox");
  for(var mi = 0; mi < moneys.length; mi++) wireMoney(moneys[mi]);

  function wireMoney(box){
    var go = box.querySelector(".mnygo");
    if(!go) return;                       /* stuck: no button, nothing to wire */
    var q = box.querySelector(".tkq");
    var hint = box.querySelector(".tkhint");
    var action = box.getAttribute("data-action") || "";
    var url = box.getAttribute("data-url") || "";
    var key = box.getAttribute("data-key") || "";
    var csrf = box.getAttribute("data-csrf") || "";
    var title = box.getAttribute("data-title") || action;
    var capA = box.getAttribute("data-cap");
    var cap = capA === null ? null : parseInt(capA, 10);
    var extra = {};
    try { extra = JSON.parse(box.getAttribute("data-extra") || "{}") || {}; }
    catch(e){ extra = {}; }
    var post = function(path, body){
      return fetch(path, {method:"POST", credentials:"same-origin",
        headers:{"Content-Type":"application/json", "X-CSRF-Token":csrf},
        body: JSON.stringify(body)}).then(function(r){ return r.json(); });
    };
    var merge = function(base){
      for(var k in extra){ if(extra.hasOwnProperty(k)) base[k] = extra[k]; }
      return base;
    };
    go.addEventListener("click", function(){
      var amount = 0;
      if(q){
        amount = parseInt(q.value, 10);
        if(isNaN(amount) || amount <= 0){
          hint.textContent = "Enter how many coins."; return;
        }
        if(cap !== null && amount > cap){
          hint.textContent = "Only " + cap.toLocaleString() + "c available for this.";
          return;
        }
      }
      go.disabled = true; hint.textContent = "Checking with the bank…";
      post("/api/banking/preview", merge({action: action, amount: amount}))
        .then(function(p){
          if(!p || !p.ok){
            hint.textContent = (p && p.error) || "The bank could not price that.";
            go.disabled = false; return;
          }
          var lines = (p.rows || []).map(function(r){ return r[0] + ": " + r[1]; });
          if(p.total) lines.push(p.total[0] + ": " + p.total[1]);
          (p.effect || []).forEach(function(r){ lines.push(r[0] + ": " + r[1]); });
          if(p.blocked){
            /* The preview says it cannot be done. That is shown INSTEAD of a
               confirm, never behind one — with the figures that make it true,
               because "blocked" on its own is not a reason. */
            hint.textContent = "The bank will not do that: " +
              (lines.length ? lines.join(" · ") : (p.note || "check the figures above."));
            go.disabled = false; return;
          }
          if(!window.confirm((p.head ? p.head + "\n" : "") + title +
              (lines.length ? "\n\n" + lines.join("\n") : "") +
              (p.note ? "\n\n" + p.note : "") +
              (p.confirm_label ? "\n\n[OK] " + p.confirm_label : ""))){
            hint.textContent = ""; go.disabled = false; return;
          }
          return post(url, merge({amount: amount, idempotency_key: key}))
            .then(function(j){
              if(j && j.replayed){
                hint.textContent = "That was a repeat of an instruction already " +
                  "completed — it was not done a second time.";
              } else {
                hint.textContent = (j && (j.big || j.note || j.error)) || "Done.";
              }
              if(j && j.ok) setTimeout(function(){ location.reload(); }, 900);
              else go.disabled = false;
            });
        })
        .catch(function(){
          /* Unknown, not failed. The instruction may have reached the bank, and
             the key is claimed either way — re-sending can only 409, and telling
             him to try again is how somebody deposits twice. */
          hint.textContent = "Network error — do not re-send. Reload and check " +
            "your balances before trying again.";
        });
    });
  }

  /* Replying, on the page that lists the conversation. No preview step: unlike
     a bid or a deposit there is no arithmetic to confirm — the thing being
     confirmed is the text, and it is on screen in the box. */
  var replies = document.querySelectorAll(".replybox");
  for(var ri = 0; ri < replies.length; ri++) wireReply(replies[ri]);

  function wireReply(box){
    var ta = box.querySelector(".rpbody");
    var go = box.querySelector(".rpgo");
    var rd = box.querySelector(".rdgo");
    var hint = box.querySelector(".tkhint");
    var count = box.querySelector(".rpcount");
    if(!ta) return;
    var tid = box.getAttribute("data-tid") || "";
    var to = box.getAttribute("data-to") || "";
    var key = box.getAttribute("data-key") || "";
    var csrf = box.getAttribute("data-csrf") || "";
    var newest = parseInt(box.getAttribute("data-newest"), 10) || 0;
    var max = parseInt(ta.getAttribute("maxlength"), 10) || 2000;
    var post = function(path, body){
      return fetch(path, {method:"POST", credentials:"same-origin",
        headers:{"Content-Type":"application/json", "X-CSRF-Token":csrf},
        body: JSON.stringify(body)}).then(function(r){ return r.json(); });
    };
    var tick = function(){
      if(count) count.textContent = ta.value.length + " / " + max;
    };
    ta.addEventListener("input", tick); tick();

    if(go) go.addEventListener("click", function(){
      var text = (ta.value || "").trim();
      if(!text){ hint.textContent = "Write something first."; return; }
      go.disabled = true; hint.textContent = "Sending…";
      var body = {body: text, idempotency_key: key};
      if(tid) body.thread_id = tid; else body.to = to;
      post("/api/messages/send", body)
        .then(function(j){
          if(j && j.duplicate){
            hint.textContent = "That confirmation had already posted a message — " +
              "one exists, not two.";
          } else if(j && j.ok){
            ta.value = ""; tick();
            hint.textContent = "Sent.";
            setTimeout(function(){ location.reload(); }, 700);
            return;
          } else {
            hint.textContent = (j && (j.error || j.note)) || "That was not sent.";
          }
          go.disabled = false;
        })
        .catch(function(){
          /* The send may have landed. The key is claimed either way, so pressing
             again can only be refused — which is better than a second message. */
          hint.textContent = "Network error — do not re-send. Reload and check the " +
            "conversation before writing again.";
        });
    });

    if(rd) rd.addEventListener("click", function(){
      rd.disabled = true;
      post("/api/messages/read", {thread_id: tid, up_to: newest})
        .then(function(j){
          if(j && j.ok){ location.reload(); }
          else { hint.textContent = (j && j.error) || "Not marked."; rd.disabled = false; }
        })
        .catch(function(){
          /* Safe to repeat: the watermark write is MAX(old, new). */
          hint.textContent = "Network error — reload and try again.";
          rd.disabled = false;
        });
    });
  }

  var head = document.querySelector(".top");
  if(head){
    var apply = function(){
      document.documentElement.style.setProperty(
        "--headh", (head.getBoundingClientRect().height + 12) + "px");
    };
    apply();
    if(window.ResizeObserver){ new ResizeObserver(apply).observe(head); }
    else { window.addEventListener("resize", apply); }
  }

  /* §5: a countdown cell ticks. `Xh XXm` -> `Xm XXs` -> `Xs` -> `closed`, and
     escalates to loss-bold under five minutes and again under one. A closing
     time rendered once and left to go stale is worse than no clock: a bidder
     reads "4m" on a lot that shut ten minutes ago. */
  var clocks = document.querySelectorAll("td.countdown[data-left]");
  if(clocks.length){
    var started = Date.now();
    var pad = function(n){ return (n < 10 ? "0" : "") + n; };
    var face = function(s){
      if(s <= 0) return "closed";
      if(s >= 3600) return Math.floor(s/3600) + "h " + pad(Math.floor((s%3600)/60)) + "m";
      if(s >= 60)   return Math.floor(s/60) + "m " + pad(s%60) + "s";
      return s + "s";
    };
    var tick = function(){
      var gone = Math.floor((Date.now() - started) / 1000);
      for(var i = 0; i < clocks.length; i++){
        var td = clocks[i];
        var base = parseInt(td.getAttribute("data-left"), 10);
        if(isNaN(base)){ td.textContent = "—"; continue; }
        var left = base - gone;
        td.textContent = face(left);
        td.style.color = left <= 300 ? "var(--loss)" : "";
        td.style.fontWeight = (left <= 60 && left > 0) ? "700" : "";
      }
    };
    tick();
    setInterval(tick, 1000);
  }
  var EVERY = 60000;                 /* the index is written every five minutes */
  function fmt(n, unit){
    return n.toLocaleString(undefined, {minimumFractionDigits:2,
                                        maximumFractionDigits:2}) + (unit||"");
  }
  /* Mirrors `abex_render._FLAT_BAND`. Two implementations of one projection, so
     they are kept identical on purpose and asserted equal in the tests. */
  var FLAT = 0.001;
  function wrapOf(svg){ return svg.parentNode; }
  function draw(svg, d){
    var pts = (d && d.points) || [];
    var line = svg.querySelector("polyline");
    if(pts.length < 2 || !line) return;
    var lo = Math.min.apply(null, pts), hi = Math.max.apply(null, pts);
    var n = pts.length, out = [];
    /* The y-window floor — see the server's comment. Without it a 0.03% move
       fills the box and reads as a crash. */
    var level = (hi + lo) / 2, span = hi - lo;
    var floorSpan = Math.abs(level) * FLAT * 2;
    if(span < floorSpan){
      var pad = (floorSpan - span) / 2;
      lo -= pad; hi += pad; span = floorSpan;
    }
    span = span || 1;
    for(var i = 0; i < n; i++){
      out.push((i * 100 / (n - 1)).toFixed(2) + "," +
               (28 - ((pts[i] - lo) / span) * 26 - 1).toFixed(2));
    }
    var unit = svg.getAttribute("data-unit") || "";
    var first = pts[0], last = pts[n-1], ch = last - first;
    var pctv = first ? (ch / first * 100) : 0;
    var flat = Math.abs(pctv) < FLAT * 100;
    var tone = flat ? "var(--dim)" : (ch > 0 ? "var(--gain)" : "var(--loss)");
    var arrow = flat ? "=" : (ch > 0 ? "▲" : "▼");
    line.setAttribute("points", out.join(" "));
    line.setAttribute("stroke", tone);
    /* Markers are redrawn with the line: a refresh that kept stale dots would
       put a trade at a price that is no longer there. */
    var old = svg.querySelectorAll("circle");
    for(var k = 0; k < old.length; k++) old[k].remove();
    var marks = (d && d.marks) || [];
    var NS = "http://www.w3.org/2000/svg";
    for(var m = 0; m < marks.length; m++){
      var idx = marks[m].i;
      if(!(idx >= 0 && idx < n)) continue;
      var c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", (idx * 100 / (n - 1)).toFixed(2));
      c.setAttribute("cy", (28 - ((pts[idx] - lo) / span) * 26 - 1).toFixed(2));
      c.setAttribute("r", "0.9");
      c.setAttribute("fill", marks[m].kind === "buy" ? "var(--gain)" : "var(--loss)");
      c.setAttribute("vector-effect", "non-scaling-stroke");
      svg.appendChild(c);
    }
    /* Kept for the hover readout, which reads whatever the chart is showing
       NOW rather than what the page was served. */
    svg.__series = d;

    /* The live price, and the ticket that quotes it. Both move with the line —
       a heading saying 999.77c above a chart whose last point is 1,010c is the
       page disagreeing with itself, and the ticket is what somebody confirms. */
    var unitq = svg.getAttribute("data-unit") || "";
    var nowEl = wrapOf(svg).querySelector(".sknow");
    if(nowEl){
      var v = nowEl.querySelector(".sknowv");
      if(v) v.textContent = last.toLocaleString(undefined,
        {minimumFractionDigits:2, maximumFractionDigits:2}) + unitq;
      var mid = nowEl.getAttribute("data-mid");
      if(mid){
        var tks = document.querySelectorAll('.ticket[data-mid="' + mid + '"]');
        for(var q = 0; q < tks.length; q++){
          tks[q].setAttribute("data-price", last.toFixed(4));
          if(tks[q].__repice) tks[q].__repice(last);
        }
      }
    }

    var wrap = svg.parentNode, meta = wrap.querySelector(".skmeta");
    if(meta){
      var pct = pctv;
      var cap = arrow + " " + (ch >= 0 ? "+" : "") + fmt(ch, unit) + " (" +
                (pct >= 0 ? "+" : "") + pct.toFixed(2) + "%) over " +
                (d.window || (n + " readings"));
      meta.innerHTML = '<span style="color:' + tone + '"></span>' +
                       '<span class="skhi"></span><span class="sklo"></span>';
      meta.children[0].textContent = cap;
      meta.children[1].textContent = fmt(hi, unit);
      meta.children[2].textContent = fmt(lo, unit);
      svg.setAttribute("aria-label", cap);
    }
  }
  /* Hover: name the point under the pointer and what moved it. Without the
     "what moved it" half a reader assumes every step is a trade — on this
     exchange most are the model repricing. */
  function readout(svg){
    var wrap = svg.parentNode;
    var row = wrap.querySelector(".skread");
    if(!row) return;
    /* Adopt the served series so the first hover works immediately. */
    if(!svg.__series){
      var blob = wrap.querySelector("script.skdata");
      if(blob){
        try { svg.__series = JSON.parse(blob.textContent); } catch(err){}
      }
    }
    var when = row.querySelector(".skwhen"), price = row.querySelector(".skprice"),
        why = row.querySelector(".skwhy");
    var clear = function(){
      when.innerHTML = "&nbsp;"; price.textContent = ""; why.textContent = "";
    };
    svg.addEventListener("mousemove", function(e){
      var d = svg.__series;
      if(!d || !d.points || d.points.length < 2) return;
      var box = svg.getBoundingClientRect();
      if(!box.width) return;
      var t = (e.clientX - box.left) / box.width;
      var i = Math.round(t * (d.points.length - 1));
      if(i < 0) i = 0;
      if(i > d.points.length - 1) i = d.points.length - 1;
      var unit = svg.getAttribute("data-unit") || "";
      when.textContent = (d.at && d.at[i]) || "";
      price.textContent = d.points[i].toLocaleString(undefined,
        {minimumFractionDigits:2, maximumFractionDigits:2}) + unit;
      why.textContent = (d.why && d.why[i]) ? "· " + d.why[i] : "";
    });
    svg.addEventListener("mouseleave", clear);
  }

  /* Timeframe buttons re-fetch the same endpoint with a different window. */
  function timeframes(svg){
    var wrap = svg.parentNode;
    var bar = wrap.querySelector(".sktf");
    if(!bar) return;
    bar.addEventListener("click", function(e){
      var b = e.target.closest(".sktfb");
      if(!b) return;
      var days = b.getAttribute("data-days");
      var base = (svg.getAttribute("data-src") || "").split("?")[0];
      if(!base) return;
      var all = bar.querySelectorAll(".sktfb");
      for(var i = 0; i < all.length; i++) all[i].classList.remove("on");
      b.classList.add("on");
      svg.setAttribute("data-src", base + "?days=" + days);
      fetch(base + "?days=" + days, {credentials:"same-origin"})
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(j){ if(j && j.ok) draw(svg, j); })
        .catch(function(){ /* leave the range that is drawn */ });
    });
  }

  function tick(){
    /* Nothing is polled while the tab is hidden. A chart nobody is looking at
       does not need to be current, and a background tab quietly hitting the
       server every minute for hours is somebody else's outage. */
    if(document.hidden) return;
    var all = document.querySelectorAll("svg.spark[data-src]");
    for(var i = 0; i < all.length; i++){
      (function(svg){
        fetch(svg.getAttribute("data-src"), {credentials:"same-origin"})
          .then(function(r){ return r.ok ? r.json() : null; })
          .then(function(j){ if(j && j.ok) draw(svg, j); })
          .catch(function(){ /* leave the served line standing */ });
      })(all[i]);
    }
  }
  var sparks = document.querySelectorAll("svg.spark");
  for(var s = 0; s < sparks.length; s++){ readout(sparks[s]); timeframes(sparks[s]); }

  if(document.querySelector("svg.spark[data-src]")){
    setInterval(tick, EVERY);
    document.addEventListener("visibilitychange", function(){
      if(!document.hidden) tick();
    });
  }
})();
"""


async def _stock_page(request):
    """`/hub/stocks/{mid}` — one market's page.

    Public. §6.7: a listed market discloses to EVERYONE, and this page is that
    disclosure — price, months, register shape. It is passed no user id for a
    signed-out reader, so the "your position" block is not built rather than
    built and hidden.
    """
    try:
        import abex_livescreens
        import abex_render
        import hub_web
    except Exception:                                # pragma: no cover
        raise web.HTTPNotFound()
    mid = request.match_info.get("mid") or ""
    user = hub_web.current_user(request)
    uid = str(user["user_id"]) if user else ""
    # The CSRF token is handed to the ticket so it can post. It is only ever
    # given to a signed-in reader's own page — `stock` builds no ticket without
    # both a user id and a token, so a public build cannot carry one.
    screen = abex_livescreens.stock(uid, mid, str(user.get("csrf") or "") if user else "")
    body = abex_render.screen_html(screen, owner=bool(user))
    snap = hub_web.money_snapshot(uid) if user else None
    title = f'{screen.get("title", mid)} · Abex Tech'
    return hub_web._html(hub_web.page(title, "stocks", user, snap, body,
                                      screen=screen))


async def _series(request):
    """Points for one chart, as JSON. Public: an index and a share price are

    public facts about the economy — the same things the Exchange page shows a
    signed-out reader — so this asks for no session. It returns readings and
    nothing about who is asking.
    """
    try:
        import abex_live
    except Exception:                                # pragma: no cover
        return web.json_response({"ok": False, "error": "not available"}, status=503)
    try:
        days = max(1, min(365, int(request.query.get("days", 30))))
    except (TypeError, ValueError):
        days = 30
    mid = request.match_info.get("mid") or ""
    series = (abex_live.price_series(mid, days) if mid
              else abex_live.index_series(days))
    if series is None:
        return web.json_response({"ok": False, "error": "no series"}, status=503)
    return web.json_response({"ok": True, **series})


async def _orders_moved(request):
    """`/hub/orders` used to be its own page. Orders is a section of Work now —
    same table, two sides of it — so the old path lands on the page that holds
    it rather than 404ing a link somebody has bookmarked."""
    raise web.HTTPFound("/hub/work")


def register_canvas_routes(app) -> None:
    if web is None:                                 # pragma: no cover
        return
    app.router.add_get("/hub/orders", _orders_moved)
    app.router.add_get("/hub/stocks/{mid}", _stock_page)
    app.router.add_get("/api/series/index", _series)
    app.router.add_get("/api/series/market/{mid}", _series)
    # The sample pages redirect rather than 404: they were in the nav for weeks
    # and somebody has them bookmarked.
    for key, target in _MOVED.items():
        path = PREFIX if key == "hub" else f"{PREFIX}/{key}"
        app.router.add_get(path, _moved(target))
    print(f"     {PREFIX}/* retired -> the live pages under /hub")
    register_live_routes(app)
