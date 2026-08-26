"""The legacy pages, in the new shell. Same data, same behaviour, one nav.

WHAT THIS IS NOT: a rewrite. `/inventory`, `/ledger`, `/orders`, `/teams`,
`/liabilities`, `/investor` and `/mymarket` are working pages with years of
behaviour in them — a barrel capacity derived when a scan stored none, learned
aliases that turn `Diamond Pickaxe#akQ` back into the real item, listing bundles
beside unit prices, a teams window that can be re-ranged. Rebuilding those as
designed screens would have thrown the lot away and looked fine in a screenshot.

WHAT IT IS: a skin swap, and a small one. `_TERMINAL_CSS` is ALREADY Warm Feel —
same tokens, same colours, same serif — so the only thing that made these look
like a different site was the nav: each carried its own `header.tshell` with its
own set of links, so somebody on `/inventory` could not see the rest of the
product and somebody in the hub could not see Inventory.

So the body is lifted out of the template and re-hung inside `abex_shell.render`,
which owns the nav, the header and the theme. The page's own `<style>` and
`<script>` ride along through the `extra_css` and `tail` hatches that exist for
exactly this — `render`'s docstring calls them "a compatibility stylesheet for a
page whose markup still uses the old class vocabulary", which is precisely what
these are.

Three rules of the extraction, and each one is a bug that happened:

* THE OLD HEADER GOES. `__NAV__` is replaced with nothing, and `header.tshell`
  is dropped from the stylesheet. Leaving the rules in put a second, differently
  styled header bar under the real one.
* `body{}` GOES. The legacy sheet sets the background, the dot grid and a 19px
  base — the type scale this project already decided was a fifth too big. The
  shell owns the body; a page-level `body` rule silently un-does that decision
  for seven pages.
* THE SCRIPT MOVES TO THE END, unchanged. These pages render themselves from a
  JSON blob the handler injects. Leaving the script in the body meant it ran
  before the shell's own markup existed.
"""
from __future__ import annotations

import json as _json
import logging
import re

log = logging.getLogger("abex_reskin")

#: Rules in `_TERMINAL_CSS` that fight the shell rather than style the page.
#: Matched on the SELECTOR at the start of a rule, so a later rule that merely
#: mentions one of these in a descendant selector is left alone.
_DROP = ("body", "header.tshell", ".brand", ".rt", "*")


#: The wrapper the whole legacy body is hung inside, and every legacy rule is
#: scoped to. See `_scope_css`.
SCOPE = "legacypage"


def _scope_css(css: str, scope: str = SCOPE) -> str:
    """Confine a legacy stylesheet to `.legacypage`, and drop the page chrome.

    TWO STYLESHEETS ON ONE PAGE MEANS TWO VOCABULARIES, and these two share ten
    class names — `.bar`, `.chip`, `.btn`, `.tag`, `.fillbar`, `.up`, `.down`,
    `.muted`, `.faint`, `.mono`. That is not a theoretical hazard. `.bar` is a
    6px progress bar in the shell and a filter row on the inventory page; the
    page's rule sets no height, so there was nothing to override the shell's
    `height:6px`, and the row's chips were sliced in half by its `overflow:
    hidden`. Two rows on every one of these pages, and it looked like a broken
    font before anyone worked out it was a name.

    Scoping is the fix rather than renaming, because renaming fixes one name and
    leaves nine, and the eleventh appears the next time either side adds a rule.

    `:root` is rewritten to the scope rather than dropped: it carries the
    tokens the page's own rules read. Left global it would also overwrite the
    SHELL's `--line` and `--accent` — the same values today, both being Warm
    Feel, which is precisely the kind of accident that survives until somebody
    retunes one of them.

    Anything unparseable is KEPT and left global: dropping a rule by accident
    breaks a page silently, keeping one only risks a cosmetic clash.
    """
    out = []
    for head, body, whole in _rules(css):
        if head.startswith("@"):
            if body is None:
                out.append(whole)                    # @import, @charset
            else:
                out.append(head + "{" + _scope_css(body, scope) + "}")
            continue
        heads = []
        for h in head.split(","):
            h = h.strip()
            if not h:
                continue
            bare = h.split(":")[0].split(" ")[0].strip()
            if bare in _DROP:
                # Chrome the shell owns: the old header bar, and `body`, whose
                # 19px base would quietly undo the type scale on seven pages.
                continue
            if h in (":root", "html", "body", "*"):
                heads.append("." + scope)
            else:
                heads.append(f".{scope} {h}")
        if heads:
            out.append(",".join(heads) + "{" + (body or "") + "}")
    return "".join(out)



