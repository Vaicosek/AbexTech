"""A section's sub-categories are PAGES under it, not blocks inside it.

The mistake this file exists to prevent. Market's console grew to seven blocks —
items, shelves, ledger, month, waterfall, liabilities, staff — because things
that had always been separate pages got stacked onto one screen. Two problems,
and the second one hid the first:

1. Seven things in one scroll is not an information architecture. `/inventory`,
   `/ledger`, `/orders`, `/teams`, `/liabilities` and `/investor` are pages with
   years of behaviour in them and they were still there; the console was a
   duplicate that could only ever be a worse copy.

2. The nav derived a section's children from its BLOCK HEADINGS and capped them
   at four. So the console's own seven became four anchors, and Liabilities and
   Staff were silently not in the nav at all.

Children are DECLARED now, in `hub_web.SECTION_CHILDREN`, because a child page
is a routing fact and cannot be read off a parent's blocks. Declared children
are never capped and never derived — the cap exists to stop a long screen
becoming a table of contents, and a section's real sub-pages are not that.

The pages themselves are unchanged: `abex_reskin` lifts each legacy body into
the hub shell so there is one nav and one skin. The data, the JSON the handler
injects, and the page's own script are all still theirs.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_shell as SH        # noqa: E402
import abex_livescreens as LS  # noqa: E402
import hub_web                 # noqa: E402
import canvas_web              # noqa: E402


def _registered():
    for key, label, path, order in canvas_web.LIVE_SECTIONS:
        hub_web.register_section(key, label, path, order=order)


def _nav(active, subs):
    _registered()
    staff = False
    mounted = {hub_web._NAV_KEY_FOR(s["key"]) for s in hub_web.sections()}
    paths = {hub_web._NAV_KEY_FOR(s["key"]): s["path"] for s in hub_web.sections()}
    for kids in hub_web.SECTION_CHILDREN.values():
        for k, _l, href in kids:
            paths.setdefault(k, href)
    return SH._nav_html(active, staff, available=mounted, paths=paths, subs=subs)


def _subs(html):
    return re.findall(r'class="navsub" data-k="([^"]+)" href="([^"]+)"([^>]*)>([^<]*)',
                      html)


def test_markets_opens_to_every_one_of_its_pages():
    subs = hub_web.nav_subs("markets", None)
    labels = [s[1] for s in subs["markets"]]
    for want in ("Inventory", "Ledger", "Orders", "Teams", "Liabilities",
                 "Investor"):
        assert want in labels, f"{want} is not under Markets: {labels}"


def test_every_declared_child_is_offered():
    """There is no cap any more. The cap existed to stop a long screen becoming
    a table of contents, and screens no longer contribute children at all — a
    section's declared sub-pages are all of them, however many."""
    subs = hub_web.nav_subs("markets", None)
    assert len(subs["markets"]) == len(hub_web.SECTION_CHILDREN["markets"])
    assert not hasattr(hub_web, "NAV_SUB_LIMIT"), (
        "the cap belonged to derived children, which are gone")


def test_a_child_needs_no_screen_to_be_offered():
    """A re-skinned legacy page passes no screen at all. Asking for one first is
    how those pages rendered with the design's hardcoded child instead of their
    real siblings."""
    assert hub_web.nav_subs("markets.inventory", None) is not None
    assert hub_web.nav_subs("markets.ledger", None) is not None


def test_the_child_you_are_on_is_the_one_marked_current():
    subs = hub_web.nav_subs("markets.teams", None)
    html = _nav("markets.teams", subs)
    current = [label for _k, _h, attrs, label in _subs(html)
               if "aria-current" in attrs]
    assert current == ["Teams"], current


def test_children_only_open_under_their_own_parent():
    subs = hub_web.nav_subs("banking", None)
    html = _nav("banking", subs)
    assert _subs(html) == [], "another section must not show Markets' pages"


def test_every_child_points_at_a_route_that_exists():
    src = (HERE.parent / "Restocker_web.py").read_text(encoding="utf-8")
    hub = (HERE.parent / "canvas_web.py").read_text(encoding="utf-8")
    every = [c for kids in hub_web.SECTION_CHILDREN.values() for c in kids]
    for _k, label, href in every:
        served = (f'add_get("{href}"' in src
                  or f'"{href}"' in src
                  or href in hub)
        assert served, f"{label} points at {href}, which nobody serves"


