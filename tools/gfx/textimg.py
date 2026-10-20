"""Render English text into palette-index images for the game's texture/BG graphics.

Images are lists of rows of palette indices (0 = transparent). Text uses the VWF font
(font/vwf12.txt) with a fill index and an optional 1 px outline index, so results sit naturally
next to the game's own outlined text.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import textcodec  # noqa: E402
import vwf_font  # noqa: E402

Indexed = list[list[int]]

_GLYPHS = None


def glyphs() -> dict[int, vwf_font.Glyph]:
    global _GLYPHS
    if _GLYPHS is None:
        _GLYPHS = vwf_font.load_font()
    return _GLYPHS


@dataclass(frozen=True)
class TextStyle:
    fill: int
    outline: int | None = None   # palette index of a 1 px outline (8-neighbour), or None
    shadow: int | None = None    # palette index of a 1 px drop shadow (+1, +1), or None
    spacing: int = 0             # extra pixels between characters


def blank(width: int, height: int, index: int = 0) -> Indexed:
    return [[index] * width for _ in range(height)]


def text_width(text: str, style: TextStyle) -> int:
    data = textcodec.encode(text, allow_fullwidth=False)
    g = glyphs()
    if not data:
        return 0
    adv = sum(g.get(b, g[vwf_font.FALLBACK]).advance + style.spacing for b in data) - style.spacing - 1
    return adv + (2 if style.outline is not None else 0) + (1 if style.shadow is not None else 0)


def render(text: str, style: TextStyle) -> Indexed:
    """Render one line of text into a tight image (12 px glyph cell plus outline/shadow margins)."""
    data = textcodec.encode(text, allow_fullwidth=False)
    if b"!" in data:
        raise ValueError("render() draws a single line; split on newlines first")
    g = glyphs()
    margin = 1 if style.outline is not None else 0
    width = text_width(text, style)
    height = vwf_font.ROWS + 2 * margin + (1 if style.shadow is not None else 0)
    img = blank(width, height)
    ink: list[tuple[int, int]] = []
    x = margin
    for b in data:
        glyph = g.get(b, g[vwf_font.FALLBACK])
        for r, bits in enumerate(glyph.rows):
            for c in range(vwf_font.MAX_WIDTH):
                if bits & (0x80 >> c):
                    ink.append((x + c, margin + r))
        x += glyph.advance + style.spacing
    inked = set(ink)
    if style.shadow is not None:
        for px, py in ink:
            if (px + 1, py + 1) not in inked and px + 1 < width and py + 1 < height:
                img[py + 1][px + 1] = style.shadow
    if style.outline is not None:
        for px, py in ink:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx, ny = px + dx, py + dy
                    if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in inked:
                        img[ny][nx] = style.outline
    for px, py in ink:
        if px < width:
            img[py][px] = style.fill
    return img


def colorize(mask: list[list[int]], fill: int | list[int], outline: int | None = None,
             outline_width: int = 1, shadow: int | None = None,
             outline2: int | list[int] | None = None) -> Indexed:
    """Turn a 1-bit mask into an indexed image.

    fill is one index or a list of indices spread over the mask's inked rows top to bottom (a
    vertical gradient). The outline grows outline_width pixels around the ink (8-neighbour);
    outline2 adds one more ring outside it (a list adds one ring per colour, innermost first);
    the shadow is the outlined shape offset by (+1, +1).
    """
    rings = [] if outline2 is None else (outline2 if isinstance(outline2, list) else [outline2])
    margin = (outline_width if outline is not None else 0) + len(rings)
    extra = 1 if shadow is not None else 0
    h, w = len(mask), len(mask[0])
    out = blank(w + 2 * margin + extra, h + 2 * margin + extra)
    inked_rows = [y for y in range(h) if any(mask[y])]
    top, bottom = (inked_rows[0], inked_rows[-1]) if inked_rows else (0, 0)
    ink = {(x + margin, y + margin) for y in range(h) for x in range(w) if mask[y][x]}
    shape = set(ink)
    for _ in range(outline_width if outline is not None else 0):
        shape |= {(x + dx, y + dy) for x, y in shape for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    outer = set(shape)
    ring_areas = []
    for color in rings:
        outer = outer | {(x + dx, y + dy) for x, y in outer for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        ring_areas.append((color, outer))
    if shadow is not None:
        for x, y in outer:
            out[y + 1][x + 1] = shadow
    for color, area in reversed(ring_areas):     # outermost first; inner rings paint over it
        for x, y in area:
            out[y][x] = color
    if outline is not None:
        for x, y in shape:
            out[y][x] = outline
    bands = fill if isinstance(fill, list) else [fill]
    span = max(1, bottom - top + 1)
    for x, y in ink:
        band = min(len(bands) - 1, (y - margin - top) * len(bands) // span)
        out[y][x] = bands[band]
    return out


def paste(dst: Indexed, src: Indexed, x: int, y: int, transparent: int | None = 0) -> None:
    for sy, row in enumerate(src):
        ty = y + sy
        if not 0 <= ty < len(dst):
            continue
        for sx, v in enumerate(row):
            tx = x + sx
            if 0 <= tx < len(dst[ty]) and (transparent is None or v != transparent):
                dst[ty][tx] = v


def shelf_pack(sizes: list[tuple[int, int]], width: int, height: int) -> list[tuple[int, int]]:
    """Place rectangles (w, h) left-to-right in rows of equal height; returns (u, v) per rect."""
    positions = []
    x = y = row_h = 0
    for w, h in sizes:
        if w > width:
            raise ValueError(f"rectangle {w}x{h} wider than atlas {width}")
        if x + w > width:
            x, y, row_h = 0, y + row_h, 0
        if y + h > height:
            raise ValueError(f"atlas {width}x{height} full; cannot place {w}x{h}")
        positions.append((x, y))
        x += w
        row_h = max(row_h, h)
    return positions


def shelf_pack_ffd(sizes: list[tuple[int, int]], width: int, height: int) -> list[tuple[int, int]]:
    """First-fit decreasing shelf packing for equal-height rectangles; returns (u, v) per rect.

    Rectangles are placed widest first into the first shelf with room, which packs variable
    width strips far tighter than filling shelves in input order.
    """
    if len({h for _, h in sizes}) > 1:
        raise ValueError("shelf_pack_ffd needs rectangles of one height")
    row_h = sizes[0][1] if sizes else 0
    shelves: list[int] = []  # used width per shelf
    positions: list[tuple[int, int] | None] = [None] * len(sizes)
    for i in sorted(range(len(sizes)), key=lambda k: -sizes[k][0]):
        w = sizes[i][0]
        if w > width:
            raise ValueError(f"rectangle {w}x{row_h} wider than atlas {width}")
        for s, used in enumerate(shelves):
            if used + w <= width:
                positions[i] = (used, s * row_h)
                shelves[s] += w
                break
        else:
            if (len(shelves) + 1) * row_h > height:
                raise ValueError(f"atlas {width}x{height} full; cannot place {w}x{row_h}")
            positions[i] = (0, len(shelves) * row_h)
            shelves.append(w)
    return positions
