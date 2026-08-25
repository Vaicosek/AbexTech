"""terms_web.py — the one public page on the site: what the coins are.

Public on purpose. Every other page behind `require_page_session` is for people
who already have an account; this one exists for the person who has NOT signed
in and wants to know what they would be signing into, and for anyone asking what
this platform is. It therefore takes no session, reads no database and renders
from constants — it must still answer when the bot is down.

## Why the wording is what it is

The tempting line is "coins have no value." Do not write that. It is a claim
about what happens to a coin after it leaves this software, which is not
something this software knows or controls — so it is a promise the platform
cannot keep, and a term that can be shown to be untrue is worse than no term.

What IS true, and is what actually protects the platform, is narrower and is
entirely about this codebase:

  * Abex Tech never sells coins and never redeems them for money. Coins enter
    and leave only through in-game activity. No payment method is attached to
    any part of this codebase and none is planned.
  * Real-money trading of coins is against the rules here.
  * There is no wagering. No game of chance, no betting on outcomes, no pools.
    The prediction-market surface that once existed here has been removed —
    route, nav entry, API and UI — and the betting mockup with it. What is left
    is guardrail only: `games` is a reserved ledger identity with no command
    surface, and `gambling_blocked` is a wallet flag that exists so borrowed
    coins could never fund a wager. A lock on a door the building does not have
    is not evidence of the room.

Those three are statements about what this software does, and they stay true
regardless of anything that happens outside it.
"""
from __future__ import annotations

import html as _h

try:
    from aiohttp import web
except Exception:  # pragma: no cover — same pattern as every other section
    web = None  # type: ignore

from abex_theme import THEME_CSS, FONTS_LINK

#: (heading, [paragraph, ...]). Kept as data so the footer summary below and the
#: page cannot drift apart: both are generated from this.
SECTIONS: list[tuple[str, list[str]]] = [
    ("What Abex Tech is", [
        "Abex Tech is the economy layer for a Minecraft server. It keeps the "
        "books for in-game shops, share listings, land sales, loans and bonds, "
        "and it renders them on this site. It is a game.",
        "Everything it records happens inside Discord and Minecraft. Nothing it "
        "records happens anywhere else.",
    ]),
    ("Coins are game currency", [
        "Coins exist only inside this economy. They are earned and spent through "
        "in-game activity — selling to shops, running a market, working orders, "
        "holding shares.",
        "Abex Tech does not sell coins and does not buy them back. There is no "
        "way to put money into this platform and no way to take money out of it. "
        "No payment method is connected to any part of it.",
        "A coin balance is not a deposit, not a savings account, not a security "
        "and not a claim on anything outside the game, whatever the pages call "
        "it. The banking language is theme.",
    ]),
    ("No real-money trading", [
        "Trading coins, shares, land or items for real money is against the "
        "rules of this platform. That applies to selling and to buying, and it "
        "applies whether the trade is arranged here, in Discord or anywhere else.",
        "Accounts found doing it can be frozen and their positions unwound.",
    ]),
    ("No gambling", [
        "Abex Tech runs no game of chance and takes no bets. There is no casino, "
        "no lottery, no prediction market and no wagering pool on in-game events, "
        "and none is planned.",
        "Markets, shares, bonds, loans and land are economic mechanics: what you "
        "get out depends on what you and other players do, not on an outcome "
        "drawn at random.",
    ]),
    ("The books are open", [
        "Every movement of coins is written to an append-only ledger with the "
        "reason it happened and the account on each side. Staff actions are "
        "logged the same way. Nothing here is designed to make a transfer harder "
        "to trace, and nothing here should be used to try.",
    ]),
    ("No guarantees", [
        "This is a hobby project run for one server. Balances can be corrected, "
        "markets can be delisted, the economy can be rebalanced and the whole "
        "thing can stop. None of that entitles anyone to anything, because none "
        "of it was ever worth anything outside the game.",
    ]),
]

#: The one line that goes in the page shell's footer, everywhere.
FOOTER_LINE = ("Coins are in-game currency for Discord and Minecraft. Abex Tech "
               "neither sells nor redeems them for money, real-money trading is "
               "against the rules, and nothing here is a wager.")

_CSS = """
main.terms{max-width:64ch;margin:0 auto;padding:4rem 2rem 6rem}
main.terms h1{font-size:1.9rem;font-weight:400;margin:0 0 .4rem;letter-spacing:.01em}
main.terms .sub{color:var(--dim);margin:0 0 3rem;font-size:.95rem}
main.terms h2{font-size:1.05rem;font-weight:400;color:var(--accent);
  margin:2.6rem 0 .8rem;letter-spacing:.02em}
main.terms p{margin:0 0 1rem;line-height:1.65;font-size:1.02rem}
main.terms .back{display:inline-block;margin-top:3.5rem;color:var(--dim);
  font-size:.9rem;text-decoration:none;border-bottom:1px solid var(--line)}
main.terms .back:hover{color:var(--text)}
"""


def render_terms() -> str:
    """The whole page. Standalone — it does not go through `abex_shell.render`,
    because the shell's nav assumes a signed-in viewer and this page must answer
    for someone who is not."""
    out = []
    for heading, paras in SECTIONS:
        out.append(f"<h2>{_h.escape(heading)}</h2>")
        out.extend(f"<p>{_h.escape(p)}</p>" for p in paras)
    body = "\n".join(out)
    return f"""<!DOCTYPE html>
<html lang="en" data-domain="banking"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Terms &middot; Abex Tech</title>
{FONTS_LINK}
<style>{THEME_CSS}</style>
<style>{_CSS}</style>
</head><body data-domain="banking">
<main class="terms">
<h1>Abex Tech</h1>
<p class="sub">What the coins are, and what they are not.</p>
{body}
<a class="back" href="/hub">Back to the hub</a>
</main>
</body></html>"""


async def _handle_terms(request):
    return web.Response(text=render_terms(), content_type="text/html",
                        charset="utf-8")


def register_terms_routes(app) -> None:
    if web is None:  # pragma: no cover
        return
    app.router.add_get("/terms", _handle_terms)
