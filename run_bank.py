"""Abex Bank — one of the three bots this repo runs.

Three bots, three Discord servers, three tokens, one checkout. They are separate
PROCESSES on purpose: an unhandled exception in Stakes must not be able to stall
core's money loops, and each keeps its own restart button on the panel.

## Why this file sets sys.path instead of using packages

`bank/` keeps its own flat imports — `import bank_db`, `from bank_main import
main` — exactly as they were written, and it also reaches up for `abex_embed`,
the house embed builder shared with core. Two directories therefore have to be
importable: the repo root for the shared modules, and `bank/` for the bot's own.

Rewriting those imports into a package would mean touching core too, and core has
1,472 internal import statements using flat module names (`import Restocker_db`
alone appears 1,094 times). That rewrite is worth doing on a quiet day, as its own
change with its own test run. It is not worth doing in the same commit that moves
three repos onto one box.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))            # shared: abex_embed, and core modules
sys.path.insert(0, str(ROOT / "bank"))   # the bank's own flat modules

# The bot writes relative paths (bank.db, .env) — anchor them to the repo root so
# it does not matter which directory the panel starts the process from.
os.chdir(ROOT)

if __name__ == "__main__":
    from bank_main import main
    main()
