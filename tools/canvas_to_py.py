"""tools/canvas_to_py.py — regenerate `abex_canvas.py` from a Claude Design export.

    python tools/canvas_to_py.py "Abex Tech Screens.dc.html" abex_canvas.py

The canvas is a single HTML file with the screen set as a JavaScript object
literal inside a `screens()` method. That literal is DATA — no calls, no
references — but it is not JSON: keys are bare, strings are single-quoted, and
there are trailing commas. Rather than write a tolerant JS parser (and get the
edge cases wrong quietly), this hands the literal to `node` and takes the JSON
back. Node is the only thing that agrees with the canvas about what the canvas
means.

Requires `node` on PATH. If it is missing the script says so and changes
nothing, rather than falling back to a regex that half-works.
"""
from __future__ import annotations

import json
import pprint
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

#: The design has a Betting screen. The product does not do betting, so it is
#: dropped HERE, at the boundary, rather than carried into the codebase and
#: commented out. A screen that must never render should not exist to render.
DROP = {"betting"}

HEADER = '''"""abex_canvas.py — the design's screens, as data. GENERATED, do not hand-edit.

Extracted verbatim from the Claude Design canvas, which encodes every screen the
way the spec describes it in §4:

    screen = {d, title, asof, band?, band3?, blocks[], dock?}
    block  = {h2, ac?, own?} + one of
             table   : c[headers], r[rows], n?(note), lk?(link)
             balance : bal[[label, value, note]], tot?(ruled total row)
             action  : act(sentence), btns[[label, 'p'|'s'|'d']]

Regenerate with `python tools/canvas_to_py.py <canvas.dc.html> abex_canvas.py`.

The ROWS are the design's sample data, on purpose: each screen is swapped to
live queries one at a time, and until then its SHAPE is still right — columns,
tone rules and copy all correct.

Tone tags on a cell (`g|`, `l|`, `w|`, `m|`, `k|`) mean gain / loss / warn /
faint / action; `G|` on a grade cell asks for the grade ramp.
"""
from __future__ import annotations

'''


def _literal(html: str) -> str:
    """The `screens()` object literal, by brace matching that respects quotes."""
    i = html.find("this._s = {")
    if i < 0:
        raise SystemExit("no `this._s = {` in that file — is it a screens canvas?")
    start = html.index("{", i + len("this._s ="))
    depth = 0
    quote = None
    esc = False
    j = start
    while j < len(html):
        ch = html[j]
        if quote:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return html[start:j + 1]
        j += 1
    raise SystemExit("unbalanced braces in the screens literal")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    if not shutil.which("node"):
        print("node is not on PATH — refusing to guess at the JS with regexes.")
        return 1
    src, dest = Path(argv[1]), Path(argv[2])
    lit = _literal(src.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        mod = Path(tmp) / "screens.js"
        mod.write_text("module.exports = " + lit + ";\n", encoding="utf-8")
        out = subprocess.run(
            ["node", "-e", f"process.stdout.write(JSON.stringify(require({str(mod)!r})))"],
            capture_output=True, text=True)
        if out.returncode:
            print(out.stderr.strip() or "node failed to read the literal")
            return 1
        data = json.loads(out.stdout)
    for k in DROP:
        data.pop(k, None)
    dest.write_text(HEADER + "SCREENS: dict[str, dict] = "
                    + pprint.pformat(data, width=100, sort_dicts=False) + "\n",
                    encoding="utf-8", newline="\n")
    blocks = sum(len(s.get("blocks", [])) for s in data.values())
    print(f"{dest}: {len(data)} screens, {blocks} blocks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
