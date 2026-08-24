"""Abex Tech core — the market, the money and the website.

Kept byte-for-byte equivalent to the old top-level `main.py` (seed hook, then
`runpy` into `Restocker_main`) so the migration changes where the code lives and
nothing about how it starts. `main.py` stays next to this file as an alias, because
the Pterodactyl/Wisp startup command on the running server still names it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

if __name__ == "__main__":
    try:
        import seed_items
        seed_items.main()
    except Exception as _seed_err:          # a failed seed must not block boot
        print("[seed] startup hook failed:", _seed_err)
    import runpy
    runpy.run_path(str(ROOT / "Restocker_main.py"), run_name="__main__")
