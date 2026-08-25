"""
abex_tiers.py — rank ladder for the whole network.

⚠️ INCOMPLETE MODEL — READ BEFORE EXTENDING
    John has TWO ladders, not one: a **company rank** (what you made for the company) and
    a **bank rank** (what you hold at the bank). They are intertwined — each informs the
    other — but they are separate standings with separate benefits, and a customer can sit
    high on one and low on the other.

    What is implemented below is a SINGLE blended score, which was the earlier reading of
    the design. It is directionally right (both halves count, savings are capped so they
    cannot buy standing on their own) but it collapses two ladders into one and cannot
    express "Veteran at the company, Silver at the bank".

    Splitting it is the first task in `abex-handoff.md`. Do not wire the benefits below
    into live fee code until that split is settled, or the fees will be attributed to the
    wrong ladder.

A rank is earned by TWO things, and the split is the point of the design:

  * what you made for the company — loyalty points, awarded on orders filled and sales.
  * what you hold at the bank — your savings balance.

Neither alone gets you far. Savings are converted to a points-equivalent and added, but
capped so they can **at most double** what you earned: park a fortune and contribute
nothing and your rank stays Recruit, because half of nothing is nothing. That one rule is
what stops the ladder becoming a rich-list.

The rank then pays out in EVERY domain, not just at the bank — a better savings rate, a
lower trading fee, a smaller cut on a market sale, less rake on a bet, a cheaper parcel
listing, and a bigger bonus on every order you fill.

WHY THIS MODULE EXISTS
    The thresholds and the savings/payout numbers already lived in `Restocker_main`
    (`LOYALTY_TIERS`). The other five domains had no concept of a rank at all, so each
    would have grown its own. This is the single table they all read.

    It is data, not behaviour — every domain looks up its own benefit and applies it in
    its own code path. Nothing here moves money.

USE
    from abex_tiers import summary, benefit
    s = summary(points=6_200, savings=156_900)   # rank + benefits + how it was earned
    fee = benefit(s["score"], "stocks")          # 0.60
"""
from __future__ import annotations

#: The ladder. Thresholds and the first two benefits come from the live
#: `LOYALTY_TIERS`; the rest were set here so every domain rewards the same ladder.
#:
#: savings_pct_month — RATES ARE PER MONTH, because that is how the server states them.
#:   The live rate today is a flat 0.5% a month for everyone, so Recruit sits exactly
#:   there: nobody loses anything the day tiers switch on. Higher ranks earn more, up to
#:   3x the base at Elite. Multiply by 12 for the rough annual figure, or compound it
#:   ((1+r)^12-1) for the exact one — `annual_pct()` below does the compounding.
TIERS = [
    {
        "key": "recruit", "name": "Recruit", "min_points": 0,
        "savings_pct_month": 0.50, "payout_bonus_pct": 0,
        "trade_fee_pct": 1.00,    "market_commission_pct": 5.00,
        "land_listing_fee_pct": 5.00,
    },
    {
        "key": "worker", "name": "Worker", "min_points": 1_000,
        "savings_pct_month": 0.60, "payout_bonus_pct": 2,
        "trade_fee_pct": 0.90,    "market_commission_pct": 4.75,
        "land_listing_fee_pct": 4.75,
    },
    {
        "key": "veteran", "name": "Veteran", "min_points": 5_000,
        "savings_pct_month": 0.80, "payout_bonus_pct": 5,
        "trade_fee_pct": 0.75,    "market_commission_pct": 4.50,
        "land_listing_fee_pct": 4.50,
    },
    {
        "key": "expert", "name": "Expert", "min_points": 15_000,
        "savings_pct_month": 1.10, "payout_bonus_pct": 8,
        "trade_fee_pct": 0.60,    "market_commission_pct": 4.00,
        "land_listing_fee_pct": 4.00,
    },
    {
        "key": "elite", "name": "Elite", "min_points": 40_000,
        "savings_pct_month": 1.50, "payout_bonus_pct": 12,
        "trade_fee_pct": 0.50,    "market_commission_pct": 3.50,
        "land_listing_fee_pct": 3.50,
    },
]

