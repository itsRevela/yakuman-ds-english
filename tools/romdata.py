"""Shared helpers for reading the extracted Yakuman DS ARM9 binary and dsd relocations.

Paths are resolved relative to the project root so every tool works from any cwd.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
ARM9_BIN = WORK / "extract" / "arm9" / "arm9.bin"
RELOCS_TXT = WORK / "dsd" / "arm9" / "relocs.txt"
ARM9_BASE = 0x02000000

_RELOC_RE = re.compile(r"from:0x([0-9a-f]+) kind:(\S+) to:0x([0-9a-f]+)")
# Linker-symbol constants (e.g. ARM9_CTOR_START) have no concrete target address.
_LINK_CONST_RE = re.compile(r"from:0x[0-9a-f]+ kind:link_time_const\(\w+\)$")


@dataclass(frozen=True)
class Reloc:
    src: int
    kind: str
    dst: int


def load_arm9(path: Path = ARM9_BIN) -> bytes:
    if not path.is_file():
        raise FileNotFoundError(f"ARM9 binary not found at {path}; run the extract step first")
    return path.read_bytes()


def load_relocs(path: Path = RELOCS_TXT) -> list[Reloc]:
    if not path.is_file():
        raise FileNotFoundError(f"relocs.txt not found at {path}; run `dsd init` first")
    relocs = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = _RELOC_RE.match(line)
        if not m and _LINK_CONST_RE.match(line):
            continue
        if not m:
            raise ValueError(f"{path}:{line_no}: unparseable relocation line: {line!r}")
        relocs.append(Reloc(int(m.group(1), 16), m.group(2), int(m.group(3), 16)))
    return relocs


def u32(data: bytes, addr: int, base: int = ARM9_BASE) -> int:
    return struct.unpack_from("<I", data, addr - base)[0]


def is_sjis_lead(b: int) -> bool:
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEA


def read_cstring(data: bytes, addr: int, base: int = ARM9_BASE) -> bytes:
    off = addr - base
    end = data.index(b"\x00", off)
    return data[off:end]
