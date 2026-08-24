"""
abex_data.py — the mockup's own content, ported verbatim.

These are the exact strings and figures from OverhaulALedger.dc.html. They stay here as
the reference dataset so a screen can be built and eyeballed against the design before it
is wired to the live database. Swap each list for a real query when the screen ships;
the SHAPES are the contract the templates were designed against.
"""
from __future__ import annotations

from abex_theme import DOMAINS, GAIN, LOSS

TEXT, DIM, FAINT = "#F4F4F4", "#B4B4B4", "#6A6A6A"

#: Sticky-header summary — label, value, colour.
# Money direction only. A section hue on a figure said "this number belongs to
# Banking", which is not a fact about the money and reads as a fourth meaning for
# colour. Gain for money that is yours and growing, dim for money that is parked.
SUMMARY = [
    ("Available",   "84,230c",  GAIN),
    ("Held",        "12,400c",  DIM),
    ("Savings",     "156,900c", DIM),
    ("Holdings",    "21,084c",  GAIN),
    ("Owed to you", "2,850c",   GAIN),
]

#: Hub stat band.
HUB_TILES = [
    ("Index",       "1,284.6", "+2.1% this cycle",        GAIN),
    ("Dividends",   "214.60c", "228c estimated next",     TEXT),
    ("Holdings",    "21,084c", "+3,846c unrealised",      GAIN),
    ("Next report", "BNL",     "Tue 25 Aug, then GreyHames Sat 29 Aug", TEXT),
]

#: ticker, name, owner, grade, backing, last net, index weight, next report
MARKETS = [
    ("GREY", "GreyHames",         "xXGreyHamesXx",   "AAA", "1.70×", "42,180c", "14.2%", "Sat 29 Aug"),
    ("AMAZ", "Amazonia",          "Amazonia_Co",     "AA",  "1.28×", "31,050c", "11.6%", "Wed 26 Aug"),
    ("SANC", "Sancta",            "Sancta_Order",    "AA",  "1.24×", "27,600c", "10.4%", "Thu 3 Sep"),
    ("BNL",  "BNL",               "BNL_Holdings",    "A",   "1.02×", "18,400c", "7.1%",  "Tue 25 Aug"),
    ("NAUT", "NauticalMarket",    "Nautica",         "A",   "1.08×", "15,220c", "6.4%",  "Sun 6 Sep"),
    ("NETH", "Nether market",     "Netherite_Guild", "A",   "1.05×", "16,700c", "6.8%",  "Tue 1 Sep"),
    ("TOOL", "Toolshop",          "Toolsmith",       "BBB", "0.71×", "9,260c",  "3.4%",  "Mon 31 Aug"),
    ("VIRI", "ViridianMarket",    "Viridian",        "BBB", "0.64×", "8,940c",  "3.1%",  "Fri 4 Sep"),
    ("GOBL", "Goblin Mart",       "Goblin_King",     "BBB", "0.66×", "7,410c",  "2.8%",  "Fri 28 Aug"),
    ("FALR", "Falrija",           "Falrija_Co",      "BB",  "0.38×", "5,120c",  "1.4%",  "Sun 30 Aug"),
    ("INVI", "Invictus-emporium", "Invictus",        "BB",  "0.34×", "4,300c",  "1.1%",  "Wed 2 Sep"),
    ("FREE", "Freezone",          "Freezone",        "BB",  "0.31×", "3,960c",  "1.0%",  "Thu 27 Aug"),
    ("GENE", "GeneralStore",      "GeneralStore",    "C",   "0.12×", "1,870c",  "0.3%",  "Sat 5 Sep"),
]

#: item, qty, pay, market, window, window colour
# Real durations and the unit spelled out. "31m" and "42c / stack" are the two
# shorthands the copy rules ban by name.
WORK = [
    ("Iron ingot", "8 stacks",   "42c per stack",  "Toolshop",       "Employees only, 31 minutes left", LOSS),
    ("Glass pane", "320 pieces", "1.4c per piece", "ViridianMarket", "Open to all",                     FAINT),
    ("Blaze rod",  "2 stacks",   "180c per stack", "Nether market",  "Employees only, 8 minutes left",  LOSS),
]

#: grade, what it requires
GRADE_LEGEND = [
    ("AAA", "1.6× backed"), ("AA", "1.2×"), ("A", "fully backed"),
    ("BBB", "0.6×"), ("BB", "0.3×"), ("C", "under 0.3×"),
]