def test_the_console_did_not_swallow_its_own_children():
    """The console is a landing. Inventory belongs at /inventory, where it has
    always been and where the legacy behaviour still lives."""
    src = (HERE.parent / "abex_livescreens.py").read_text(encoding="utf-8")
    body = src[src.index("def market(user_id"):]
    body = body[:body.index('screen_d["title"]')]
    assert "_shop_blocks(" not in body, (
        "the shelves are a child page, not a block on the parent")
    assert "_item_block(" not in body


# ── the re-skin ─────────────────────────────────────────────────────────────

def test_a_legacy_page_comes_back_with_one_nav_and_no_second_header():
    import abex_reskin
    import Restocker_web as RW
    _registered()
    html = abex_reskin.render(
        RW._INVENTORY_HTML, active="mine.inventory", title="Inventory",
        user=None, snap=None,
        replacements={"__TERMINAL_CSS__": RW._TERMINAL_CSS,
                      "__INVENTORY_JSON__": RW._jscript({"markets": []})},
        ownerinfo={"logged_in": False})
    assert html.count("<!DOCTYPE") == 1 and html.count("<body") == 1
    assert 'header class="tshell"' not in html, "the old header bar is gone"
    assert "header.tshell" not in html, "and so are the rules that drew it"
    assert 'class="navsub"' in html, "and the hub nav is what replaced it"


def test_no_placeholder_survives_the_re_skin():
    import abex_reskin
    import Restocker_web as RW
    html = abex_reskin.render(
        RW._TEAMS_HTML, active="markets.teams", title="Teams", user=None, snap=None,
        replacements={"__TERMINAL_CSS__": RW._TERMINAL_CSS,
                      "__TEAMS_JSON__": RW._jscript({})},
        ownerinfo={"logged_in": False})
    for marker in ("__NAV__", "__TERMINAL_CSS__", "__TEAMS_JSON__"):
        assert marker not in html, marker


def test_the_page_keeps_its_own_script_and_its_own_styles():
    """A skin swap. The body, the stylesheet and the script are the page's."""
    import abex_reskin
    import Restocker_web as RW
    html = abex_reskin.render(
        RW._ORDERS_HTML, active="markets.orders", title="Orders", user=None,
        snap=None,
        replacements={"__TERMINAL_CSS__": RW._TERMINAL_CSS,
                      "__ORDERS_JSON__": RW._jscript({"markets": ["MARKER"]}),
                      "__ITEMS_JSON__": RW._jscript({})},
        ownerinfo={"logged_in": False})
    assert "MARKER" in html, "its data must still reach it"
    assert ".panel" in html, "its own stylesheet must ride along"


def test_the_shell_owns_the_body_rule():
    """The legacy sheet sets a 19px base and its own background. The type scale
    was deliberately brought down; a page-level `body` rule would quietly undo
    that decision on seven pages at once."""
    import abex_reskin
    import Restocker_web as RW
    css = abex_reskin._scope_css(RW._TERMINAL_CSS)
    assert not re.search(r"(^|\})\s*body\s*\{", css), css[:200]
    assert "--accent" in css, "the tokens themselves must survive"


def test_the_legacy_tokens_do_not_leak_out_of_the_page():
    """`:root` becomes the scope. Left global it would overwrite the SHELL's
    `--line` and `--accent` — identical values today, both being Warm Feel,
    which is exactly the kind of accident that survives until one is retuned."""
    import abex_reskin
    import Restocker_web as RW
    css = abex_reskin._scope_css(RW._TERMINAL_CSS)
    assert ":root" not in css
    assert f".{abex_reskin.SCOPE}{{" in css.replace(" ", "")


def test_a_class_name_both_sheets_use_is_neutralised():
    """THE BUG THIS EXISTS FOR. `.bar` is a 6px progress bar in the shell and a
    filter row on the inventory page. Scoping the page's own CSS was not enough:
    `.legacypage .bar` outranks `.bar`, but only for properties it DECLARES, and
    the page's filter row declares no height — so `height:6px` went on applying
    and its `overflow:hidden` sliced two rows of chips in half on every page.
    """
    import abex_reskin
    import Restocker_web as RW
    page_css = re.search(r"<style[^>]*>(.*?)</style>", RW._INVENTORY_HTML,
                         re.S).group(1)
    neutral = abex_reskin._neutralise(page_css)
    assert ".bar" in neutral, "the collision that caused this must be caught"
    assert "height:auto" in neutral and "overflow:visible" in neutral
    # It must come BEFORE the page restates what it wants, or it wipes it.
    full = abex_reskin._neutralise(page_css) + abex_reskin._scope_css(page_css)
    assert full.index("height:auto") < full.rindex(".bar")


