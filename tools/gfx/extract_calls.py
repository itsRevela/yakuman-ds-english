"""List the sprite draw calls (func_0206f82c) of an ARM function from the dsd disassembly.

For every call it reports the sprite expression (texture*1000+region, optionally + a register for
runtime digits), and the addresses/values of the `mov r2, #x` / `mov r3, #y` instructions that set
its position, so positions can be patched. Addresses are recomputed from the listing and checked
against the ARM9 binary.

Usage: python tools/gfx/extract_calls.py FUNC_ADDR   (e.g. 02040698) -> JSON on stdout
"""
from __future__ import annotations

import json
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from romdata import ARM9_BASE, WORK, load_arm9  # noqa: E402

LISTING = WORK / "asm" / "_dsd_gap@main_0.s"
DRAW = "func_0206f82c"
INSN = re.compile(r"^\s{4}(?!\.)(\w+)")
WORD = re.compile(r"^(\.L_\w+): \.word (\S+)")
LABEL = re.compile(r"^(\.L_\w+):\s*(;.*)?$")


def function_lines(name: str) -> list[str]:
    lines = LISTING.read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(f"{name}:"))
    end = next(i for i in range(start, len(lines)) if f"arm_func_end {name}" in lines[i])
    return lines[start + 1:end]


def mov_imm(word: int) -> tuple[int, int] | None:
    """(rd, value) for `mov rd, #imm` (cond AL), else None."""
    if word & 0xFFF00000 != 0xE3A00000:
        return None
    rot = (word >> 8) & 0xF
    imm = word & 0xFF
    value = ((imm >> (2 * rot)) | (imm << (32 - 2 * rot))) & 0xFFFFFFFF if rot else imm
    return (word >> 12) & 0xF, value


def extract(func_addr: int) -> list[dict]:
    a9 = load_arm9()
    name = f"func_{func_addr:08x}"
    body = function_lines(name)
    addr = func_addr
    pool: dict[str, int] = {}
    entries: list[tuple[int, str]] = []
    for line in body:
        if WORD.match(line):
            label, value = WORD.match(line).groups()
            pool[label] = int(value, 0) if value.startswith("0x") else 0
            entries.append((addr, line.strip()))
            addr += 4
        elif LABEL.match(line):
            entries.append((-1, line.strip()))
        elif INSN.match(line):
            entries.append((addr, line.strip()))
            addr += 4

    calls = []
    block = None
    regs: dict[str, object] = {}
    pos: dict[int, tuple[int, int]] = {}
    for a, text in entries:
        if a < 0:
            block = text.split(":")[0]
            regs, pos = {}, {}
            continue
        word = struct.unpack_from("<I", a9, a - ARM9_BASE)[0]
        m = re.match(r"ldr (r\d+), (\.L_\w+)$", text)
        if m and m.group(2) in pool:
            regs[m.group(1)] = pool[m.group(2)]
        m = re.match(r"add (r\d+), (r\d+), (r\d+)$", text)
        if m:
            a_, b_ = regs.get(m.group(2)), regs.get(m.group(3))
            if isinstance(b_, int) and b_ >= 1000:
                regs[m.group(1)] = (b_, m.group(2))
            elif isinstance(a_, int) and a_ >= 1000:
                regs[m.group(1)] = (a_, m.group(3))
        mi = mov_imm(word)
        if text.startswith("mov ") and mi is not None:
            rd, value = mi
            regs[f"r{rd}"] = value
            pos[rd] = (a, value)
        if f"bl {DRAW}" in text:
            sprite = regs.get("r1")
            if isinstance(sprite, tuple):
                expr = {"sprite": sprite[0], "plus": sprite[1]}
            elif isinstance(sprite, int):
                expr = {"sprite": sprite}
            else:
                expr = {"sprite": None}
            x_addr, x = pos.get(2, (None, None))
            y_addr, y = pos.get(3, (None, None))
            calls.append({"block": block, "call": f"{a:08x}", **expr,
                          "x": x, "x_addr": f"{x_addr:08x}" if x_addr else None,
                          "y": y, "y_addr": f"{y_addr:08x}" if y_addr else None})
            regs.pop("r1", None)
            pos.pop(2, None)
            pos.pop(3, None)
    return calls


if __name__ == "__main__":
    print(json.dumps(extract(int(sys.argv[1], 16)), indent=1))