# ── Exchange ────────────────────────────────────────────────────────────────
EXCHANGE_TILES = [
    ("Markets listed",     "13",       "9 investment grade",           TEXT),
    ("Shares outstanding", "31,400",   "across all markets",           TEXT),
    ("Holders",            "186",      "42 hold more than one market", TEXT),
    ("Index",              "1,284.6",  "+2.1% this cycle",             GAIN),
]
#: ticker, name, grade, shares out, holders, price, free float
EXCHANGE = [
    ("GREY", "GreyHames",      "AAA", "3,000", "18", "11.20c", "42%"),
    ("AMAZ", "Amazonia",       "AA",  "4,000", "21", "6.35c",  "55%"),
    ("SANC", "Sancta",         "AA",  "3,200", "16", "9.10c",  "38%"),
    ("BNL",  "BNL",            "A",   "2,400", "12", "4.05c",  "61%"),
    ("NAUT", "NauticalMarket", "A",   "2,000", "9",  "7.40c",  "29%"),
    ("NETH", "Nether market",  "A",   "2,600", "14", "13.90c", "44%"),
    ("TOOL", "Toolshop",       "BBB", "1,800", "8",  "3.10c",  "33%"),
    ("VIRI", "ViridianMarket", "BBB", "1,600", "7",  "2.85c",  "48%"),
]

# ── Stocks ──────────────────────────────────────────────────────────────────
#: ticker, name, grade, shares, avg cost, price, value, P/L, up?, dividend, next
HOLDINGS = [
    ("GREY", "GreyHames",     "AAA", "420",   "8.40",  "11.20", "4,704.00", "+1,176.00", True,  "58.80c", "Sat 29 Aug"),
    ("AMAZ", "Amazonia",      "AA",  "1,200", "5.10",  "6.35",  "7,620.00", "+1,500.00", True,  "96.00c", "Wed 26 Aug"),
    ("SANC", "Sancta",        "AA",  "600",   "7.25",  "9.10",  "5,460.00", "+1,110.00", True,  "41.40c", "Thu 3 Sep"),
    ("NETH", "Nether market", "A",   "150",   "12.00", "13.90", "2,085.00", "+285.00",   True,  "12.10c", "Tue 1 Sep"),
    ("BNL",  "BNL",           "A",   "300",   "4.80",  "4.05",  "1,215.00", "-225.00",   False, "6.30c",  "Tue 25 Aug"),
]
PRICE_FORMULA = [
    ("Trailing net, mean of three reports", "42,180c",       TEXT),
    ("Growth P/E multiple",                 "6.4×",          TEXT),
    ("Implied equity",                      "269,952c",      TEXT),
    ("Shares outstanding",                  "24,100",        TEXT),
    ("Book value floor",                    "1.71c / share", DIM),
    ("Settled price",                       "11.20c / share", DOMAINS["stocks"]),
]

# ── Banking ─────────────────────────────────────────────────────────────────
BANK_TILES = [
    ("Available",   "84,230c",  "spendable right now",        DOMAINS["banking"]),
    ("Held",        "12,400c",  "one bid, one lease deposit", DIM),
    ("Savings",     "156,900c", "earning 0.8% a month",       DOMAINS["banking"]),
    ("Owed to you", "2,850c",   "GEX absorption, unpaid",     DOMAINS["banking"]),
]
BORROW = [
    ("Shares you hold",     "21,084c", TEXT),
    ("Land you hold",       "8,400c",  TEXT),
    ("Lending limit, 60%",  "17,690c", TEXT),
    ("Already borrowed",    "−9,400c", "#FF4D4D"),
    ("You can borrow",      "8,290c",  GAIN),
]
#: NOTE — the mockup's banking tiers (Gold/Silver/Bronze/Watch, keyed on savings balance)
#: are a DESIGN invention. The live code has no such thing: its tiers are Recruit, Worker,
#: Veteran, Expert, Elite, keyed on loyalty points, and they set the SAVINGS rate, not the
#: loan rate. Ported verbatim so the screen matches the approved design — decide which
#: model is real before this screen is wired to the database.
TIERS = [
    # The real network ladder (see abex_tiers.py). Savings rates are PER MONTH; the live
    # server rate is 0.5%/month and Recruit sits exactly there, so nobody loses out.
    ("Recruit", "0.50% / mo", "the base rate, everyone starts here",   FAINT),
    ("Worker",  "0.60% / mo", "1,000 points",                          DIM),
    ("Veteran", "0.80% / mo", "you are here \u00b7 5,000 points",     DOMAINS["banking"]),
    ("Expert",  "1.10% / mo", "15,000 points",                         DIM),
    ("Elite",   "1.50% / mo", "40,000 points",                         DIM),
]
BOND_TILES = [
    ("Face held",          "18,000c", "3 bonds",             TEXT),
    ("Coupons this cycle", "1,164c",  "paid before dividends", GAIN),
]
#: ticker, issuer, term, face, coupon, paid so far, matures
BONDS_HELD = [
    ("GREY", "GreyHames",      "6 cycles",  "6,000c", "5.2%", "936c", "in 2 cycles"),
    ("ATB",  "Abex Tech Bank", "12 cycles", "8,000c", "4.0%", "960c", "in 7 cycles"),
    ("AMAZ", "Amazonia",       "6 cycles",  "4,000c", "6.5%", "520c", "in 4 cycles"),
]
#: ticker, issuer, grade, term, coupon, left to fill, what backs it
BONDS_OFFERED = [
    ("NETH", "Nether market",  "A",   "6 cycles",  "7.0%", "9,400c",    "stock and the shopfront deed"),
    ("SANC", "Sancta",         "AA",  "12 cycles", "4.8%", "22,000c",   "net, 1.9× covered"),
    ("TOOL", "Toolshop",       "BBB", "6 cycles",  "9.5%", "3,200c",    "stock only"),
    ("ATB",  "Abex Tech Bank", "AAA", "12 cycles", "3.6%", "unlimited", "the bank itself"),
]