#: Properties a colliding shell rule can use to wreck a legacy layout, and the
#: value that means "as if the shell had never named this class". Deliberately a
#: SHORT list of box-model and flow properties rather than `all:revert`, which
#: would also strip inherited typography and leave buttons in the browser's
#: system font.
_NEUTRAL = ("height:auto;min-height:0;max-height:none;overflow:visible;"
            "position:static;float:none;transform:none;inset:auto")


def _simple_selectors(css: str) -> set:
    """The bare class/element heads a stylesheet defines, for collision-finding."""
    out = set()
    for head, body, _whole in _rules(css):
        if head.startswith("@"):
            if body:
                out |= _simple_selectors(body)
            continue
        for h in head.split(","):
            h = h.strip()
            if not h:
                continue
            first = h.split(">")[0].strip().split(" ")[0].strip()
            first = first.split(":")[0].strip()
            if first.startswith(".") and len(first) > 1:
                out.add(first)
    return out


def _shell_css() -> str:
    """Everything `hub_web.page` puts in front of a page's own stylesheet."""
    parts = []
    for mod, attr in (("vt_web_shell", "_LEGACY_CSS"), ("abex_theme", "THEME_CSS"),
                      ("canvas_web", "CANVAS_CSS")):
        try:
            parts.append(getattr(__import__(mod), attr))
        except Exception as exc:                      # pragma: no cover
            log.warning("[reskin] %s.%s unreadable: %s", mod, attr, exc)
    return "".join(parts)



def _root_tokens(css: str, scope: str = SCOPE) -> str:
    """Legacy custom properties the SHELL does not define, restored to `:root`.

    Scoping `:root` to `.legacypage` is right for the cascade and wrong for
    JavaScript. These pages read their own tokens back through
    `getComputedStyle(document.documentElement).getPropertyValue('--up')`, and a
    property that now lives on a div returns `''` there. On /orders that made a
    100%-filled progress bar render with `background:''` — an empty track, on
    the row that means the work is done.

    Only the names the shell does NOT already define are re-emitted. `--accent`
    and `--line` stay scoped, because those are exactly the ones that would
    overwrite the shell's own. `--up` is restored, because the shell has no such
    name — it calls that colour `--gain` — so nothing of the shell's is touched.

    Not caught by looking at the page: the three tokens the JS reads most
    (`--amber`, `--accent`, `--muted`) happen to exist in the shell too, so they
    resolved anyway and only `--up` was empty. A screenshot of a row that was
    not at 100% looks perfect.
    """
    import re as _re
    mine, theirs = {}, set()
    for head, body, _w in _rules(css):
        if head.startswith("@") or body is None:
            continue
        if head.strip() in (":root", "html", "body"):
            for name, value in _re.findall(r"(--[\w-]+)\s*:\s*([^;]+)", body):
                mine[name] = value.strip()
    for head, body, _w in _rules(_shell_css()):
        if body is None:
            continue
        for name, _v in _re.findall(r"(--[\w-]+)\s*:\s*([^;]+)", body):
            theirs.add(name)
    only_mine = {k: v for k, v in mine.items() if k not in theirs}
    if not only_mine:
        return ""
    decls = ";".join(f"{k}:{v}" for k, v in sorted(only_mine.items()))
    return (f"/* legacy tokens the shell does not define, kept on :root because "
            f"the page's own script reads them from documentElement */\n"
            f":root{{{decls}}}\n")


