"""A proportional, outlined display font built from the game's own TexNameFont texture.

TexNameFont (vtex/TexNameFont.ntft, 4bpp 256x256) holds 16x16 cells in the order of the name
character set at ARM9 0x020F54E0 (full-width symbols, digits, A-Z, a-z, kana). Each glyph has a
1 px outline (palette index 13) and a vertical gradient fill in four bands (indices 9, 8, 10, 11).
Glyphs are cropped to their ink, so text renders proportionally, and the outline/bands can be
mapped to any palette when drawing into another texture.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ntft  # noqa: E402
from romdata import WORK, load_arm9, read_cstring  # noqa: E402

TEXTURE = WORK / "extract" / "files" / "vtex" / "TexNameFont.ntft"
CHARSET_ADDR = 0x020F54E0
CELL = 16
OUTLINE = 13
BANDS = (9, 8, 10, 11)  # top to bottom
# Full-width characters in the charset that stand in for ASCII.
ASCII_EQUIV = {"？": "?", "！": "!", "；": ";", "’": "'", "ー": "-", "～": "~", "＄": "$", "％": "%",
               "＆": "&", "．": ".", "、": ","}


@dataclass(frozen=True)
class DisplayGlyph:
    width: int
    rows: tuple[tuple[int, ...], ...]  # CELL rows of source indices (0 = empty)


@dataclass(frozen=True)
class DisplayStyle:
    outline: int
    bands: tuple[int, int, int, int]   # target indices for the four gradient bands, top to bottom
    spacing: int = -1                  # outlines of neighbouring letters overlap by default
    space_width: int = 5


def _fw_to_ascii(ch: str) -> str | None:
    if ch in ASCII_EQUIV:
        return ASCII_EQUIV[ch]
    o = ord(ch)
    if 0xFF10 <= o <= 0xFF19 or 0xFF21 <= o <= 0xFF3A or 0xFF41 <= o <= 0xFF5A:
        return chr(o - 0xFEE0)
    return None


def load_glyphs() -> dict[str, DisplayGlyph]:
    charset = read_cstring(load_arm9(), CHARSET_ADDR).decode("cp932")
    idx = ntft.decode_indices(TEXTURE.read_bytes(), 4)
    glyphs: dict[str, DisplayGlyph] = {}
    for n, ch in enumerate(charset):
        key = _fw_to_ascii(ch)
        if key is None:
            continue
        cx, cy = (n % 16) * CELL, (n // 16) * CELL
        cell = [[idx[(cy + y) * 256 + cx + x] for x in range(CELL)] for y in range(CELL)]
        cols = [x for x in range(CELL) if any(cell[y][x] for y in range(CELL))]
        if not cols:
            continue
        x0, x1 = cols[0], cols[-1] + 1
        glyphs[key] = DisplayGlyph(x1 - x0, tuple(tuple(row[x0:x1]) for row in cell))
    return glyphs


_CACHE: dict[str, DisplayGlyph] | None = None


def glyphs() -> dict[str, DisplayGlyph]:
    global _CACHE
    if _CACHE is None:
        _CACHE = load_glyphs()
    return _CACHE


def measure(text: str, style: DisplayStyle) -> int:
    g = glyphs()
    width = 0
    for i, ch in enumerate(text):
        width += style.space_width if ch == " " else g[ch].width
        if i < len(text) - 1:
            width += style.spacing
    return width


def render(text: str, style: DisplayStyle) -> list[list[int]]:
    g = glyphs()
    missing = sorted({c for c in text if c != " " and c not in g})
    if missing:
        raise ValueError(f"display font has no glyph for {missing}")
    width = measure(text, style)
    img = [[0] * width for _ in range(CELL)]
    mapping = {OUTLINE: style.outline, **{src: dst for src, dst in zip(BANDS, style.bands)}}
    x = 0
    for ch in text:
        if ch == " ":
            x += style.space_width + style.spacing
            continue
        glyph = g[ch]
        for y, row in enumerate(glyph.rows):
            for gx, v in enumerate(row):
                if v and 0 <= x + gx < width:
                    # Fill wins over a neighbour's outline where letters overlap.
                    if v != OUTLINE or img[y][x + gx] == 0:
                        img[y][x + gx] = mapping.get(v, style.bands[1])
        x += glyph.width + style.spacing
    return img
