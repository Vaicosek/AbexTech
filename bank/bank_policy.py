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
import math
import os
from datetime import datetime, timedelta, timezone

import bank_db as bdb

log = logging.getLogger("bank.policy")


def _env_bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


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


# ── Collections ──────────────────────────────────────────────────────────────
# These four lived in `bank_main` and were read only by the bot, which is why the
# website's staff-collections page had to re-read COLLECT_FROM_SAVINGS out of the
# environment itself (`bank_local._staff_collections`) to decide whether savings
# were reachable. That was a second implementation of a policy question, and the
# two could disagree the moment either spelling of the env var changed. They live
# here now; `bank_main` imports them back under the same names.
COLLECT_FROM_SAVINGS = _env_bool("COLLECT_FROM_SAVINGS", "1")
COLLECT_GRACE_DAYS = float(os.getenv("COLLECT_GRACE_DAYS", "3"))
GARNISH_BOND_PAYOUTS = _env_bool("GARNISH_BOND_PAYOUTS", "1")
OVERDUE_ANNOUNCE = _env_bool("OVERDUE_ANNOUNCE", "1")


#: WHICH DEBT IS SETTLED FIRST, said once, for every path that settles debt.
#:
#: Oldest DUE first. A borrower with several loans has the one that has been
#: overdue longest settled first, whether the coins arrive as a voluntary
#: repayment, as a garnished bond payout, or as a savings seizure. `id ASC`
#: breaks ties so two loans due the same second settle in a stable order, and
#: `due_at IS NULL` sorts last because a loan with no due date can never be the
#: most overdue one.
#:
#: This used to be two rules: `bdb.overdue_loans` ordered by `due_at` (used by
#: garnishment and by the collections pass) while `bdb.get_active_loans` ordered
#: by `issued_at` (used by /loan repay). Two orders for one question, so the same
#: 500c settled different loans depending on how it was paid -- which changes
#: which loan goes overdue next, and `overdue_notified` is a permanent black mark
#: on the credit limit. One order, here, imported by both sides.
SETTLEMENT_ORDER_SQL = "due_at IS NULL, due_at ASC, id ASC"


def collection_grace_cutoff(now_iso: str) -> str:
    """A loan due AFTER this instant is still inside its grace period."""
    try:
        now = datetime.fromisoformat(str(now_iso).replace("Z", "+00:00"))
    except ValueError:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - timedelta(days=COLLECT_GRACE_DAYS)).isoformat()


#: Why a collection took nothing. `savings_collectable` returns one of these, and
#: the staff page turns it into a sentence -- so "nothing happened" always names
#: its reason instead of reporting a silent zero.
COLLECT_REASONS = {
    "collection_off": "Collection from savings is switched off (COLLECT_FROM_SAVINGS=0).",
    "in_grace": "That loan is still inside its grace period.",
    "no_savings": "There is nothing in that borrower's savings to take.",
    "settled": "That loan has nothing left owing.",
    "below_one_coin": "Less than one whole coin is reachable, and the bank rounds "
                      "down in the borrower's favour.",
}


def savings_collectable(owed: float, savings: float, due_at: str | None,
                        now_iso: str, cap: int | None = None) -> tuple[int, str]:
    """How many coins may be taken from savings against this loan, and why not.

    THE ONE PLACE that answers "is this debt reachable, and how much of it".
    The hourly pass and the staff page both ask it, so a Lead Banker's screen can
    never offer a collection the automatic pass would refuse to make.

    What it encodes, all of it deliberate:
      - savings only. The wallet, escrow holds, stock and land are out of reach;
        that is the bank's promise and it is enforced by never being asked for.
      - COLLECT_GRACE_DAYS of grace past `due_at`, savings-side ONLY. A bond
        payout is garnished the moment it is redeemed, with no grace, because
        those coins are passing through the bank's own hands.
      - `math.floor`, so a fraction of a coin is never rounded up into a seizure.
        Rounding always favours the borrower.
      - `cap` is the staff page naming an amount. It can only ever reduce.
    """
    if not COLLECT_FROM_SAVINGS:
        return 0, "collection_off"
    if float(owed) <= 0:
        return 0, "settled"
    if (due_at or "") > collection_grace_cutoff(now_iso):
        return 0, "in_grace"
    if float(savings) <= 0:
        return 0, "no_savings"
    take = int(math.floor(min(float(owed), float(savings))))
    if cap is not None:
        take = min(take, int(cap))
    if take < 1:
        return 0, "below_one_coin"
    return take, ""


