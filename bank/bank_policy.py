"""The bank's money POLICY, in one place, importable without starting a bot.

Why this module exists
----------------------
`banking_web.py` states the rule it lives by:

    `schedule`, `ladder`, `limit.components` and `interest_at_maturity` are
    COMPUTED BY THE BANK and rendered verbatim. This module does not re-derive a
    repayment schedule or a credit limit from the terms. Two implementations of one
    policy is how a FAQ says 7.5% while the embed says 10%.

That rule was easy to honour while the website reached the bank over HTTP: there was
only ever one implementation, and the website asked it. Now that both run in one
process against one database, the website could just as easily recompute a credit
limit itself from `bank_loans` -- and that is precisely the second implementation the
rule forbids.

So the policy moves HERE, and both sides import it. `bank_main` keeps its names by
importing them back, so every existing call site is untouched.

Why not simply `import bank_main` from the website
--------------------------------------------------
Importing `bank_main` runs its module body, which calls `logging.basicConfig()` and
constructs a `commands.Bot`. Core's web process would gain a second Discord bot object
and have its logging reconfigured underneath it, as a side effect of rendering a page.
This module imports `os` and `bank_db` and nothing else.
"""
from __future__ import annotations

import logging
import os

import bank_db as bdb

log = logging.getLogger("bank.policy")


# ── Savings and loans ────────────────────────────────────────────────────────
#: PER MONTH, not per year. The live rate is 0.5%/month (6.17% a year compounded).
#: Annualising this by x12 or x52 is a recurring mis-read; the column that IS
#: mislabelled is `interest_weekly_pct` in core's LOYALTY_TIERS, not this one.
SAVINGS_APR = float(os.getenv("SAVINGS_APR", "0.05"))
LOAN_APR = float(os.getenv("LOAN_APR", "0.18"))
LOAN_OVERDUE_EXTRA_APR = float(os.getenv("LOAN_OVERDUE_EXTRA_APR", "0.18"))
MAX_LOAN = int(os.getenv("MAX_LOAN", "100000"))
DEFAULT_LOAN_DAYS = int(os.getenv("DEFAULT_LOAN_DAYS", "30"))

# ── Credit limit ─────────────────────────────────────────────────────────────
# base + (per-repaid-loan bonus x clean repayments) - (penalty x late), capped at
# MAX_LOAN. A per-user override in bank_accounts.credit_limit beats all of it.
BASE_CREDIT_LIMIT = int(os.getenv("BASE_CREDIT_LIMIT", "10000"))
CREDIT_PER_REPAID_LOAN = int(os.getenv("CREDIT_PER_REPAID_LOAN", "5000"))
CREDIT_LATE_PENALTY = int(os.getenv("CREDIT_LATE_PENALTY", "5000"))


def parse_bond_terms(raw: str) -> dict[int, float]:
    """Parse BOND_TERMS='7:0.06,30:0.09,90:0.14' -> {7:0.06, 30:0.09, 90:0.14}."""
    out: dict[int, float] = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            d, r = part.split(":")
            out[int(d.strip())] = float(r.strip())
        except ValueError:
            log.warning("Ignoring malformed BOND_TERMS entry: %r", part)
    return dict(sorted(out.items()))


BOND_TERMS = parse_bond_terms(os.getenv("BOND_TERMS", "7:0.06,30:0.09,90:0.14"))
BOND_EARLY_PENALTY_PCT = float(os.getenv("BOND_EARLY_PENALTY_PCT", "0.0"))


def bond_payout(principal: int, apr: float, term_days: int) -> int:
    """Fixed simple-interest payout at maturity, rounded to whole coins."""
    return int(round(principal * (1.0 + apr * term_days / 365.0)))


def credit_limit_for(user_id) -> int:
    """How much total debt this user is allowed to carry.

    A per-user override (set by /admin creditlimit) wins outright. Otherwise it
    grows with a clean repayment record and shrinks for every loan that went
    overdue -- so the limit is earned rather than flat."""
    acct = bdb.get_account(user_id) or {}
    override = acct.get("credit_limit")
    if override is not None:
        return max(0, int(override))
    h = bdb.loan_history(user_id)
    limit = (BASE_CREDIT_LIMIT
             + CREDIT_PER_REPAID_LOAN * h["repaid_count"]
             - CREDIT_LATE_PENALTY * h["late_count"])
    if h["written_off_count"]:
        # A written-off loan means the bank ate a loss on this person.
        limit = 0
    return max(0, min(limit, MAX_LOAN))


def credit_limit_components(user_id) -> list[tuple[str, int]]:
    """The same limit, itemised, for `limit.components` on the website.

    INVARIANT: these rows always sum to exactly what `credit_limit_for` returns.
    The labels exist to explain the number; a breakdown that adds up to something
    else is worse than no breakdown, because the reader trusts the arithmetic they
    can see over the total they cannot check. Both edge cases are therefore rows in
    their own right rather than silent clamps:

      - a written-off loan zeroes the limit outright, so it is the ONLY row;
      - MAX_LOAN capping is shown as an explicit negative row, not applied quietly.
    """
    limit = credit_limit_for(user_id)
    acct = bdb.get_account(user_id) or {}
    override = acct.get("credit_limit")
    if override is not None:
        return [("Set by a Lead Banker", limit)]

    h = bdb.loan_history(user_id)
    if h["written_off_count"]:
        return [("A loan was written off — borrowing suspended", 0)]

    rows: list[tuple[str, int]] = [("Base limit", BASE_CREDIT_LIMIT)]
    if h["repaid_count"]:
        rows.append((f"{h['repaid_count']} loan(s) repaid",
                     CREDIT_PER_REPAID_LOAN * h["repaid_count"]))
    if h["late_count"]:
        rows.append((f"{h['late_count']} loan(s) went overdue",
                     -CREDIT_LATE_PENALTY * h["late_count"]))

    running = sum(v for _, v in rows)
    if running != limit:
        # Only two things can move it: the MAX_LOAN ceiling, or the floor at zero.
        label = (f"Capped at the {MAX_LOAN:,} maximum" if limit >= running
                 else f"Capped at the {MAX_LOAN:,} maximum")
        if limit == 0 and running < 0:
            label = "Floored at zero"
        rows.append((label, limit - running))
    return rows