def test_only_real_collisions_are_touched():
    """A blunt reset would move things nobody asked to move."""
    import abex_reskin
    neutral = abex_reskin._neutralise(".mine-only{color:red}")
    assert neutral == "", neutral


def test_the_neutraliser_keeps_typography_alone():
    """Not `all:revert`, which strips inherited type and leaves buttons in the
    browser's system font."""
    import abex_reskin
    assert "all:" not in abex_reskin._NEUTRAL
    for prop in ("font", "color", "letter-spacing"):
        assert prop not in abex_reskin._NEUTRAL


def test_the_body_is_hung_inside_the_scope():
    import abex_reskin
    import Restocker_web as RW
    html = abex_reskin.render(
        RW._TEAMS_HTML, active="markets.teams", title="x", user=None, snap=None,
        replacements={"__TERMINAL_CSS__": RW._TERMINAL_CSS,
                      "__TEAMS_JSON__": RW._jscript({})},
        ownerinfo={"logged_in": False})
    assert f'<div class="{abex_reskin.SCOPE}">' in html


def test_every_legacy_handler_goes_through_the_shell():
    src = (HERE.parent / "Restocker_web.py").read_text(encoding="utf-8")
    for handler in ("_handle_inventory_page", "_handle_ledger_page",
                    "_handle_orders_page", "_handle_teams_page",
                    "_handle_liabilities_page", "_handle_investor_page"):
        body = src[src.index(f"async def {handler}"):]
        body = body[:body.index("\n\n\n")]
        assert "_legacy_page(" in body, f"{handler} still renders its own shell"
        assert "_TERMINAL_NAV" not in body, f"{handler} still draws the old nav"


# ── what the old nav was carrying ───────────────────────────────────────────

def test_ownerinfo_is_set_before_anything_reads_it():
    """`window.OWNERINFO` was set by the OLD NAV'S SCRIPT and by nothing else.

    Re-hanging the body without it did not merely change chrome: `/inventory`
    shows its restock-generate button only to a market's owner and signs that
    POST with `OWNERINFO.csrf`; `/orders` keeps its whole cart behind `#locked`
    until it sees `logged_in`, and posts `/api/order` with the same token. Both
    were silently broken. It is inlined server-side and FIRST — which also kills
    the async race `_MYMARKET_HTML` already carries a hand-written guard for.
    """
    import abex_reskin
    import Restocker_web as RW
    for tmpl, act, rep in (
            (RW._INVENTORY_HTML, "markets.inventory",
             {"__INVENTORY_JSON__": RW._jscript({"markets": []})}),
            (RW._ORDERS_HTML, "markets.orders",
             {"__ORDERS_JSON__": RW._jscript({"markets": []}),
              "__ITEMS_JSON__": RW._jscript({})})):
        rep = dict(rep, __TERMINAL_CSS__=RW._TERMINAL_CSS)
        html = abex_reskin.render(
            tmpl, active=act, title="x", user=None, snap=None, replacements=rep,
            ownerinfo={"logged_in": True, "csrf": "TOK", "owned": []})
        set_at = html.find("window.OWNERINFO=")
        assert set_at >= 0, f"{act} has no OWNERINFO at all"
        uses = [m.start() for m in re.finditer(r"window\.OWNERINFO(?!=)", html)]
        assert uses, f"{act} was chosen because it READS it"
        assert all(u > set_at for u in uses), (
            f"{act} reads OWNERINFO before it is set")


def test_ownerinfo_cannot_break_out_of_its_script_tag():
    import abex_reskin
    import Restocker_web as RW
    html = abex_reskin.render(
        RW._TEAMS_HTML, active="markets.teams", title="x", user=None, snap=None,
        replacements={"__TERMINAL_CSS__": RW._TERMINAL_CSS,
                      "__TEAMS_JSON__": RW._jscript({})},
        ownerinfo={"logged_in": True, "csrf": "T",
                   "owned": [{"mid": "m", "name": "</script><b>x"}]})
    blob = html[html.index("window.OWNERINFO="):]
    blob = blob[:blob.index("</script>")]
    assert "</script" not in blob and "<b>" not in blob, blob[:200]