def bond_payout(principal: int, apr: float, term_days: int) -> int:
    """Fixed simple-interest payout at maturity, rounded to whole coins."""
    return int(round(principal * (1.0 + apr * term_days / 365.0)))


def credit_limit_from(account: dict | None, history: dict) -> int:
    """The limit arithmetic, on figures the caller already read. No I/O.

    Split out from `credit_limit_for` for one reason: a loan approval has to
    re-check the limit INSIDE its money transaction, and every `bdb` helper opens
    its own connection -- which inside a `BEGIN IMMEDIATE` would sit outside the
    transaction and then block on the write lock that transaction is holding.
    So the caller reads `bank_accounts` and the loan history on ITS connection
    and hands them here. `credit_limit_for` keeps its signature and calls this,
    so there is still one implementation of the arithmetic and not two.
    """
    acct = account or {}
    override = acct.get("credit_limit")
    if override is not None:
        return max(0, int(override))
    limit = (BASE_CREDIT_LIMIT
             + CREDIT_PER_REPAID_LOAN * history["repaid_count"]
             - CREDIT_LATE_PENALTY * history["late_count"])
    if history["written_off_count"]:
        # A written-off loan means the bank ate a loss on this person.
        limit = 0
    return max(0, min(limit, MAX_LOAN))


def credit_limit_for(user_id) -> int:
    """How much total debt this user is allowed to carry.

    A per-user override (set by /admin creditlimit) wins outright. Otherwise it
    grows with a clean repayment record and shrinks for every loan that went
    overdue -- so the limit is earned rather than flat."""
    return credit_limit_from(bdb.get_account(user_id) or {}, bdb.loan_history(user_id))


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
    acct = bdb.get_account(user_id) or {}
    h = bdb.loan_history(user_id)
    return credit_limit_components_from(acct, h)


def credit_limit_components_from(account: dict | None,
                                 history: dict) -> list[tuple[str, int]]:
    """`credit_limit_components` on figures already read. Same invariant.

    Both breakdown and total now come from ONE arithmetic (`credit_limit_from`)
    over ONE pair of reads. Before, the total was read three times -- three
    connections, three moments -- so a loan reaching 'paid' between the first and
    the second was enough for the rows to stop summing to the total, which is the
    one thing this function promises.
    """
    acct = account or {}
    h = history
    limit = credit_limit_from(acct, h)
    override = acct.get("credit_limit")
    if override is not None:
        return [("Set by a Lead Banker", limit)]

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


def bond_redeem_value(bond: dict, now_iso: str | None = None) -> dict:
    """What redeeming this bond RIGHT NOW pays, and what redeeming it early costs.

    Interest on a bond is all-or-nothing at maturity: redeem early and you get your
    principal back minus BOND_EARLY_PENALTY_PCT, and the interest is forfeited
    entirely. So `earned_so_far` is 0 before maturity BY POLICY, not by rounding --
    a website showing a pro-rata "earned so far" on a bond that pays nothing extra
    until it matures would be promising money the bank will not hand over.

    `interest_at_maturity` comes off the STORED payout, which `bond_payout` computed
    when the bond was sold. It is never recomputed from the current rate table: the
    rate a bond was bought at is the rate it pays, whatever BOND_TERMS says today.
    """
    if now_iso is None:
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
    principal = int(round(bond["principal"]))
    payout = int(round(bond["payout"]))
    matured = now_iso >= bond["matures_at"]
    if matured:
        return {"matured": True, "amount": payout, "penalty": 0,
                "interest_at_maturity": payout - principal,
                "earned_so_far": payout - principal}
    penalty = int(round(principal * BOND_EARLY_PENALTY_PCT))
    return {"matured": False, "amount": max(0, principal - penalty), "penalty": penalty,
            "interest_at_maturity": payout - principal, "earned_so_far": 0}
