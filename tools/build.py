"""Build the English-patched ROM.

Steps:
  1. fresh copy of work/extract -> work/patched
  2. compile the VWF font
  3. pad arm9.bin to the end of static BSS and assemble asm/main.asm with armips
  4. insert translated text (tools/insert_text.py) after the hack code
  5. build translated graphics (tools/gfx/assets.py)
  6. move the heap start (OS_GetInitArenaLo literal) past the new data
  7. English banner title (DS menu) for every language
  8. rebuild the ROM with dsd

Usage: python tools/build.py [--out out/Yakuman_DS_EN.nds] [--no-text]
"""
from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import vwf_font
from romdata import ARM9_BASE, ROOT, WORK

EXTRACT = WORK / "extract"
PATCHED = WORK / "patched"
BUILD = WORK / "build"
ARMIPS = ROOT / "tools" / "bin" / "armips.exe"
DSD = ROOT / "ds-decomp" / "target" / "release" / "dsd.exe"
SYMFILE = BUILD / "main.sym"
DEFAULT_OUT = ROOT / "out" / "Yakuman DS (English).nds"

BSS_END = 0x0212A200
ARENA_LO_LITERAL = 0x02006050
ORIGINAL_ARENA_LO = 0x0212A200
ARENA_ALIGN = 32
BANNER_TITLE = ["Yakuman DS", "Nintendo"]
ORIGINAL_BANNER_FIRST_LINE = "やくまんDS"


class BuildError(RuntimeError):
    pass


def run(cmd: list[str]) -> None:
    print("$", " ".join(str(c) for c in cmd))
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.rstrip())
    if proc.returncode != 0:
        raise BuildError(f"{Path(cmd[0]).name} failed ({proc.returncode}):\n{proc.stderr}")


def read_symbols(path: Path) -> dict[str, int]:
    symbols = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) == 2 and not parts[1].startswith("."):
            try:
                symbols[parts[1].lower()] = int(parts[0], 16)
            except ValueError:
                continue
    return symbols


def prepare_tree() -> Path:
    if not (EXTRACT / "config.yaml").is_file():
        raise BuildError(f"{EXTRACT} missing; run `dsd rom extract` first (see README)")
    if PATCHED.exists():
        shutil.rmtree(PATCHED)
    shutil.copytree(EXTRACT, PATCHED)
    return PATCHED / "arm9" / "arm9.bin"


def pad_arm9(arm9_bin: Path) -> None:
    data = arm9_bin.read_bytes()
    target = BSS_END - ARM9_BASE
    if len(data) > target:
        raise BuildError(f"arm9.bin is already {len(data):#x} bytes (> {target:#x}); refusing to pad")
    arm9_bin.write_bytes(data + bytes(target - len(data)))


def patch_arena(arm9_bin: Path, data_end: int) -> int:
    data = bytearray(arm9_bin.read_bytes())
    off = ARENA_LO_LITERAL - ARM9_BASE
    (current,) = struct.unpack_from("<I", data, off)
    if current != ORIGINAL_ARENA_LO:
        raise BuildError(f"arena literal at {ARENA_LO_LITERAL:#x} is {current:#x}, expected {ORIGINAL_ARENA_LO:#x}")
    new_lo = (data_end + ARENA_ALIGN - 1) & ~(ARENA_ALIGN - 1)
    struct.pack_into("<I", data, off, new_lo)
    arm9_bin.write_bytes(bytes(data))
    return new_lo


def banner_with_title(text: str, lines: list[str]) -> str:
    """banner.yaml text with every language's title block (`  lang: |-` + 4-space lines) replaced."""
    out: list[str] = []
    in_title = in_block = False
    replaced = 0
    for line in text.splitlines():
        if in_block and line.startswith("    "):
            if line.strip() != ORIGINAL_BANNER_FIRST_LINE and line.strip() != "Nintendo":
                raise BuildError(f"unexpected banner title line {line.strip()!r}")
            continue
        in_block = False
        if not line.startswith(" "):
            in_title = line == "title:"
        elif in_title and line.endswith(": |-"):
            out.append(line)
            out.extend("    " + t for t in lines)
            in_block = True
            replaced += 1
            continue
        out.append(line)
    if replaced == 0:
        raise BuildError("no banner titles found")
    return "\n".join(out) + "\n"


def patch_banner(patched: Path) -> None:
    path = patched / "banner" / "banner.yaml"
    path.write_text(banner_with_title(path.read_text(encoding="utf-8"), BANNER_TITLE), encoding="utf-8")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-text", action="store_true", help="skip text insertion (engine hacks only)")
    ap.add_argument("--asm-define", action="append", default=[], metavar="NAME",
                    help="define an armips equate (debug switches such as DEBUG_FWLOG)")
    args = ap.parse_args(argv)

    for tool in (ARMIPS, DSD):
        if not tool.is_file():
            raise BuildError(f"required tool missing: {tool} (see README)")

    BUILD.mkdir(parents=True, exist_ok=True)
    arm9_bin = prepare_tree()
    vwf_font.FONT_BIN.write_bytes(vwf_font.to_binary(vwf_font.load_font()))
    pad_arm9(arm9_bin)
    defines = [arg for name in args.asm_define for arg in ("-definelabel", name, "1")]
    run([str(ARMIPS), "asm/main.asm", "-strequ", "ARM9_BIN", str(arm9_bin.relative_to(ROOT)).replace("\\", "/"),
         "-sym", str(SYMFILE), *defines])
    symbols = read_symbols(SYMFILE)
    text_start = symbols.get("english_text_base")
    if text_start is None:
        raise BuildError("english_text_base symbol missing from armips output")

    data_end = text_start
    if not args.no_text:
        import insert_text

        data_end = insert_text.insert(arm9_bin, text_start)

    sys.path.insert(0, str(ROOT / "tools" / "gfx"))
    import assets

    assets.build_all(PATCHED / "files", arm9_bin, symbols)

    arena = patch_arena(arm9_bin, data_end)
    print(f"extension: {BSS_END:#x}-{data_end:#x} ({data_end - BSS_END} bytes), heap now starts at {arena:#x}")
    patch_banner(PATCHED)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    run([str(DSD), "rom", "build", "--config", str(PATCHED / "config.yaml"), "--rom", str(args.out)])
    print(f"built {args.out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
