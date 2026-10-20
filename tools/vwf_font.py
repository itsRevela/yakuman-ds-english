"""Compile font/vwf12.txt into the binary tables used by the VWF engine hack.

Binary layout (written to work/build/vwf_font.bin, 3328 bytes):
    0x000  u8  advance[256]     pixels to advance after drawing byte N
    0x100  u8  rows[256][12]    glyph rows, bit 7 = leftmost pixel

Bytes with no glyph get the '?' glyph so missing characters are visible instead of invisible.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT_SRC = ROOT / "font" / "vwf12.txt"
FONT_BIN = ROOT / "work" / "build" / "vwf_font.bin"

ROWS = 12
MAX_WIDTH = 8
FALLBACK = 0x3F  # '?'
# Single-byte values the game treats as Shift-JIS lead bytes can never reach the VWF.
SJIS_LEAD = set(range(0x81, 0xA0)) | set(range(0xE0, 0xFD))

_HEADER_RE = re.compile(r"^@\s+([0-9A-Fa-f]{2})(?:\s+adv=(\d+))?\s*$")
_ROW_RE = re.compile(r"^(\d+)\s+([.#]+)\s*$")


@dataclass(frozen=True)
class Glyph:
    code: int
    width: int
    advance: int
    rows: tuple[int, ...]  # ROWS bytes, bit 7 = leftmost


class FontError(ValueError):
    pass


def parse_font(text: str, source: str = "<font>") -> dict[int, Glyph]:
    glyphs: dict[int, Glyph] = {}
    current: dict | None = None

    def finish() -> None:
        if current is None:
            return
        code = current["code"]
        if not current["rows"]:
            raise FontError(f"{source}: glyph {code:02X} has no rows")
        widths = {len(p) for p in current["rows"].values()}
        if len(widths) != 1:
            raise FontError(f"{source}: glyph {code:02X} has rows of differing widths {sorted(widths)}")
        width = widths.pop()
        if width > MAX_WIDTH:
            raise FontError(f"{source}: glyph {code:02X} is {width} px wide (max {MAX_WIDTH})")
        rows = [0] * ROWS
        for r, pattern in current["rows"].items():
            rows[r] = sum(0x80 >> i for i, ch in enumerate(pattern) if ch == "#")
        advance = current["adv"] if current["adv"] is not None else width + 1
        glyphs[code] = Glyph(code, width, advance, tuple(rows))

    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            finish()
            m = _HEADER_RE.match(line)
            if not m:
                raise FontError(f"{source}:{line_no}: bad glyph header {raw!r}")
            code = int(m.group(1), 16)
            if code in glyphs:
                raise FontError(f"{source}:{line_no}: glyph {code:02X} defined twice")
            if code < 0x20 or code in SJIS_LEAD:
                raise FontError(f"{source}:{line_no}: byte {code:02X} is not drawable as a single-byte glyph")
            current = {"code": code, "adv": int(m.group(2)) if m.group(2) else None, "rows": {}}
            continue
        m = _ROW_RE.match(line)
        if not m or current is None:
            raise FontError(f"{source}:{line_no}: expected '<row> <pattern>', got {raw!r}")
        r = int(m.group(1))
        if not 0 <= r < ROWS:
            raise FontError(f"{source}:{line_no}: row {r} out of range 0..{ROWS - 1}")
        if r in current["rows"]:
            raise FontError(f"{source}:{line_no}: row {r} given twice")
        current["rows"][r] = m.group(2)
    finish()
    if FALLBACK not in glyphs:
        raise FontError(f"{source}: fallback glyph {FALLBACK:02X} missing")
    return glyphs


def load_font(path: Path = FONT_SRC) -> dict[int, Glyph]:
    return parse_font(path.read_text(encoding="utf-8"), str(path))


def to_binary(glyphs: dict[int, Glyph]) -> bytes:
    fallback = glyphs[FALLBACK]
    advance = bytearray(256)
    rows = bytearray()
    for code in range(256):
        g = glyphs.get(code, fallback)
        advance[code] = g.advance
        rows += bytes(g.rows)
    return bytes(advance) + bytes(rows)


def render_preview(glyphs: dict[int, Glyph], text: str, encode, scale: int = 3) -> tuple[int, int, list]:
    """Render `text` (already a str; `encode` maps it to bytes) the way the game would."""
    data = encode(text)
    width = sum(glyphs.get(b, glyphs[FALLBACK]).advance for b in data) + 2
    img = [[(255, 255, 255, 255)] * (width * scale) for _ in range(ROWS * scale)]
    x = 1
    for b in data:
        g = glyphs.get(b, glyphs[FALLBACK])
        for r, bits in enumerate(g.rows):
            for c in range(MAX_WIDTH):
                if bits & (0x80 >> c):
                    for dy in range(scale):
                        for dx in range(scale):
                            img[r * scale + dy][(x + c) * scale + dx] = (0, 0, 0, 255)
        x += g.advance
    return width * scale, ROWS * scale, img


def main() -> int:
    glyphs = load_font()
    FONT_BIN.parent.mkdir(parents=True, exist_ok=True)
    FONT_BIN.write_bytes(to_binary(glyphs))
    print(f"{len(glyphs)} glyphs -> {FONT_BIN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
