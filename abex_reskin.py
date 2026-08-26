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


def _strip_shell_css(css: str) -> str:
    """Drop the rules that own the page chrome, keep the ones that style content.

    A crude brace-walk rather than a CSS parser: this sheet is 3KB of flat rules
    with no nesting beyond `@media`, and a dependency to read it would be worth
    more than the job. Anything it cannot parse is KEPT — dropping a rule by
    accident breaks a page silently, keeping one only risks a cosmetic clash.
    """
    out, i, n = [], 0, len(css)
    while i < n:
        brace = css.find("{", i)
        if brace < 0:
            out.append(css[i:])
            break
        selector = css[i:brace]
        # Walk to the matching close, so `@media{...}` survives whole.
        depth, j = 0, brace
        while j < n:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        rule = css[i:j + 1]
        heads = [h.strip() for h in selector.split("\n")[-1].split(",")]
        heads = [h for h in heads if h]
        if heads and all(h.split(":")[0].split(" ")[0] in _DROP for h in heads):
            pass                                  # chrome: the shell owns it
        else:
            out.append(rule)
        i = j + 1
    return "".join(out)


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
    css = _strip_shell_css(RW._TERMINAL_CSS) + "\n" + _strip_shell_css(page_css)
    if ownerinfo is not None:
        # `</script>` inside the JSON would close this tag early; `<` is escaped
        # so no value in a market name can break out of it.
        blob = _json.dumps(ownerinfo).replace("<", "\\u003c")
        scripts = f"<script>window.OWNERINFO={blob};</script>" + scripts
    return hub_web.page(title, active, user, snap, body, extra_css=css,
                        tail=scripts)
