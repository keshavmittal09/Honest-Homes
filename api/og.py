"""Per-project share cards.

A shared link previews far harder with an image than with text, and this is the
product's main growth loop — a buyer sends a verdict into a family WhatsApp
group. The card carries the one thing that travels: the score, the band, and the
project it belongs to.

Rendered on demand and cached in memory. Fonts are bundled in web/fonts so the
output is identical on Windows and on Render's Linux box, where no system font
is guaranteed.
"""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent / "web" / "fonts"

W, H = 1200, 630
PAPER = (244, 240, 232)
INK = (22, 34, 46)
INK_2 = (76, 89, 101)
INK_3 = (116, 128, 139)
BRAND = (27, 78, 128)
BAND = {
    "green": ((28, 132, 86), "LOOKS CLEAN"),
    "amber": ((169, 113, 26), "CAUTION"),
    "red": ((187, 59, 54), "SERIOUS FLAGS"),
    "incomplete": ((116, 128, 139), "INCOMPLETE DATA"),
}


@lru_cache(maxsize=8)
def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    p = FONT_DIR / name
    try:
        return ImageFont.truetype(str(p), size)
    except OSError:
        # Bundled font missing — a plain default still produces a valid card.
        return ImageFont.load_default()


def _mark(d: ImageDraw.ImageDraw, x: int, y: int, size: int) -> None:
    """The Honest Homes tower mark, same geometry as web/img/mark.svg.

    Drawn rather than loaded so the card needs no SVG rasteriser, and so it stays
    in step with the favicon: both are generated from this one set of rectangles.
    """
    VX, VY, VW = 4, 2, 56
    k = size / VW
    def box(bx, by, bw, bh, fill):
        d.rectangle([x + (bx - VX) * k, y + (by - VY) * k,
                     x + (bx - VX + bw) * k, y + (by - VY + bh) * k], fill=fill)
    box(10, 18, 15, 34, BRAND)
    box(39, 12, 15, 40, (94, 155, 219))
    box(25, 30, 14, 8, BRAND)
    box(45.5, 4, 3, 8, (94, 155, 219))
    for bx in (13, 18.5):
        for by in (22, 41):
            box(bx, by, 3.5, 3.5, PAPER)
    for bx in (42, 47.5):
        for by in (17, 24, 41):
            box(bx, by, 3.5, 3.5, PAPER)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int, max_lines: int) -> list[str]:
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and words:
        while lines and draw.textlength(lines[-1] + "…", font=font) > max_w:
            lines[-1] = lines[-1].rsplit(" ", 1)[0]
        joined = " ".join(lines)
        if len(joined) < len(text):
            lines[-1] += "…"
    return lines


def card(name: str, builder: str, score, band: str, headline: str, area: str = "") -> bytes:
    colour, label = BAND.get(band, BAND["incomplete"])
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    # band stripe down the left edge — the verdict readable at thumbnail size
    d.rectangle([0, 0, 18, H], fill=colour)

    _mark(d, 64, 46, 44)
    bold = _font("DejaVuSans-Bold.ttf", 30)
    d.text((122, 52), "HONEST HOMES", font=bold, fill=BRAND)
    d.text((122, 90), "Verdict from the official MahaRERA record",
           font=_font("DejaVuSans.ttf", 22), fill=INK_3)

    # project name, wrapped
    title = _font("DejaVuSerif-Bold.ttf", 58)
    y = 168
    for line in _wrap(d, name or "This project", title, W - 420, 2):
        d.text((64, y), line, font=title, fill=INK)
        y += 68

    d.text((64, y + 4), ("by " + builder)[:52] if builder else "",
           font=_font("DejaVuSans.ttf", 26), fill=INK_2)
    if area:
        d.text((64, y + 44), area[:52], font=_font("DejaVuSans.ttf", 24), fill=INK_3)

    # headline — the actual finding
    for i, line in enumerate(_wrap(d, headline, _font("DejaVuSans.ttf", 25), W - 140, 3)):
        d.text((64, 452 + i * 36), line, font=_font("DejaVuSans.ttf", 25), fill=INK_2)

    # score block, right
    if score is None:
        d.text((980, 190), "N/A", font=_font("DejaVuSans-Bold.ttf", 92), fill=INK_3, anchor="mm")
    else:
        d.text((980, 196), f"{score:g}", font=_font("DejaVuSans-Bold.ttf", 150),
               fill=colour, anchor="mm")
        d.text((980, 286), "out of 10", font=_font("DejaVuSans.ttf", 26), fill=INK_3, anchor="mm")

    lab = _font("DejaVuSans-Bold.ttf", 24)
    tw = d.textlength(label, font=lab)
    d.rounded_rectangle([980 - tw / 2 - 22, 322, 980 + tw / 2 + 22, 374], radius=26, fill=colour)
    d.text((980, 348), label, font=lab, fill=PAPER, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
