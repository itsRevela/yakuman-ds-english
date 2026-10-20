"""Texture descriptor table: name -> (format, width, height, region table) for every vtex texture.

Each descriptor is 28 bytes in ARM9 data:
    +0  u32 format (DS GX texture format: 2 = 4-colour, 3 = 16-colour, 4 = 256-colour, ...)
    +4  u32 pointer to the texture's region (sub-image) table
    +8  u16 width code, u16 height code   (size = 8 << code)
    +12 u32 pointer to the name, e.g. "MainMenu/TexMenuText" (file vtex/<name>.ntft/.ntfp)
    +16 3 x u32 runtime fields

Usage: python tools/gfx/textures.py [--dump OUT_DIR]   (lists descriptors; --dump decodes all)
"""
from __future__ import annotations

import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from romdata import ARM9_BASE, WORK, load_arm9, read_cstring  # noqa: E402
import ntft  # noqa: E402

GX_FORMATS = {2: "2bpp", 3: "4bpp", 4: "8bpp"}
FILES = WORK / "extract" / "files" / "vtex"


@dataclass(frozen=True)
class Texture:
    desc_addr: int
    name: str
    gx_format: int
    width: int
    height: int
    regions_addr: int

    @property
    def texel_path(self) -> Path:
        return FILES / f"{self.name}.ntft"

    @property
    def palette_path(self) -> Path:
        return FILES / f"{self.name}.ntfp"


def find_textures(a9: bytes | None = None) -> list[Texture]:
    a9 = a9 or load_arm9()
    wanted = {f.relative_to(FILES).with_suffix("").as_posix() for f in FILES.rglob("*.ntft")}
    names = {}
    for m in re.finditer(rb"[A-Za-z0-9_/]{3,40}\x00", a9):
        name = m.group()[:-1].decode()
        if name in wanted:
            names[m.start() + ARM9_BASE] = name
    out = []
    for off in range(0, len(a9) - 28, 4):
        name_ptr = struct.unpack_from("<I", a9, off + 12)[0]
        if name_ptr not in names:
            continue
        fmt, regions, wcode, hcode = struct.unpack_from("<IIHH", a9, off)
        if fmt not in GX_FORMATS or not (0 <= wcode <= 7 and 0 <= hcode <= 7):
            continue
        out.append(Texture(off + ARM9_BASE, names[name_ptr], fmt, 8 << wcode, 8 << hcode, regions))
    return out


def decode(tex: Texture) -> ntft.Image:
    bpp = ntft.FORMAT_BPP[GX_FORMATS[tex.gx_format]]
    texels = tex.texel_path.read_bytes()
    expected = tex.width * tex.height * bpp // 8
    if len(texels) != expected:
        raise ValueError(f"{tex.name}: {len(texels)} bytes, expected {expected} for {tex.width}x{tex.height}")
    palette = ntft.read_palette(tex.palette_path.read_bytes())
    return ntft.to_image(texels, palette, bpp, tex.width)


def main(argv: list[str]) -> int:
    textures = find_textures()
    out_dir = Path(argv[argv.index("--dump") + 1]) if "--dump" in argv else None
    for t in textures:
        status = ""
        if out_dir:
            try:
                ntft.write_png(out_dir / f"{t.name.replace('/', '_')}.png", decode(t))
            except (ValueError, FileNotFoundError) as exc:
                status = f"  !! {exc}"
        print(f"{t.desc_addr:08x} {t.name:28s} {GX_FORMATS[t.gx_format]} {t.width}x{t.height} "
              f"regions@{t.regions_addr:08x}{status}")
    print(f"{len(textures)} textures", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
