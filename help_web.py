"""The "How X works" pages.

WHY THIS FILE EXISTS. The design brief says an explanatory paragraph does not sit inside
content — "link to a How X works page instead" — so the screens had ~30 subtitle,
caption and footnote sentences removed and seven of them replaced with a link. The links
were written before the pages were, so for one round every one of them was a 404: the
rule had been deleted from the screen and not written down anywhere else. A rule a
reader needs in order to not misread a money figure cannot be deleted; it can only be
MOVED, and this is where it moved to.

The text here is recovered verbatim from what was cut, not rewritten from memory.

There is no navigation to these pages by design. They are reached from the one screen
whose figures they explain, which is the whole point of moving them off it.
"""
from __future__ import annotations

try:
    from aiohttp import web
except Exception:                                    # pragma: no cover
    web = None

import abex_shell


#: topic -> (title, [paragraph, ...]). Recovered from the screens they were cut from.
TOPICS: dict[str, tuple[str, list[str]]] = {
    "grades": ("How grades work", [
        "A grade is led by BACKING. Composite quality alone cannot reach the top "
        "bands — a market with excellent numbers and nothing behind them is not "
        "investment grade, because the grade is a claim about what a holder can "
        "recover, not about how well the shop is trading.",
        "AAA needs 1.6× backing · AA 1.2× · A fully backed · BBB 0.6× · BB 0.3× · "
        "C under 0.3×.",
        "An unlisted market has no market cap, so backing cannot be computed for it. "
        "Those markets are NOT RATED, which is not a bad grade and is never drawn in "
        "the loss colour.",
    ]),
    "borrowing": ("How borrowing works", [
        "Interest is charged per cycle and is paid out of net BEFORE dividends. A "
        "borrower's lenders are paid before the borrower's shareholders.",
        "Missed payments take the collateral. They do not touch the shares.",
        "Rates run by tier, from 18% a year down for longer-standing accounts.",
    ]),
    "bonds": ("How bonds work", [
        "Coupons are paid out of net before dividends, on the same rule as loan "
        "interest: a market pays what it owes before it pays what it chooses to.",
        "A bond states what backs it. That backing is what a holder recovers if the "
        "market cannot pay, and it is the figure to read before the coupon.",
    ]),
    "pay": ("How pay works", [
        "Claim a production order, deliver it, get paid.",
        "PAY IS PER PIECE unless the order says per stack — and a stack is 64. This "
        "is the one unit rule on the site worth reading twice: an order quoted per "
        "barrel is 3,456 pieces, so a rate that looks like 345,600c is 100.00c a "
        "piece.",
    ]),
    "claims": ("How claims work", [
        "A parcel is bought outright. What the table shows is who holds it and what "
        "it went for.",
        "A lapsed lease returns the parcel to the market at its listed price.",
    ]),
    "preferred": ("How preferred shares work", [
        "GEX.PR preferred is a separate class from common shares. Common holders "
        "take no cut of this pool.",
        "A fixed percentage of each market's monthly net feeds the preferred pool. "
        "A market that lost money contributes nothing — the pool is a share of "
        "profit, not a charge on the group.",
    ]),
    "filings": ("How filings work", [
        "A market files a report when its month closes. Reports arrive when an owner "
        "files them; nothing schedules them, so there is no due date to miss.",
        "A missed filing keeps the last price, pays no dividend, and drops a band.",
    ]),
}


def page_html(topic: str) -> str | None:
    """The rendered page, or None for a topic that does not exist."""
    entry = TOPICS.get(topic)
    if entry is None:
        return None
    title, paras = entry
    body = ['<div class="pagehead"><div><h1>%s</h1></div></div>' % abex_shell._h.escape(title)]
    body.append('<div class="panel">')
    for p in paras:
        body.append('<p class="helpp">%s</p>' % p)
    body.append("</div>")
    # No "back" link: the browser has one, and inventing a second navigation for a
    # page reached from exactly one place is chrome the product does not need.
    return abex_shell.render("", "".join(body), title=title,
                             extra_css=".helpp{margin:0 0 14px;max-width:70ch;"
                                       "text-wrap:pretty}.helpp:last-child{margin:0}")


def register_help_routes(app) -> None:
    """Mount `/help/<topic>`. A topic with no entry 404s rather than rendering empty."""
    if web is None:                                  # pragma: no cover
        return

    async def handle(request):
        html = page_html(str(request.match_info.get("topic") or ""))
        if html is None:
            raise web.HTTPNotFound()
        return web.Response(text=html, content_type="text/html")

    app.router.add_get("/help/{topic}", handle)