def test_the_leaderboard_toggle_has_a_control_again():
    """It has been orphaned twice — when /classic went, and when these pages
    stopped drawing their own nav — while the setting kept working. A setting
    with a real effect and no control is worse than no setting."""
    src = (HERE.parent / "hub_web.py").read_text(encoding="utf-8")
    assert 'id="navAnon"' in src
    assert "anonymous" in src, "the header must know the current value"
    js = canvas_web.CANVAS_JS
    assert "/api/anon" in js
    i = js.index("navAnon")
    assert "j.anonymous" in js[i:i + 3000], (
        "repaint from what the server says, not from what was asked for")


def test_the_toggle_defaults_to_hidden_when_unknown():
    """`_holder_label()` hides an unset user. Reporting "visible" for somebody
    who is actually hidden, then toggling twice, would EXPOSE them."""
    src = (HERE.parent / "hub_web.py").read_text(encoding="utf-8")
    i = src.index("anonymity preference unreadable")
    assert "anon = True" in src[max(0, i - 700):i]


def test_legacy_tokens_the_shell_lacks_stay_readable_from_javascript():
    """Scoping `:root` is right for the cascade and wrong for JavaScript.

    These pages read their own tokens back through
    `getComputedStyle(document.documentElement).getPropertyValue('--up')`. Once
    `:root` became `.legacypage`, that returned '' — and on /orders a
    100%-filled progress bar rendered with `background:''`, an empty track, on
    the row that means the work is finished.

    Nearly invisible: the three tokens the JS reads most (`--amber`,
    `--accent`, `--muted`) exist in the shell too, so they resolved anyway.
    Only `--up` was empty, and only on rows at 100%.
    """
    import abex_reskin
    import Restocker_web as RW
    page_css = re.search(r"<style[^>]*>(.*?)</style>", RW._ORDERS_HTML,
                         re.S).group(1)
    root = abex_reskin._root_tokens(RW._TERMINAL_CSS + page_css)
    assert "--up:" in root, "the page's JS cannot see --up without this"
    # And the ones that WOULD overwrite the shell stay scoped.
    for shared in ("--accent:", "--line:"):
        assert shared not in root, (
            f"{shared} is the shell's too; putting it back on :root overwrites it")


def test_the_orders_progress_bar_has_a_colour_to_read():
    """The concrete failure, end to end: status 'ready' and a 100% bar both ask
    for `--up` by name from documentElement."""
    import abex_reskin
    import Restocker_web as RW
    assert "css('--up')" in RW._ORDERS_HTML, (
        "if this moves, this test is checking the wrong thing")
    assert "getComputedStyle(document.documentElement)" in RW._ORDERS_HTML
    root = abex_reskin._root_tokens(RW._TERMINAL_CSS)
    assert "#8fbf6a" in root


def test_the_legacy_pages_use_the_shells_type_scale():
    """"its too huge" — the legacy sheets were written at a 19px base and the
    shell's ramp was brought down to 15px, so a re-skinned page put 19-28px
    content inside 15px chrome. Scaled 15/19, mechanically, so the page's own
    ramp between its sizes is preserved and only the base moves."""
    import abex_reskin
    import Restocker_web as RW
    # The 19px BASE came from `body{}`, which is dropped as chrome — the page
    # inherits the shell's 15px instead. What still needed scaling is the page's
    # own ramp above that base: 21px table text, 25px group rows, 28px titles.
    page_css = re.search(r"<style[^>]*>(.*?)</style>", RW._LEDGER_HTML,
                         re.S).group(1)
    before = set(re.findall(r"font-size:\s*([\d.]+)px", page_css))
    scaled = abex_reskin._rescale_type(abex_reskin._scope_css(page_css))
    after = set(re.findall(r"font-size:\s*([\d.]+)px", scaled))
    big_before = {float(x) for x in before if float(x) > 16}
    big_after = {float(x) for x in after if float(x) > 16}
    assert big_before, "this test is pointless if the sheet had no large type"
    assert max(big_after) < max(big_before), (
        "largest type went %s -> %s" % (max(big_before), max(big_after)))
    assert not any(float(x) > 11 and float(x) < 11.0 for x in after)


