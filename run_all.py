"""Start all three Abex bots inside one container.

Wisp runs a single startup command, but this deployment is three bots. This file is
that one command: it launches `run_core.py`, `run_bank.py` and `run_stakes.py` as
CHILD PROCESSES and supervises them.

## Why child processes and not one event loop

Three separate processes is a deliberate property, not an accident of how they grew
(`run_bank.py` says so in its own docstring): an unhandled exception in Stakes must
not be able to stall core's money loops. Running three `discord.Client`s in one
asyncio loop would put them back in each other's blast radius, and one bad `await`
in the least important bot could freeze the ledger. Separate processes keep the
isolation while still sharing ONE filesystem — which is the whole point of the move,
because it is what lets `bank.db` fold into `restocker.db` and turns `banking_web`'s
HTTP call into a `SELECT`.

## What it does

- Prefixes every child's output with `[core]` / `[bank]` / `[stakes]` so one console
  stays readable, unbuffered so it appears live.
- Restarts a bot that dies, with exponential backoff.
- GIVES UP on a bot that keeps dying fast (default: 5 failures inside 60s) instead of
  spinning forever — a missing token fails instantly and would otherwise flood the
  console. The other bots keep running.
- Forwards SIGTERM/SIGINT to the children so a panel Stop closes Discord connections
  cleanly rather than leaving them to time out.

## Panel settings

    APP PY FILE      run_all.py
    REQUIREMENTS     requirements.txt   (root; it is a superset of bank's and stakes')

## Env knobs (all optional)

    RUN_ALL_BOTS            core,bank,stakes   which to start — drop one until it is
                                               configured, e.g. "core,bank"
    RUN_ALL_MAX_RESTARTS    5                  rapid failures before giving up on a bot
    RUN_ALL_RESTART_WINDOW  60                 seconds that counts as "rapid"
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

BOTS = {
    "core":   "run_core.py",
    "bank":   "run_bank.py",
    "stakes": "run_stakes.py",
}


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


WANTED = [b.strip().lower() for b in _env("RUN_ALL_BOTS", "core,bank,stakes").split(",") if b.strip()]
MAX_RESTARTS = max(1, int(_env("RUN_ALL_MAX_RESTARTS", "5") or "5"))
WINDOW = max(5.0, float(_env("RUN_ALL_RESTART_WINDOW", "60") or "60"))

_unknown = [b for b in WANTED if b not in BOTS]
if _unknown:
    raise SystemExit(f"RUN_ALL_BOTS names an unknown bot: {', '.join(_unknown)}. "
                     f"Valid: {', '.join(BOTS)}")
if not WANTED:
    raise SystemExit("RUN_ALL_BOTS is empty — nothing to start.")

_stopping = threading.Event()
_procs: dict[str, subprocess.Popen] = {}
_gave_up: set[str] = set()
_lock = threading.Lock()


def say(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


def _pump(tag: str, stream) -> None:
    """Forward one child's output, line by line, prefixed."""
    try:
        for raw in iter(stream.readline, b""):
            print(f"[{tag}] {raw.decode('utf-8', 'replace').rstrip()}", flush=True)
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _supervise(name: str) -> None:
    script = BOTS[name]
    if not (ROOT / script).is_file():
        say(name, f"{script} not found — skipping this bot")
        _gave_up.add(name)
        return

    fails: list[float] = []
    while not _stopping.is_set():
        say(name, f"starting {script}")
        started = time.monotonic()
        try:
            # -u and PYTHONUNBUFFERED both, so output is live even if one is ignored.
            p = subprocess.Popen(
                [sys.executable, "-u", script],
                cwd=str(ROOT),
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except Exception as e:
            say(name, f"could not start: {e}")
            _gave_up.add(name)
            return

        with _lock:
            _procs[name] = p
        pump = threading.Thread(target=_pump, args=(name, p.stdout), daemon=True)
        pump.start()

        code = p.wait()
        pump.join(timeout=5)
        with _lock:
            _procs.pop(name, None)

        if _stopping.is_set():
            say(name, f"stopped (exit {code})")
            return

        ran = time.monotonic() - started
        say(name, f"exited with code {code} after {ran:.0f}s")

        now = time.monotonic()
        fails = [t for t in fails if now - t < WINDOW]
        if ran < WINDOW:
            fails.append(now)

        if len(fails) >= MAX_RESTARTS:
            say(name, f"GIVING UP — {len(fails)} failures inside {WINDOW:.0f}s. "
                      f"This is almost always missing config, not a crash loop worth "
                      f"retrying. Fix it and restart the server; the other bots keep "
                      f"running.")
            _gave_up.add(name)
            return

        delay = min(30, 2 ** len(fails))
        say(name, f"restarting in {delay}s")
        _stopping.wait(delay)


def _shutdown(signum, _frame) -> None:
    if _stopping.is_set():
        return
    _stopping.set()
    say("run_all", f"signal {signum} — stopping {len(_procs)} bot(s)")
    with _lock:
        children = list(_procs.items())
    for name, p in children:
        try:
            p.terminate()
        except Exception:
            pass
    deadline = time.monotonic() + 15
    for name, p in children:
        try:
            p.wait(timeout=max(0, deadline - time.monotonic()))
        except Exception:
            say(name, "did not stop in time — killing")
            try:
                p.kill()
            except Exception:
                pass


def main() -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _shutdown)
        except (ValueError, OSError, AttributeError):
            pass  # not available on this platform / not the main thread

    say("run_all", f"starting: {', '.join(WANTED)}  (python {sys.version.split()[0]})")
    threads = [threading.Thread(target=_supervise, args=(n,), name=n, daemon=True)
               for n in WANTED]
    for t in threads:
        t.start()

    try:
        while any(t.is_alive() for t in threads):
            for t in threads:
                t.join(timeout=1)
    except KeyboardInterrupt:
        _shutdown(signal.SIGINT, None)
        for t in threads:
            t.join(timeout=20)

    if _stopping.is_set():
        say("run_all", "all bots stopped")
        return

    alive = [n for n in WANTED if n not in _gave_up]
    if not alive:
        say("run_all", "every bot gave up — see the reasons above")
        raise SystemExit(1)
    if "core" in _gave_up:
        say("run_all", "core gave up; bank and stakes depend on it, so stopping too")
        _shutdown(signal.SIGTERM, None)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
