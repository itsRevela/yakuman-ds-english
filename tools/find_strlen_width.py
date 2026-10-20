"""List every strlen() call (func_020186f8) and the instructions after it, flagging likely
"length * 6 px" text-width computations that need the VWF width function instead.

Usage: python tools/find_strlen_width.py [--all]
"""
from __future__ import annotations

import re
import sys

from asm_addr import ASM, annotate
from romdata import load_relocs

STRLEN = 0x020186F8
WINDOW = 6
_SIX = re.compile(r"#0x6\b|#0xc\b|lsl #0x1\b")


def function_starts() -> list[int]:
    out = []
    for line in ASM.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^func_([0-9a-f]{8}):", line)
        if m:
            out.append(int(m.group(1), 16))
    return sorted(out)


def main(argv: list[str]) -> int:
    show_all = "--all" in argv
    starts = function_starts()
    calls = sorted(r.src for r in load_relocs() if r.dst == STRLEN)
    cache: dict[int, list[tuple[int, str]]] = {}
    flagged = 0
    for src in calls:
        func = max(s for s in starts if s <= src)
        if func not in cache:
            cache[func] = annotate(f"{func:08x}")
        lines = cache[func]
        idx = next(i for i, (a, t) in enumerate(lines) if a == src and "bl " in t)
        after = [t.strip() for _, t in lines[idx + 1 : idx + 1 + WINDOW] if not t.endswith(":")]
        hit = any(_SIX.search(t) for t in after)
        flagged += hit
        if hit or show_all:
            print(f"{src:08x} (func_{func:08x}) {'WIDTH?' if hit else ''}")
            for t in after:
                print(f"      {t}")
    print(f"{len(calls)} strlen calls, {flagged} look like width computations", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
