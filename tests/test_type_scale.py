"""The type scale is sized for a page of tables, not for one screen in isolation.

Players were viewing the site at 80% browser zoom. That is a measurement, not an
opinion: 100% was about a fifth too big. The ramp had been set from a single
screen read on its own — "bigger and more readable", 15px to 18px base — and a
market page is now a chart, three tables, a ticket and a register. At 18px with
a 34px heading over it, that reads as shouting.

So the whole ramp came down ~18% and headings further, in both stylesheets at
once. The two are asserted to agree, because the theme and the canvas block
vocabulary style the same page and a page with two type scales looks broken in a
way nobody can name.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import abex_theme  # noqa: E402
import canvas_web  # noqa: E402


def _sizes(css):
    return sorted({float(x) for x in re.findall(r"font-size:([\d.]+)px", css)})


def test_nothing_is_set_at_the_old_body_size():
    """18px was the base; it is now a heading-ish size and must not be body."""
    css = abex_theme.THEME_CSS
    body = re.search(r"font-size:([\d.]+)px;line-height:1\.55", css)
    assert body, "the body rule moved — check the scale by hand"
    assert float(body.group(1)) <= 15.5, body.group(1)


def test_the_page_heading_came_down_hardest():
    css = abex_theme.THEME_CSS
    h1 = re.search(r"h1\{font-size:([\d.]+)px", css)
    assert h1 and float(h1.group(1)) <= 26, h1.group(1) if h1 else "no h1 rule"


def test_no_type_is_left_above_the_heading_size():
    biggest = max(_sizes(abex_theme.THEME_CSS))
    assert biggest <= 26, f"something is set at {biggest}px"


def test_nothing_is_too_small_to_read():
    """Coming down 18% must not push meta text under a readable floor."""
    assert min(_sizes(abex_theme.THEME_CSS)) >= 11, _sizes(abex_theme.THEME_CSS)


def test_both_stylesheets_share_the_scale():
    """The theme and the canvas block vocabulary style the same page."""
    theme, canvas = set(_sizes(abex_theme.THEME_CSS)), set(_sizes(canvas_web.CANVAS_CSS))
    stray = {s for s in canvas if s > max(theme)}
    assert not stray, f"canvas sets sizes the theme never does: {sorted(stray)}"


def test_the_reason_is_written_down_where_it_will_be_read():
    """Otherwise the next session reads the smaller type as a regression and
    'fixes' it back."""
    src = (Path(__file__).resolve().parent.parent / "abex_theme.py").read_text(
        encoding="utf-8")
    assert "80% browser zoom" in src, "the measurement is not recorded"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("type scale: ok")


def test_the_brand_shares_the_navs_left_edge():
    """The sidebar had a centred brand over a left-aligned nav — two columns
    that missed each other. They line up now, and this checks the ARITHMETIC
    rather than a pixel, because the failure mode is somebody changing
    `.navitem`'s padding and the brand silently drifting three pixels.

    A `.navitem` puts its padding INSIDE a left border, so its text starts at
    border + padding. The brand has no border, so its padding-left must equal
    that sum.
    """
    import re
    import abex_theme
    css = abex_theme.THEME_CSS

    item = re.search(r"\.navitem\{[^}]*\}", css, re.S).group(0)
    pad = int(re.search(r"padding:\s*[\d.]+px\s+(\d+)px", item).group(1))
    border = int(re.search(r"border-left:\s*(\d+)px", item).group(1))

    brand = re.search(r"\n\.brand\{[^}]*\}", css, re.S).group(0)
    assert "align-items:flex-start" in brand, "the brand must not be centred"
    assert "text-align:left" in brand
    # `0` is legal CSS without a unit, so the first three values may be bare.
    bpad = re.search(r"padding:\s*[\d.]+(?:px)?\s+[\d.]+(?:px)?\s+"
                     r"[\d.]+(?:px)?\s+(\d+)px", brand)
    assert bpad, "the brand needs an explicit left padding to line up: " + brand
    assert int(bpad.group(1)) == pad + border, (
        "brand starts at %spx, nav text at %spx (%s padding inside a %spx border)"
        % (bpad.group(1), pad + border, pad, border))


def test_no_css_is_left_behind_for_the_removed_badge():
    """`.brand .mark` styled the medallion `<img>`. The element is gone; rules
    for an element that no longer exists are what makes a stylesheet unreadable
    a year later."""
    import abex_theme
    import abex_shell
    for css in (abex_theme.THEME_CSS, abex_shell._FOOTER_CSS):
        assert ".brand .mark" not in css
