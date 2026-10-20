"""Re-lay out sprite text drawn by code at hard-coded positions (e.g. challenge clear conditions).

The game composes some sentences from texture regions drawn with func_0206f82c(flags, sprite, x,
y, ...), where sprite = texture_id * 1000 + region and x/y come from `mov r2, #x` / `mov r3, #y`
right before each call. A layout spec lists, per sentence, lines of draw calls in English reading
order; this module measures the (already translated) regions and rewrites the x/y immediates so
the fragments sit next to each other. Every instruction is checked against its original encoding
before it is changed, so a wrong address fails the build instead of corrupting code.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from regions import read_regions
from romdata import ARM9_BASE

TEXTURE_TABLE = 0x020F01B0   # 28-byte texture records; sprite // 1000 indexes this table
RECORD_SIZE = 28
DESCRIPTOR_SKEW = 8          # textures.find_textures() reports record + 8 (the format field)


class LayoutError(ValueError):
    pass


@dataclass(frozen=True)
class Call:
    sprite: int
    x_addr: int
    x: int
    y_addr: int
    y: int


def mov_imm_word(rd: int, value: int) -> int:
    if not 0 <= value <= 0xFF:
        raise LayoutError(f"position {value} does not fit an 8-bit immediate")
    return 0xE3A00000 | (rd << 12) | value


def patch_mov(arm9: bytearray, addr: int, rd: int, old: int, new: int) -> None:
    off = addr - ARM9_BASE
    word = struct.unpack_from("<I", arm9, off)[0]
    if word not in (mov_imm_word(rd, old), mov_imm_word(rd, new)):
        raise LayoutError(f"{addr:08x}: expected mov r{rd}, #{old} but found {word:08x}")
    struct.pack_into("<I", arm9, off, mov_imm_word(rd, new))


def region_width(arm9: bytes, sprite: int, tables: dict[int, tuple[int, int]]) -> tuple[int, int]:
    """(width, x offset) of a sprite's region in the current ARM9 image."""
    tex_id, index = divmod(sprite, 1000)
    if tex_id not in tables:
        raise LayoutError(f"sprite {sprite}: unknown texture {tex_id}")
    addr, count = tables[tex_id]
    if index >= count:
        raise LayoutError(f"sprite {sprite}: region {index} out of range ({count})")
    r = read_regions(arm9, addr, count)[index]
    return r.w, r.x


def texture_tables(textures, counts: dict[int, int]) -> dict[int, tuple[int, int]]:
    out = {}
    for t in textures:
        tex_id, rem = divmod(t.desc_addr - DESCRIPTOR_SKEW - TEXTURE_TABLE, RECORD_SIZE)
        if rem == 0 and t.regions_addr in counts:
            out[tex_id] = (t.regions_addr, counts[t.regions_addr])
    return out


def line_width(arm9: bytearray, tokens: list[str], calls: dict, tables: dict, space: int) -> int:
    total = 0
    for i, token in enumerate(tokens):
        call = calls[int(token.lstrip("+"), 16)]
        total += region_width(bytes(arm9), call.sprite, tables)[0]
        if i and not token.startswith("+"):
            total += space
    return total


def apply_layout(arm9: bytearray, spec: dict, tables: dict[int, tuple[int, int]]) -> int:
    calls = {int(a, 16): Call(c["sprite"], int(c["x_addr"], 16), c["x"], int(c["y_addr"], 16), c["y"])
             for a, c in spec["calls"].items()}
    space = spec.get("space", 3)
    max_width = spec.get("max_width")
    placed: dict[int, tuple[int, int]] = {}
    for group in spec["groups"]:
        for line in group["lines"]:
            cursor = line.get("x", spec["origin_x"])
            if "center" in line:
                cursor = line["center"] - line_width(arm9, line["tokens"], calls, tables, space) // 2
            start = cursor
            for i, token in enumerate(line["tokens"]):
                glue = token.startswith("+")
                addr = int(token.lstrip("+"), 16)
                if addr not in calls:
                    raise LayoutError(f"{group['name']}: call {addr:08x} not in spec calls")
                call = calls[addr]
                width, offset = region_width(bytes(arm9), call.sprite, tables)
                if i and not glue:
                    cursor += space
                pos = (cursor - offset, line["y"])
                if addr in placed and placed[addr] != pos:
                    raise LayoutError(f"{group['name']}: call {addr:08x} placed at {pos} and {placed[addr]}")
                placed[addr] = pos
                cursor += width
            if max_width is not None and cursor - start > max_width:
                raise LayoutError(f"{group['name']}: line at y={line['y']} is {cursor - start} px, "
                                  f"limit {max_width}")
    for addr, (x, y) in placed.items():
        call = calls[addr]
        patch_mov(arm9, call.x_addr, 2, call.x, x)
        patch_mov(arm9, call.y_addr, 3, call.y, y)
    return len(placed)
