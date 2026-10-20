"""Decode the game's 2D graphics in vdata/ (headerless OBJ/BG data) to PNG for inspection.

    .plt   BGR555 palette (32 bytes = 16 colours -> 4bpp, 512 bytes = 256 colours -> 8bpp)
    .gcd   character data: 8x8 tiles (32 bytes each at 4bpp, 64 at 8bpp), laid out 1D as the
           game's sprites use them (each sprite's tiles row-major, sprites back to back)
    .gbd   bitmap data (BG): either 8bpp linear pixels or tiles, decided by the caller

Usage:
    python tools/gfx/vdata.py tiles FILE.gcd PALETTE.plt OUT.png [--sprite WxH] [--cols N]
        --sprite WxH  group tiles into sprites of W x H pixels (default 8x8) before laying out
        --cols N      sprites per output row (default 8)
    python tools/gfx/vdata.py bitmap FILE.gbd PALETTE.plt OUT.png WIDTH
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ntft  # noqa: E402

BG = (40, 70, 40, 255)


def palette_bpp(plt: bytes) -> int:
    return 4 if len(plt) <= 32 else 8


def decode_tiles(data: bytes, bpp: int) -> list[list[int]]:
    """List of tiles; each tile is 64 palette indices, row-major."""
    size = 8 * bpp
    if len(data) % size:
        raise ValueError(f"{len(data)} bytes is not a whole number of {bpp}bpp tiles")
    return [ntft.decode_indices(data[i:i + size], bpp) for i in range(0, len(data), size)]


def encode_tiles(tiles: list[list[int]], bpp: int) -> bytes:
    return b"".join(ntft.encode_indices(t, bpp) for t in tiles)


def sprites_to_image(tiles: list[list[int]], sprite_w: int, sprite_h: int, cols: int) -> list[list[int]]:
    """Arrange 1D-mapped tiles into sprites of sprite_w x sprite_h, `cols` sprites per row."""
    tw, th = sprite_w // 8, sprite_h // 8
    per = tw * th
    count = (len(tiles) + per - 1) // per
    rows_of_sprites = (count + cols - 1) // cols
    img = [[-1] * (cols * sprite_w) for _ in range(rows_of_sprites * sprite_h)]
    for t, tile in enumerate(tiles):
        s, k = divmod(t, per)
        sx, sy = (s % cols) * sprite_w, (s // cols) * sprite_h
        tx, ty = (k % tw) * 8, (k // tw) * 8
        for i, v in enumerate(tile):
            img[sy + ty + i // 8][sx + tx + i % 8] = v
    return img


def image_to_tiles(img: list[list[int]], sprite_w: int, sprite_h: int, cols: int, count: int) -> list[list[int]]:
    """Inverse of sprites_to_image for the first `count` tiles."""
    tw, th = sprite_w // 8, sprite_h // 8
    per = tw * th
    tiles = []
    for t in range(count):
        s, k = divmod(t, per)
        sx, sy = (s % cols) * sprite_w, (s // cols) * sprite_h
        tx, ty = (k % tw) * 8, (k // tw) * 8
        tiles.append([img[sy + ty + i // 8][sx + tx + i % 8] for i in range(64)])
    return tiles


def to_rgba(img: list[list[int]], pal: list[tuple[int, int, int]]) -> list[list[tuple[int, int, int, int]]]:
    return [[BG if v <= 0 else (*pal[v], 255) for v in row] for row in img]


def main(argv: list[str]) -> int:
    mode = argv[0]
    data = Path(argv[1]).read_bytes()
    plt = Path(argv[2]).read_bytes()
    pal = ntft.read_palette(plt)
    bpp = palette_bpp(plt)
    out = argv[3]
    if mode == "tiles":
        sw = sh = 8
        cols = 8
        if "--sprite" in argv:
            sw, sh = (int(v) for v in argv[argv.index("--sprite") + 1].split("x"))
        if "--cols" in argv:
            cols = int(argv[argv.index("--cols") + 1])
        img = sprites_to_image(decode_tiles(data, bpp), sw, sh, cols)
    elif mode == "bitmap":
        width = int(argv[4])
        idx = ntft.decode_indices(data, bpp)
        img = [idx[y * width:(y + 1) * width] for y in range(len(idx) // width)]
    else:
        raise SystemExit(__doc__)
    rows = to_rgba(img, pal)
    ntft.write_png(out, (len(rows[0]), len(rows), rows))
    print(f"{Path(argv[1]).name}: {bpp}bpp, {len(rows[0])}x{len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
