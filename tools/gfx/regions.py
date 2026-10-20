"""Texture region tables: the sub-images (u, v, w, h, x, y) each texture is drawn from.

Region tables are stored back to back in ARM9 data (0x020ECEA8 onwards), so the size of a table
is the distance to the next table referenced by any texture descriptor.

Usage: python tools/gfx/regions.py NAME [OUT.png]   (list regions; optionally draw numbered boxes)
"""
from __future__ import annotations

import struct
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from romdata import ARM9_BASE, load_arm9  # noqa: E402
from textures import Texture, decode, find_textures  # noqa: E402

REGION_SIZE = 12
# The last table (Ranking/Ranking) has no successor; its size was counted by hand.
LAST_TABLE_COUNT = {0x020EFD84: 89}


@dataclass(frozen=True)
class Region:
    u: int
    v: int
    w: int
    h: int
    x: int
    y: int

    def overlaps(self, other: "Region") -> bool:
        return (self.u < other.u + other.w and other.u < self.u + self.w
                and self.v < other.v + other.h and other.v < self.v + self.h)


def table_counts(textures: list[Texture]) -> dict[int, int]:
    starts = sorted({t.regions_addr for t in textures})
    counts = {a: (b - a) // REGION_SIZE for a, b in zip(starts, starts[1:])}
    for addr, n in LAST_TABLE_COUNT.items():
        if addr == starts[-1]:
            counts[addr] = n
    return counts


def read_regions(arm9: bytes, addr: int, count: int) -> list[Region]:
    off = addr - ARM9_BASE
    return [Region(*struct.unpack_from("<6h", arm9, off + i * REGION_SIZE)) for i in range(count)]


def write_region(arm9: bytearray, addr: int, index: int, region: Region) -> None:
    struct.pack_into("<6h", arm9, addr - ARM9_BASE + index * REGION_SIZE,
                     region.u, region.v, region.w, region.h, region.x, region.y)


def main(argv: list[str]) -> int:
    arm9 = load_arm9()
    textures = find_textures(arm9)
    tex = {t.name: t for t in textures}[argv[0]]
    count = table_counts(textures).get(tex.regions_addr)
    if count is None:
        raise SystemExit(f"unknown region count for table {tex.regions_addr:08x}")
    regions = read_regions(arm9, tex.regions_addr, count)
    for i, r in enumerate(regions):
        print(f"{i:3d} uv=({r.u:3d},{r.v:3d}) wh=({r.w:3d},{r.h:3d}) xy=({r.x:4d},{r.y:4d})")
    if len(argv) > 1:
        import ntft
        import textimg
        _, _, src_rows = decode(tex)
        scale = 2
        rows = [[(p if p[3] else (40, 70, 40, 255)) for p in row for _ in range(scale)]
                for row in src_rows for _ in range(scale)]
        label_style = textimg.TextStyle(fill=1, outline=2)
        for i, r in enumerate(regions):
            for x in range(r.u * scale, (r.u + r.w) * scale):
                for y in (r.v * scale, (r.v + r.h) * scale - 1):
                    if 0 <= y < len(rows) and 0 <= x < len(rows[0]):
                        rows[y][x] = (255, 0, 0, 255)
            for y in range(r.v * scale, (r.v + r.h) * scale):
                for x in (r.u * scale, (r.u + r.w) * scale - 1):
                    if 0 <= y < len(rows) and 0 <= x < len(rows[0]):
                        rows[y][x] = (255, 0, 0, 255)
            tag = textimg.render(str(i), label_style)
            for ty, trow in enumerate(tag):
                for tx, v in enumerate(trow):
                    y, x = r.v * scale + 1 + ty, r.u * scale + 1 + tx
                    if v and 0 <= y < len(rows) and 0 <= x < len(rows[0]):
                        rows[y][x] = (255, 255, 0, 255) if v == 1 else (0, 0, 0, 255)
        ntft.write_png(argv[1], (len(rows[0]), len(rows), rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
