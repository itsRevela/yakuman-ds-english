"""Print a function from the dsd disassembly with an absolute address on every instruction.

dsd only labels functions and branch targets; patches need exact instruction addresses. Each
instruction / .word is 4 bytes (ARM). Addresses are cross-checked against relocation sources
(every `bl` to a known function must have a relocation at the computed address).

Usage: python tools/asm_addr.py 020209b0 [020209b0 ...]
"""
from __future__ import annotations

import re
import sys

from romdata import WORK, load_relocs

ASM = WORK / "asm" / "_dsd_gap@main_0.s"
_FUNC_RE = re.compile(r"^(func_[0-9a-f]{8}): ; 0x([0-9a-f]{8})")
_SKIP_RE = re.compile(r"^\s*(\.global|arm_func_start|arm_func_end|thumb_func_start|thumb_func_end|\.balign|\.align)\b")


def annotate(func: str) -> list[tuple[int, str]]:
    lines = ASM.read_text(encoding="utf-8").splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith(f"func_{func}:")), None)
    if start is None:
        raise KeyError(f"func_{func} not found in {ASM}")
    addr = int(func, 16)
    out = []
    for line in lines[start + 1 :]:
        if line.strip().startswith("arm_func_end"):
            break
        if not line.strip() or _SKIP_RE.match(line):
            continue
        if re.match(r"^\.?L?_?[0-9A-Za-z_]+:", line.strip()) and not line.strip().startswith(".word"):
            label, _, rest = line.strip().partition(":")
            out.append((addr, f"{label}:"))
            rest = rest.split(";")[0].strip()
            if rest.startswith(".word"):
                out.append((addr, "    " + rest))
                addr += 4
            continue
        out.append((addr, line))
        addr += 4
    return out


def main(argv: list[str]) -> int:
    reloc_srcs = {r.src: r for r in load_relocs()}
    for func in argv:
        bad = 0
        for addr, text in annotate(func.lower().removeprefix("func_").removeprefix("0x")):
            m = re.search(r"\bbl (func_[0-9a-f]{8})", text)
            mark = ""
            if m:
                r = reloc_srcs.get(addr)
                ok = r is not None and f"{r.dst:08x}" == m.group(1)[5:]
                mark = "" if ok else "   <-- ADDRESS MISMATCH"
                bad += not ok
            if text.endswith(":"):
                print(f"          {text}")
            else:
                print(f"{addr:08x}  {text.strip()}{mark}")
        if bad:
            print(f"!! {bad} bl instructions did not match relocations", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