# ── Work / Orders ───────────────────────────────────────────────────────────
#: item, market, owner, qty, qty detail, unit price, unit, total, points, priority?, left
ORDERS = [
    ("Iron ingot",    "Toolshop",       "Toolsmith",       "8 stacks",   "of 64 · 512 pieces", "42c",  "per stack of 64", "336c", "40", True,  "31m left"),
    ("Glass pane",    "ViridianMarket", "Viridian",        "320 pieces", "five stacks",        "1.4c", "per piece",       "448c", "35", False, ""),
    ("Blaze rod",     "Nether market",  "Netherite_Guild", "2 stacks",   "of 64 · 128 pieces", "180c", "per stack of 64", "360c", "60", True,  "8m left"),
    ("Oak log",       "GreyHames",      "xXGreyHamesXx",   "12 stacks",  "of 64 · 768 pieces", "18c",  "per stack of 64", "216c", "25", False, ""),
    ("Redstone dust", "BNL",            "BNL_Holdings",    "640 pieces", "ten stacks",         "0.9c", "per piece",       "576c", "45", True,  "44m left"),
    ("Kelp block",    "NauticalMarket", "Nautica",         "6 stacks",   "of 64 · 384 pieces", "22c",  "per stack of 64", "132c", "20", False, ""),
]

# ── Lands ───────────────────────────────────────────────────────────────────
#: name, owner, tenant, rent, state, term
PARCELS = [
    ("Millbrook 7",  "Yours",              "Steve_Forge",     "120c / week", "Leased",   "Renews in 12 days"),
    ("Northgate 14", "Northwind Co-op",    "Abex Tech",       "400c / week", "Expiring", "Ends in 3 days"),
    ("Riverside 2",  "xXGreyHamesXx",      "—",               "—",           "Vacant",   "Listed for lease"),
    ("Southfen 3",   "Millbrook Holdings", "Ironforge Guild", "250c / week", "Leased",   "Renews in 26 days"),
]

# ── Betting ─────────────────────────────────────────────────────────────────
#: title, closes, your stake, foot, [(outcome, pool, odds, share)]
BETS = [
    ("Will GreyHames file above 45,000c net?", "closes on filing",
     "You staked 400c on No", "Pool 4,820c · odds last moved 6m ago",
     [("Yes", "2,600", "1.85×", "54%"), ("No", "2,220", "2.17×", "46%")]),
    ("Which market gets downgraded first?", "closes in 6d",
     "No stake yet", "Pool 3,140c · odds last moved 41m ago",
     [("GeneralStore", "1,940", "1.42×", "62%"), ("Freezone", "760", "3.60×", "24%"),
      ("Invictus-emporium", "440", "6.20×", "14%")]),
    ("Does Toolshop reach A grade this cycle?", "suspended",
     "You staked 150c on Yes",
     "Toolshop's report is landing. Stakes reopen once the figures are in.",
     [("Yes", "1,120", "2.90×", "34%"), ("No", "2,180", "1.49×", "66%")]),
]

# ── Investor (GEX.PR preferred) ─────────────────────────────────────────────
POOL = [
    ("GREY", "GreyHames",         "42,180c", "23.2%"),
    ("AMAZ", "Amazonia",          "31,050c", "17.1%"),
    ("SANC", "Sancta",            "27,600c", "15.2%"),
    ("BNL",  "BNL",               "18,400c", "10.1%"),
    ("—",    "Nine other markets", "62,810c", "34.4%"),
]

# ── Earnings reports ────────────────────────────────────────────────────────
#: ticker, name, month, net, per share, dividend, grade after, missed?
FILINGS = [
    ("GREY", "GreyHames",      "July", "42,180c", "14.06c", "13.94c", "AAA", False),
    ("NETH", "Nether market",  "July", "28,940c", "11.13c", "10.90c", "A",   False),
    ("AMAZ", "Amazonia",       "July", "31,050c", "7.76c",  "7.44c",  "AA",  False),
    ("SANC", "Sancta",         "July", "24,600c", "7.69c",  "7.30c",  "AA",  False),
    ("BNL",  "BNL",            "July", "9,180c",  "3.83c",  "3.60c",  "A",   False),
    ("TOOL", "Toolshop",       "July", "-1,240c", "—",      "none",   "BBB", True),
    ("VIRI", "ViridianMarket", "June", "4,320c",  "2.70c",  "2.48c",  "BBB", False),
    ("GREY", "GreyHames",      "June", "40,200c", "13.40c", "13.28c", "AAA", False),
]