#: Which benefit each domain reads, and how to say it to a customer.
#:
#: There is no betting rake here because there is no betting. A fee schedule
#: is a product catalogue: a "% rake on winnings" line advertises a book this
#: platform does not run and will not run.
DOMAIN_BENEFIT = {
    "banking":  ("savings_pct_month",     "{v}% a month on savings"),
    "stocks":   ("trade_fee_pct",         "{v}% trading fee"),
    "markets":  ("market_commission_pct", "{v}% commission on a sale"),
    "lands":    ("land_listing_fee_pct",  "{v}% fee to list a parcel"),
    "work":     ("payout_bonus_pct",      "+{v}% on every order you fill"),
}

#: Every domain the ladder pays out in, in nav order.
DOMAINS = tuple(DOMAIN_BENEFIT)


# ── how the two halves combine ──────────────────────────────────────────────
#: Coins held at the bank, expressed as points. 10,000c saved reads as 1,000 points,
#: so a 100,000c balance is worth 10,000 — about the weight of a Veteran's earnings.
POINTS_PER_COIN_SAVED = 0.1

#: Savings may contribute at most this multiple of what you earned. 1.0 means "savings
#: can double your score, never more". Set it higher to let holdings matter more; set it
#: to 0 to make rank purely about contribution.
SAVINGS_MATCH_CAP = 1.0


def score(points=0, savings=0) -> dict:
    """Blend the two halves into one rank score, and show the working.

    The cap is applied to the savings half, never to earnings, so the answer to
    "why am I not Elite?" is always a number the customer can act on.
    """
    try:
        earned = max(0.0, float(points or 0))
    except (TypeError, ValueError):
        earned = 0.0
    try:
        held = max(0.0, float(savings or 0))
    except (TypeError, ValueError):
        held = 0.0
    raw = held * POINTS_PER_COIN_SAVED
    allowed = earned * SAVINGS_MATCH_CAP
    from_savings = min(raw, allowed)
    return {
        "total": earned + from_savings,
        "from_earnings": earned,
        "from_savings": from_savings,
        "savings_uncapped": raw,
        "savings_capped": raw > allowed,
    }


def tier_for(points) -> dict:
    """The tier a point total earns. Never returns None — 0 points is Recruit."""
    try:
        p = float(points or 0)
    except (TypeError, ValueError):
        p = 0.0
    current = TIERS[0]
    for t in TIERS:
        if p >= t["min_points"]:
            current = t
    return current


def next_tier(points) -> dict | None:
    """The next rung up, or None at Elite."""
    try:
        p = float(points or 0)
    except (TypeError, ValueError):
        p = 0.0
    for t in TIERS:
        if t["min_points"] > p:
            return {**t, "points_needed": t["min_points"] - p}
    return None


def benefit(points, domain: str, key: str | None = None):
    """One domain's benefit at this point total."""
    t = tier_for(points)
    if key is None:
        key = DOMAIN_BENEFIT.get(domain, (None, ""))[0]
    return t.get(key) if key else None


def benefits(points) -> dict[str, dict]:
    """Every domain's benefit at once — what a /me or profile screen shows."""
    t = tier_for(points)
    out = {}
    for domain, (key, phrasing) in DOMAIN_BENEFIT.items():
        v = t[key]
        out[domain] = {"key": key, "value": v, "says": phrasing.format(v=v)}
    return out


def summary(points=0, savings=0) -> dict:
    """Rank + every benefit + progress + how the score was earned. One payload for the
    core API, the website panels and the Discord /me."""
    sc = score(points, savings)
    total = sc["total"]
    t = tier_for(total)
    nxt = next_tier(total)
    return {
        "score": total,
        "earned_points": sc["from_earnings"],
        "from_savings": sc["from_savings"],
        "savings_capped": sc["savings_capped"],
        "tier": {k: t[k] for k in ("key", "name", "min_points")},
        "benefits": benefits(total),
        "next_tier": ({"name": nxt["name"], "min_points": nxt["min_points"],
                       "points_needed": nxt["points_needed"]} if nxt else None),
    }


def annual_pct(monthly_pct) -> float:
    """The compounded annual figure for a monthly rate — 0.5%/month is 6.17%/year, not
    6.00%. Shown alongside the monthly rate wherever a customer compares to a loan."""
    r = float(monthly_pct) / 100.0
    return round(((1.0 + r) ** 12 - 1.0) * 100.0, 2)


def ladder() -> list[dict]:
    """The whole table, for the 'how tiers work' screen."""
    return [{"name": t["name"], "min_points": t["min_points"],
             "benefits": {d: t[k] for d, (k, _p) in DOMAIN_BENEFIT.items()}}
            for t in TIERS]
