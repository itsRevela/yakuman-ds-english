"""Print the colours used inside texture regions, to pick text styles for gfx/labels.json.

Usage: python tools/gfx/sample.py NAME REGION [REGION ...]
For each region: palette index, #rrggbb and pixel count, most common first, plus an ASCII view
where each colour is shown by its rank (0-9, a-z).
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ntft  # noqa: E402
from regions import read_regions, table_counts  # noqa: E402
from romdata import load_arm9  # noqa: E402
from textures import GX_FORMATS, find_textures  # noqa: E402

RANKS = "0123456789abcdefghijklmnopqrstuvwxyz"


def main(argv: list[str]) -> int:
    arm9 = load_arm9()
    textures = find_textures(arm9)
    tex = {t.name: t for t in textures}[argv[0]]
    regions = read_regions(arm9, tex.regions_addr, table_counts(textures)[tex.regions_addr])
    bpp = ntft.FORMAT_BPP[GX_FORMATS[tex.gx_format]]
    idx = ntft.decode_indices(tex.texel_path.read_bytes(), bpp)
    pal = ntft.read_palette(tex.palette_path.read_bytes())
    show = "--ascii" in argv
    for arg in (a for a in argv[1:] if a != "--ascii"):
        r = regions[int(arg)]
        pixels = [[idx[y * tex.width + x] for x in range(r.u, r.u + r.w)] for y in range(r.v, r.v + r.h)]
        counts = Counter(v for row in pixels for v in row if v)
        ranked = [i for i, _ in counts.most_common()]
        print(f"region {arg} {r}")
        print("   " + "  ".join(f"{i}:#{bytes(pal[i]).hex()}x{n}" for i, n in counts.most_common(12)))
        if show:
            for row in pixels:
                print("   " + "".join(RANKS[ranked.index(v)] if v and ranked.index(v) < len(RANKS) else
                                       ("." if not v else "+") for v in row))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