def _neutralise(page_css: str, scope: str = SCOPE) -> str:
    """Undo the shell's rules for class names the legacy page also uses.

    SCOPING THE PAGE'S OWN CSS IS NOT ENOUGH, and that is the whole lesson here.
    `.legacypage .bar` outranks `.bar`, but only for properties it DECLARES —
    and the page's `.bar` (a filter row) declares no height, so the shell's
    `.bar{height:6px}` (a progress bar) went on applying and its `overflow:
    hidden` sliced two rows of chips in half on every one of these pages.

    So for each name both sides use, a neutralising rule is emitted at the same
    specificity as the page's own scoped rules and BEFORE them: the shell's
    layout is reverted, then the page re-states whatever it actually wants.
    Only names that genuinely collide are touched, so nothing else moves.
    """
    theirs = _simple_selectors(_shell_css())
    mine = _simple_selectors(page_css)
    clash = sorted(theirs & mine)
    if not clash:
        return ""
    heads = ",".join(f".{scope} {c}" for c in clash)
    return (f"/* {len(clash)} class names are used by both stylesheets: "
            f"{' '.join(clash)} */\n{heads}{{{_NEUTRAL}}}\n")


def _rules(css: str):
    """`(selector, body, whole)` per top-level rule. `body` is None if unbraced.

    A brace-walk rather than a CSS parser: these sheets are flat rules and
    `@media` blocks, and a dependency to read them would cost more than the job.
    """
    i, n = 0, len(css)
    while i < n:
        brace = css.find("{", i)
        if brace < 0:
            rest = css[i:].strip()
            if rest:
                yield rest, None, css[i:]
            return
        depth, j = 0, brace
        while j < n:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        head = _decomment(css[i:brace]).strip()
        body = css[brace + 1:j]
        yield head, body, css[i:j + 1]
        i = j + 1


def _decomment(text: str) -> str:
    return re.sub(r"/\*.*?\*/", " ", text, flags=re.S)


def _split(template: str) -> tuple[str, str, str]:
    """`(body, page_css, scripts)` from a legacy page template.

    The template still carries its `__TERMINAL_CSS__` and `__NAV__` markers at
    this point; both are resolved here rather than by the caller, so a caller
    cannot forget one and ship a page with the literal marker in it.
    """
    html = template.replace("__NAV__", "")
    page_css = ""
    for m in re.finditer(r"<style[^>]*>(.*?)</style>", html, re.S):
        page_css += m.group(1)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.S)
    scripts = "".join(m.group(0) for m in
                      re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>.*?</script>",
                                  html, re.S))
    html = re.sub(r"<script(?![^>]*\bsrc=)[^>]*>.*?</script>", "", html,
                  flags=re.S)
    m = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
    body = m.group(1) if m else html
    # The old header is markup, not just CSS: drop the element too.
    body = re.sub(r"<header class=\"tshell\".*?</header>", "", body, flags=re.S)
    return body.strip(), page_css, scripts


def render(template: str, *, active: str, title: str, user=None, snap=None,
           replacements: dict | None = None, ownerinfo=None) -> str:
    """One legacy page, in the shell. `replacements` are its JSON injections.

    `ownerinfo` is NOT optional decoration. The old nav's script was the only
    thing that set `window.OWNERINFO`, and these pages gate real controls on it
    — the restock-generate button, the ordering cart, the trade ticket — and
    sign their POSTs with the CSRF token inside it. Dropping the nav without
    this locks ordering and unsigns two writes. It is inlined FIRST, before the
    page's own script, so nothing has to wait for it.
    """
    import abex_shell
    import hub_web
    import Restocker_web as RW

    html = template
    for key, value in (replacements or {}).items():
        html = html.replace(key, value)
    body, page_css, scripts = _split(html)
    css = (_neutralise(page_css)
           + _root_tokens(RW._TERMINAL_CSS + "\n" + page_css)
           + _scope_css(RW._TERMINAL_CSS) + "\n" + _scope_css(page_css))
    # The body goes inside the scope it was just confined to.
    body = f'<div class="{SCOPE}">{body}</div>' 
    if ownerinfo is not None:
        # `</script>` inside the JSON would close this tag early; `<` is escaped
        # so no value in a market name can break out of it.
        blob = _json.dumps(ownerinfo).replace("<", "\\u003c")
        scripts = f"<script>window.OWNERINFO={blob};</script>" + scripts
    return hub_web.page(title, active, user, snap, body, extra_css=css,
                        tail=scripts)
