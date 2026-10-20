"""Encode English translation text into the byte format the (patched) game renderer expects.

Markup used in translation files:
    \\n        line break                 -> 0x21 ('!' is the renderer's newline code)
    {...}     highlighted cross-reference -> 0x3C ... 0x3E
    ^         toggle instant drawing      -> 0x23
Literal '!', '#', '<', '>' and typographic extras are remapped to glyph slots >= 0xA0
(see font/vwf12.txt). Any other non-ASCII character is emitted as 2-byte Shift-JIS and drawn
with the game's original 12x12 full-width font (e.g. the tutorial's tile placeholder 'Π').
"""
from __future__ import annotations

from vwf_font import FALLBACK, Glyph

NEWLINE = 0x21
HL_START, HL_END = 0x3C, 0x3E
INSTANT = 0x23
FULLWIDTH_ADVANCE = 12

# Characters whose ASCII code is a control code, plus extras with their own glyph slot.
REMAP = {
    "!": 0xA1, "#": 0xA3, "<": 0xBC, ">": 0xBE,
    "é": 0xC0, "…": 0xC1, "“": 0xC2, "”": 0xC3, "‘": 0xC4, "’": 0xC5, "×": 0xC6,
    "→": 0xC7, "←": 0xC8, "↑": 0xC9, "↓": 0xCA, "♪": 0xCB, "★": 0xCC, "☆": 0xCD,
    "○": 0xCE, "●": 0xCF, "·": 0xD0, "°": 0xD1, "〜": 0xD2,
}
MARKUP = {"\n": NEWLINE, "{": HL_START, "}": HL_END, "^": INSTANT}
_REVERSE = {v: k for k, v in REMAP.items()}
_REVERSE_MARKUP = {v: k for k, v in MARKUP.items()}


class EncodeError(ValueError):
    pass


def encode(text: str, *, allow_fullwidth: bool = True) -> bytes:
    out = bytearray()
    for i, ch in enumerate(text):
        if ch in MARKUP:
            out.append(MARKUP[ch])
        elif ch in REMAP:
            out.append(REMAP[ch])
        elif " " <= ch <= "~":
            out.append(ord(ch))
        else:
            if not allow_fullwidth:
                raise EncodeError(f"character {ch!r} at {i} has no single-byte glyph: {text!r}")
            try:
                sj = ch.encode("cp932")
            except UnicodeEncodeError as exc:
                raise EncodeError(f"character {ch!r} at {i} is not encodable: {text!r}") from exc
            if len(sj) != 2:
                raise EncodeError(f"character {ch!r} at {i} maps to a single SJIS byte: {text!r}")
            out += sj
    return bytes(out)


def decode(data: bytes) -> str:
    out = []
    i = 0
    while i < len(data):
        b = data[i]
        if 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEA:
            out.append(data[i : i + 2].decode("cp932"))
            i += 2
            continue
        if b in _REVERSE_MARKUP:
            out.append(_REVERSE_MARKUP[b])
        elif b in _REVERSE:
            out.append(_REVERSE[b])
        else:
            out.append(chr(b))
        i += 1
    return "".join(out)


def line_widths(data: bytes, glyphs: dict[int, Glyph], spacing: int = 0) -> list[int]:
    """Pixel width of each explicit line, as the patched renderer would advance."""
    widths = [0]
    i = 0
    while i < len(data):
        b = data[i]
        if 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEA:
            widths[-1] += FULLWIDTH_ADVANCE + spacing
            i += 2
            continue
        if b == NEWLINE:
            widths.append(0)
        elif b not in (HL_START, HL_END, INSTANT):
            widths[-1] += glyphs.get(b, glyphs[FALLBACK]).advance + spacing
        i += 1
    return widths
