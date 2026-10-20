"""Large display text: the 12 px VWF font upscaled with Scale2x (EPX), optionally emboldened.

Scale2x keeps pixel-art diagonals smooth instead of the staircase of a plain 2x zoom, giving a
~24 px font for headers and titles that matches the hand-drawn look of the game's own text.
Output is a 1-bit mask (list of rows of 0/1); colouring (outline, gradient) is done by the caller.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import textcodec  # noqa: E402
import vwf_font  # noqa: E402

Mask = list[list[int]]

_GLYPHS = None


def _glyphs() -> dict[int, vwf_font.Glyph]:
    global _GLYPHS
    if _GLYPHS is None:
        _GLYPHS = vwf_font.load_font()
    return _GLYPHS


def text_mask(text: str, spacing: int = 0) -> Mask:
    """1x mask of a single line in the VWF font (12 rows)."""
    data = textcodec.encode(text, allow_fullwidth=False)
    g = _glyphs()
    glyphs = [g.get(b, g[vwf_font.FALLBACK]) for b in data]
    width = max(1, sum(gl.advance + spacing for gl in glyphs) - spacing)
    mask = [[0] * (width + vwf_font.MAX_WIDTH) for _ in range(vwf_font.ROWS)]
    x = 0
    for gl in glyphs:
        for r, bits in enumerate(gl.rows):
            for c in range(vwf_font.MAX_WIDTH):
                if bits & (0x80 >> c):
                    mask[r][x + c] = 1
        x += gl.advance + spacing
    return trim_columns(mask)


def trim_columns(mask: Mask) -> Mask:
    cols = [x for x in range(len(mask[0])) if any(row[x] for row in mask)]
    if not cols:
        return [row[:1] for row in mask]
    return [row[cols[0]:cols[-1] + 1] for row in mask]


def scale2x(mask: Mask) -> Mask:
    h, w = len(mask), len(mask[0])

    def px(x: int, y: int) -> int:
        return mask[y][x] if 0 <= x < w and 0 <= y < h else 0

    out = [[0] * (2 * w) for _ in range(2 * h)]
    for y in range(h):
        for x in range(w):
            p, a, b, c, d = px(x, y), px(x, y - 1), px(x + 1, y), px(x - 1, y), px(x, y + 1)
            e0 = e1 = e2 = e3 = p
            if c == a and c != d and a != b:
                e0 = a
            if a == b and a != c and b != d:
                e1 = b
            if d == c and d != b and c != a:
                e2 = c
            if b == d and b != a and d != c:
                e3 = d
            out[2 * y][2 * x], out[2 * y][2 * x + 1] = e0, e1
            out[2 * y + 1][2 * x], out[2 * y + 1][2 * x + 1] = e2, e3
    return out


def embolden(mask: Mask) -> Mask:
    """Thicken strokes by one pixel to the right."""
    w = len(mask[0])
    return [[1 if row[x] or (x > 0 and row[x - 1]) else 0 for x in range(w)] + [row[-1]] for row in mask]


def big_mask(text: str, bold: bool = True) -> Mask:
    mask = scale2x(text_mask(text))
    return embolden(mask) if bold else mask


# 4x5 capitals, 3x5 digits and a few symbols for very small labels (drawn for this project).
TINY = {
    "A": (".##.", "#..#", "####", "#..#", "#..#"),
    "B": ("###.", "#..#", "###.", "#..#", "###."),
    "C": (".###", "#...", "#...", "#...", ".###"),
    "D": ("###.", "#..#", "#..#", "#..#", "###."),
    "E": ("####", "#...", "###.", "#...", "####"),
    "F": ("####", "#...", "###.", "#...", "#..."),
    "G": (".###", "#...", "#.##", "#..#", ".###"),
    "H": ("#..#", "#..#", "####", "#..#", "#..#"),
    "I": ("###", ".#.", ".#.", ".#.", "###"),
    "J": ("..##", "...#", "...#", "#..#", ".##."),
    "K": ("#..#", "#.#.", "##..", "#.#.", "#..#"),
    "L": ("#...", "#...", "#...", "#...", "####"),
    "M": ("#...#", "##.##", "#.#.#", "#...#", "#...#"),
    "N": ("#..#", "##.#", "#.##", "#..#", "#..#"),
    "O": (".##.", "#..#", "#..#", "#..#", ".##."),
    "P": ("###.", "#..#", "###.", "#...", "#..."),
    "Q": (".##.", "#..#", "#..#", "#.#.", ".#.#"),
    "R": ("###.", "#..#", "###.", "#.#.", "#..#"),
    "S": (".###", "#...", ".##.", "...#", "###."),
    "T": ("###", ".#.", ".#.", ".#.", ".#."),
    "U": ("#..#", "#..#", "#..#", "#..#", ".##."),
    "V": ("#..#", "#..#", "#..#", ".##.", ".##."),
    "W": ("#...#", "#...#", "#.#.#", "##.##", "#...#"),
    "X": ("#..#", "#..#", ".##.", "#..#", "#..#"),
    "Y": ("#.#", "#.#", ".#.", ".#.", ".#."),
    "Z": ("####", "...#", ".##.", "#...", "####"),
    "0": ("###", "#.#", "#.#", "#.#", "###"),
    "1": (".#", "##", ".#", ".#", ".#"),
    "2": ("###", "..#", "###", "#..", "###"),
    "3": ("###", "..#", ".##", "..#", "###"),
    "4": ("#.#", "#.#", "###", "..#", "..#"),
    "5": ("###", "#..", "###", "..#", "###"),
    "6": ("###", "#..", "###", "#.#", "###"),
    "7": ("###", "..#", "..#", ".#.", ".#."),
    "8": ("###", "#.#", "###", "#.#", "###"),
    "9": ("###", "#.#", "###", "..#", "###"),
    "/": ("...#", "..#.", ".#..", ".#..", "#..."),
    "-": ("...", "...", "###", "...", "..."),
    ".": (".", ".", ".", ".", "#"),
    " ": ("..", "..", "..", "..", ".."),
}


def tiny_mask(text: str) -> Mask:
    missing = sorted({c for c in text if c not in TINY})
    if missing:
        raise ValueError(f"tiny font has no glyph for {missing}")
    rows: Mask = [[] for _ in range(5)]
    for i, ch in enumerate(text):
        for r in range(5):
            if i:
                rows[r].append(0)
            rows[r].extend(1 if c == "#" else 0 for c in TINY[ch][r])
    return rows


def trim_rows(mask: Mask) -> Mask:
    inked = [y for y, row in enumerate(mask) if any(row)]
    return mask[inked[0]:inked[-1] + 1] if inked else mask[:1]


def scale3x(mask: Mask) -> Mask:
    """AdvMAME3x / Scale3x pixel-art upscaler."""
    h, w = len(mask), len(mask[0])

    def px(x: int, y: int) -> int:
        return mask[y][x] if 0 <= x < w and 0 <= y < h else 0

    out = [[0] * (3 * w) for _ in range(3 * h)]
    for y in range(h):
        for x in range(w):
            a, b, c = px(x - 1, y - 1), px(x, y - 1), px(x + 1, y - 1)
            d, e, f = px(x - 1, y), px(x, y), px(x + 1, y)
            g, hh, i = px(x - 1, y + 1), px(x, y + 1), px(x + 1, y + 1)
            r = [[e] * 3 for _ in range(3)]
            if b != hh and d != f:
                r[0][0] = d if d == b else e
                r[0][1] = b if (d == b and e != c) or (b == f and e != a) else e
                r[0][2] = f if b == f else e
                r[1][0] = d if (d == b and e != g) or (d == hh and e != a) else e
                r[1][2] = f if (b == f and e != i) or (hh == f and e != c) else e
                r[2][0] = d if d == hh else e
                r[2][1] = hh if (d == hh and e != i) or (hh == f and e != g) else e
                r[2][2] = f if hh == f else e
            for dy in range(3):
                for dx in range(3):
                    out[3 * y + dy][3 * x + dx] = r[dy][dx]
    return out


def huge_mask(text: str, bold: bool = True) -> Mask:
    """~36 px text: the VWF font upscaled 3x with Scale3x, emboldened by 2 px."""
    mask = scale3x(text_mask(text))
    return embolden(embolden(mask)) if bold else mask


def rotate_ccw(img: list[list[int]], degrees: int) -> list[list[int]]:
    """Rotate an image counter-clockwise by 0/90/180/270 degrees."""
    turns = (degrees // 90) % 4
    for _ in range(turns):
        img = [list(row) for row in zip(*img)][::-1]
    return img
