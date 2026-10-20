"""Decode/encode the game's headerless Nitro textures (.ntft texels + .ntfp palette).

The files carry no header; the format is inferred from the palette size unless given:
    palette   4 bytes -> 2bpp?   32 bytes -> 4bpp (16 colours)   512 bytes -> 8bpp (256 colours)
Texel layout is the DS's linear, row-major order with the lowest bits holding the leftmost pixel.
Palette entries are BGR555; index 0 is drawn transparent by most of the game's textures.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pngio import Image, write_png  # noqa: E402

FORMAT_BPP = {"2bpp": 2, "4bpp": 4, "8bpp": 8}


def bgr555_to_rgb(c: int) -> tuple[int, int, int]:
    r, g, b = c & 31, (c >> 5) & 31, (c >> 10) & 31
    return (r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2)


def rgb_to_bgr555(r: int, g: int, b: int) -> int:
    return (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)


def read_palette(data: bytes) -> list[tuple[int, int, int]]:
    return [bgr555_to_rgb(c) for (c,) in struct.iter_unpack("<H", data[: len(data) // 2 * 2])]


def guess_format(palette_size: int) -> str:
    if palette_size <= 8:
        return "2bpp"
    if palette_size <= 32:
        return "4bpp"
    return "8bpp"


def decode_indices(texels: bytes, bpp: int) -> list[int]:
    per = 8 // bpp
    mask = (1 << bpp) - 1
    return [(b >> (bpp * i)) & mask for b in texels for i in range(per)]


def encode_indices(indices: list[int], bpp: int) -> bytes:
    per = 8 // bpp
    if len(indices) % per:
        raise ValueError("pixel count not a multiple of pixels-per-byte")
    out = bytearray()
    for i in range(0, len(indices), per):
        b = 0
        for j in range(per):
            v = indices[i + j]
            if not 0 <= v < (1 << bpp):
                raise ValueError(f"index {v} does not fit in {bpp} bpp")
            b |= v << (bpp * j)
        out.append(b)
    return bytes(out)


def to_image(texels: bytes, palette: list[tuple[int, int, int]], bpp: int, width: int,
             transparent0: bool = True) -> Image:
    idx = decode_indices(texels, bpp)
    if len(idx) % width:
        raise ValueError(f"{len(idx)} pixels is not a multiple of width {width}")
    height = len(idx) // width
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            i = idx[y * width + x]
            rgb = palette[i] if i < len(palette) else (255, 0, 255)
            row.append((*rgb, 0 if (transparent0 and i == 0) else 255))
        rows.append(row)
    return width, height, rows


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: ntft.py <texels.ntft> <out.png> [width] [format]")
        return 2
    tex = Path(argv[0])
    pal = tex.with_suffix(".ntfp")
    width = int(argv[2]) if len(argv) > 2 else 256
    palette_bytes = pal.read_bytes()
    fmt = argv[3] if len(argv) > 3 else guess_format(len(palette_bytes))
    img = to_image(tex.read_bytes(), read_palette(palette_bytes), FORMAT_BPP[fmt], width)
    write_png(argv[1], img)
    print(f"{tex.name}: {fmt}, {img[0]}x{img[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
