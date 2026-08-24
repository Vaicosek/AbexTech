"""Abex Stakes — the satellite bot. See `run_bank.py` for why sys.path is set here.

Stakes holds no database of its own: `channels.json` is per-guild config, and
everything else it knows it asks core for. That makes it the cheapest of the three
to move and the first that can drop its HTTP calls for direct ones.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "stakes"))
os.chdir(ROOT)

if __name__ == "__main__":
    import app
    app.main()