def test_only_type_is_scaled_not_layout():
    """Padding, widths and heights are the page's layout. Shrinking those is a
    different change nobody asked for — the theme rescale did not touch them
    either."""
    import abex_reskin
    css = ".x{font-size:20px;padding:14px 26px;width:120px;height:38px}"
    out = abex_reskin._rescale_type(css)
    assert "padding:14px 26px" in out
    assert "width:120px" in out and "height:38px" in out
    assert "font-size:15.8px" in out


def test_fine_print_is_not_scaled_into_illegibility():
    import abex_reskin
    for small in ("font-size:10.5px", "font-size:11px"):
        assert abex_reskin._rescale_type(small) == small
    # and nothing is ever pushed below the floor
    assert "font-size:11px" in abex_reskin._rescale_type("font-size:13px")


def test_the_brand_is_type_not_an_asset():
    """The medallion is gone: a ring badge with five labelled feature icons
    around a bevelled gradient A, which his own players called "ai shit" and
    which `atech-brief.md` bans in as many words ("no logo medallion").

    Type cannot look generated, and needs no asset, so it cannot 404 the way the
    first version silently did."""
    src = (HERE.parent / "abex_shell.py").read_text(encoding="utf-8")
    assert "LOGO_SRC" not in src, "the badge constant is gone"
    assert '<img class="mark"' not in src, "and so is the element"
    assert '<span class="wordmark">' in src
    assert '<span class="rule">' in src, "the masthead rule he picked (option A)"


def test_every_legacy_page_is_off_the_old_nav():
    """/mymarket and /report were missed by the first pass and kept drawing
    `_TERMINAL_NAV`, so the site still had two navs for anyone who reached them.
    The only surviving reference is the fallback inside `_legacy_page`."""
    src = (HERE.parent / "Restocker_web.py").read_text(encoding="utf-8")
    # Prose inside a docstring mentions it too; this looks for CODE.
    live = [ln for ln in src.splitlines()
            if "_TERMINAL_NAV" in ln and not ln.strip().startswith("#")
            and "_TERMINAL_NAV = " not in ln
            and "`_TERMINAL_NAV`" not in ln]
    assert len(live) == 1, live
    assert 'html.replace("__NAV__", _TERMINAL_NAV)' in live[0], live[0]


def test_the_front_door_is_the_hub():
    """`/` served the Inventory page — a legacy tab picked when it was the only
    page there was."""
    src = (HERE.parent / "Restocker_web.py").read_text(encoding="utf-8")
    assert 'add_get("/",              _handle_root_redirect)' in src
    assert "HTTPFound(\"/hub\")" in src


def test_a_legacy_palette_is_bridged_not_left_arguing():
    """The monthly report is GitHub-dark — #0d1117, blue links, monospace —
    because it was built as a standalone attachment. Hung in the shell untouched
    it puts a blue monospace document inside warm serif chrome."""
    import abex_reskin
    gh = (":root{--bg:#0d1117;--card:#161b22;--line:#21262d;--fg:#e6edf3;"
          "--muted:#8b949e;--green:#3fb950;--red:#f85149;--blue:#58a6ff;"
          "--gold:#d29922}")
    bridge = abex_reskin._bridge_palette(gh)
    assert "--blue:var(--accent)" in bridge, "one interactive colour, not two"
    assert "--green:var(--gain)" in bridge


def test_a_same_named_token_is_never_bridged_to_itself():
    """`.legacypage{--line:var(--line)}` is a custom property referencing
    itself. CSS calls that cyclic and makes it guaranteed-invalid, so every
    border drawn with var(--line) would vanish. A shared name needs no bridge —
    dropping the page's own declaration lets the shell's inherit."""
    import abex_reskin
    gh = (":root{--bg:#0d1117;--card:#161b22;--line:#21262d;--fg:#e6edf3;"
          "--muted:#8b949e;--green:#3fb950;--red:#f85149;--blue:#58a6ff}")
    assert "--line:var(--line)" not in abex_reskin._bridge_palette(gh)
    # and the page's own value must not shadow the shell's either
    assert "--line:#21262d" not in abex_reskin._scope_css(gh)


def test_a_page_already_on_warm_feel_gets_no_bridge():
    import abex_reskin
    import Restocker_web as RW
    assert abex_reskin._bridge_palette(RW._TERMINAL_CSS) == ""
