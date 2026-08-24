"""
abex_hub.py — the Hub screen, ported from the approved mockup.

Content comes from `abex_data` so the screen can be eyeballed against the design before
it is wired to live queries. The row shapes are the contract.
"""
from __future__ import annotations

import html as _h

from abex_shell import grade_chip


def _jobs_label(n: int) -> str:
    """"All 1 open jobs" is what a count in a sentence does when nobody looks."""
    return "The one open job" if n == 1 else f"All {n} open jobs"


def _markets_label(n: int) -> str:
    return "The one market" if n == 1 else f"All {n} markets"


def body(*, tiles, markets, work, dividends=("214.60c", "228c"),
         sub: str = "Thirteen markets, each weighted by its credit grade.",
         market_count: int = 13, work_count: int = 7,
         last_col: str = "Next report",
         dividend_note: str = ("Estimates use each market's trailing net. A figure only "
                               "becomes confirmed when that market's report lands.")) -> str:
    band = "".join(
        f'<div class="tile"><span class="k">{_h.escape(k)}</span>'
        f'<span class="v" style="color:{c}">{_h.escape(v)}</span>'
        f'<span class="n">{_h.escape(note)}</span></div>'
        for k, v, note, c in tiles)

    rows = "".join(
        f'<tr class="clickable" onclick="location.href=\'/markets/{t.lower()}\'">'
        # The real name, once. "GREY GreyHames" put an id next to the thing it
        # is an id for; the ticker earns its own column on the Markets screen.
        f'<td><strong>{_h.escape(name)}</strong></td>'
        f'<td>{grade_chip(grade)}</td>'
        f'<td class="num">{_h.escape(backing)}</td>'
        f'<td class="num">{_h.escape(net)}</td>'
        f'<td class="num faint">{_h.escape(nxt)}</td></tr>'
        for t, name, _owner, grade, backing, net, _w, nxt in markets)

    wrows = "".join(
        f'<tr><td>{_h.escape(item)}</td>'
        f'<td class="faint">{_h.escape(market)} &middot; {_h.escape(qty)}</td>'
        f'<td class="num">{_h.escape(pay)}</td>'
        f'<td class="num" style="color:{wc}">{_h.escape(win)}</td></tr>'
        for item, qty, pay, market, win, wc in work)

    confirmed, estimated = dividends
    return f"""
<div class="pagehead">
  <div>
    <h1>Abexilas index</h1>
    <div class="sub">{_h.escape(sub)}</div>
  </div>
</div>

<div class="band four">{band}</div>

<div class="grid two">
  <div class="panel accented">
    <div class="h2">Markets by grade <a href="/markets" class="faint"
      style="float:right;text-transform:none;letter-spacing:0">{_markets_label(market_count)}</a></div>
    <div class="tablewrap"><table>
      <thead><tr><th>Market</th><th>Grade</th><th class="num">Backing</th>
        <th class="num">Last net</th><th class="num">{_h.escape(last_col)}</th></tr></thead>
      <tbody>{rows}</tbody>
    </table></div>
    <div class="tfoot">Showing {len(markets)} of {market_count} markets, best grade first.</div>
  </div>

  <div class="panel">
    <div class="h2">Dividends</div>
    <div class="tablewrap"><table style="min-width:0">
      <tbody>
        <tr><td>Confirmed, last cycle</td><td class="num">{confirmed}</td></tr>
        <tr><td>Estimated, next cycle</td><td class="num faint">{estimated}</td></tr>
      </tbody>
    </table></div>
    <div class="tfoot">{_h.escape(dividend_note)}</div>
  </div>
</div>

<div class="panel">
  <div class="h2">Open work <a href="/work" class="faint"
    style="float:right;text-transform:none;letter-spacing:0">{_jobs_label(work_count)}</a></div>
  <div class="tablewrap"><table>
    <thead><tr><th>Item</th><th>Market</th><th class="num">Pay</th>
      <th class="num">Window</th></tr></thead>
    <tbody>{wrows}</tbody>
  </table></div>
</div>
"""
