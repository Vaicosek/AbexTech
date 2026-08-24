"""The house embed — Abex Tech, Warm Feel.

Ported from `Abex Tech Discord Bot.dc.html` (skin "Warm Feel", its default), which
is the Discord half of the same design as the website. What the mockup encodes,
in the order it encodes it:

    kicker     the command that produced this, in small grey type  -> author line
    title      the subject, sentence case, no emoji
    desc       the one sentence that matters, or nothing
    band       up to three short parallel figures                  -> inline fields
    groups     labelled groups of label/value rows                 -> block fields
    foot       scope or a real timestamp                           -> footer

Discord gives us none of the mockup's per-value colour: a field value cannot be
tinted, only the bar down the left edge can. So the tone rules the site uses on
every figure collapse here into one decision — what the bar means — and the
figures themselves stay plain. That is the honest translation, not a limitation
worth faking with ANSI code blocks: those are monospace, they wrap badly at
380px, and a table drawn in box characters is the loudest "a bot wrote this"
tell there is.

Rules this module enforces so no caller has to remember them:

* No emoji. Not in the title, not in a field name, not as a bullet.
* Sentence case everywhere. Field names are nouns, not banners.
* The bar is `ACCENT` for anything official, `LOSS` for a failure or a loss,
  `GAIN` only for money actually received, and unset (grey) for the merely
  informational. There is no per-command colour.
* At most three band tiles, because four wrap to a second row on a phone.
* Every price carries its unit; `coins`, `per_piece` and `per_stack` below are
  the only correct way to write one. A stack is 64 pieces.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

import discord

# ── the bar ──────────────────────────────────────────────────────────────
# The palette has ONE definition, in abex_theme, and Discord gets it converted.
# It used to be written out twice -- hex strings for the website, ints here --
# with nothing holding the two in step. They happened to agree; agreeing by
# coincidence is not the same as being the same colour, and the failure mode is
# a rebrand that lands on the site and silently misses every embed.
#
# abex_theme is pure data (no discord import), so this direction is safe.
import abex_theme as _theme


def _bar(hex_colour: str) -> int:
    """'#c9b37a' -> 0xC9B37A. discord.Embed wants an int."""
    return int(str(hex_colour).lstrip("#"), 16)


#: Official statements: reports, dividends, panels, anything the bot asserts.
ACCENT = _bar(_theme.ACCENT)
#: Money actually received by the person reading it.
GAIN = _bar(_theme.GAIN)
#: A failure, a refusal, or money leaving. Warm Feel has no separate amber --
#: warning and loss are one token, deliberately, and _theme.WARN is the same value.
LOSS = _bar(_theme.LOSS)
#: Money parked rather than lost: escrow, stakes, a vault. Never the loss tone.
HELD = _bar(_theme.HELD)
#: Informational. Leave the bar grey rather than colouring it for decoration.
NEUTRAL = None


def grade_bar(grade: str) -> Optional[int]:
    """Embed bar for a credit grade, or NEUTRAL when the grade is unknown.

    Same ramp the site uses. An unrated market gets no colour rather than the loss
    tone -- it has no market cap to divide by, so it has no grade, and painting that
    red tells an owner they failed a rating nobody gave them.
    """
    tone = _theme.grade_tone(grade)
    return _bar(tone) if tone else NEUTRAL

STACK = 64


# ── figures ──────────────────────────────────────────────────────────────
def coins(value, dp: int = 0) -> str:
    """`1,240c`. Thousands separated, unit attached, never a bare number."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{n:,.{dp}f}c"


def signed(value, dp: int = 0) -> str:
    """`+1,240c` / `-320c`. For a change, never for a balance."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{n:+,.{dp}f}c"


def per_piece(value, dp: int = 2) -> str:
    return f"{coins(value, dp)} per piece"


def per_stack(value, dp: int = 2) -> str:
    """A stack is 64 pieces, and the label says so every time — the per-piece /
    per-stack confusion is the single most repeated bug in this economy."""
    return f"{coins(value, dp)} per stack"


def multiple(value, dp: int = 2) -> str:
    """`1.70×` — a backing ratio or a P/E."""
    try:
        return f"{float(value):,.{dp}f}×"
    except (TypeError, ValueError):
        return "—"


def pct(value, dp: int = 2) -> str:
    try:
        return f"{float(value):+,.{dp}f}%"
    except (TypeError, ValueError):
        return "—"


def when(dt) -> str:
    """Discord's own relative stamp, so it renders in the reader's timezone.

    Never write "~2d" or "6d" by hand: the client can do this correctly and a
    hand-rolled approximation is wrong for everyone outside your timezone.
    """
    try:
        return f"<t:{int(dt.timestamp())}:R>"
    except Exception:
        return "—"


def on_day(dt) -> str:
    """`Sat 29 Aug` in the reader's own timezone."""
    try:
        return f"<t:{int(dt.timestamp())}:D>"
    except Exception:
        return "—"


# ── the shape ────────────────────────────────────────────────────────────
def rows(pairs: Iterable[Sequence], strong: Optional[str] = None) -> str:
    """Render `(label, value)` pairs as one line each.

    The mockup puts the label left and the figure right on its own rule. Discord
    has no columns, so a row is `label — value`, which is what reads on a phone.
    `strong` names the one label whose value is bolded; the mockup bolds the
    figure a decision hangs on and nothing else.
    """
    out = []
    for pair in pairs:
        label, value = pair[0], pair[1]
        text = f"**{value}**" if strong and str(label) == strong else str(value)
        out.append(f"{label} — {text}")
    return "\n".join(out) or "—"


def embed(*, title: str, kicker: str = "", desc: str = "",
          band: Optional[Sequence[Sequence]] = None,
          groups: Optional[Sequence[Sequence]] = None,
          foot: str = "", colour: Optional[int] = ACCENT,
          url: str = "") -> discord.Embed:
    """Build one house embed.

    band:   `[(label, value), ...]` — at most three, short and parallel.
    groups: `[(label, rows_text), ...]` — each becomes one full-width field.
    """
    e = discord.Embed(title=title, colour=colour)
    if url:
        # The title becomes a link to the thing itself on the site. It is also
        # where a persistent view recovers its subject after a restart, which is
        # why it is a real URL and not decoration.
        e.url = url
    if kicker:
        e.set_author(name=kicker)
    if desc:
        e.description = desc

    for pair in (band or [])[:3]:
        e.add_field(name=str(pair[0]), value=str(pair[1]), inline=True)

    for pair in (groups or []):
        label, value = pair[0], pair[1]
        if not value:
            # An empty group is left out entirely. Empty states are empty: no
            # "None" row, no em-dash placeholder standing in for data.
            continue
        e.add_field(name=str(label), value=str(value), inline=False)

    if foot:
        e.set_footer(text=foot)
    return e


def line(*parts) -> str:
    """One event, one line, for a channel feed: label, subject, figures, time.

    `line("Iron ingot", "Toolshop", "8 stacks", per_stack(42), "closes in 31 minutes")`
    No bold, no emoji, no embed — the format John accepted for feeds.
    """
    return " · ".join(str(p) for p in parts if p not in (None, ""))
