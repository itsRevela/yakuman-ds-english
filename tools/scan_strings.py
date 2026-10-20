"""Catalog every Shift-JIS string in the ARM9 binary together with the relocations that point at it.

Output: work/catalog.json, a list of
    {"addr", "size" (bytes incl. NUL + padding to next object), "ja", "refs": [src addrs], "unreferenced": bool}
plus a human-readable summary on stdout.
"""
from __future__ import annotations

import bisect
import json
import re
import sys

from romdata import ARM9_BASE, WORK, Reloc, load_arm9, load_relocs

# Text data lives after code; anything before this is instructions/literal pools.
DATA_START = 0x020DA000
DATA_END = 0x0210FBE0
# Font index tables + glyph bitmaps (glyph headers are SJIS codes and look like strings).
FONT_RANGES = ((0x020DAD90, 0x020E94FE),)

# A plausible game string: printable ASCII, half-width katakana, or a 2-byte SJIS code from the rows the font supports.
_STR_RE = re.compile(rb"(?:[\x0a\x20-\x7e\xa1-\xdf]|[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc])+\x00")
_JA_RE = re.compile(r"[　-ヿ一-鿿！-～｡-ﾟ]")
# Unreferenced candidates are only kept if they look like real prose (full-width Japanese).
_FULLWIDTH_JA_RE = re.compile(r"[ぁ-ヿ一-鿿]")
MIN_UNREFERENCED_JA_CHARS = 2


def find_candidates(a9: bytes) -> dict[int, bytes]:
    lo, hi = DATA_START - ARM9_BASE, DATA_END - ARM9_BASE
    found = {}
    for m in _STR_RE.finditer(a9, lo, hi):
        addr = m.start() + ARM9_BASE
        if any(f_lo <= addr < f_hi for f_lo, f_hi in FONT_RANGES):
            continue
        raw = m.group()[:-1]
        try:
            text = raw.decode("cp932")
        except UnicodeDecodeError:
            continue
        if _JA_RE.search(text):
            found[addr] = raw
    return found


def split_at_pointers(candidates: dict[int, bytes], relocs: list[Reloc]) -> dict[int, bytes]:
    """A candidate may have swallowed stray bytes in front of the real string; if a pointer
    lands inside it, the pointer target is the true start."""
    starts = sorted(candidates)
    result = dict(candidates)
    for r in relocs:
        if r.dst in candidates:
            continue
        i = bisect.bisect_right(starts, r.dst) - 1
        if i < 0:
            continue
        s = starts[i]
        raw = candidates[s]
        if s < r.dst < s + len(raw):
            result[r.dst] = raw[r.dst - s :]
            # Drop the swallowed prefix unless something points at it too.
            result.pop(s, None)
    return result


def main() -> int:
    a9 = load_arm9()
    relocs = load_relocs()
    strings = split_at_pointers(find_candidates(a9), relocs)

    refs: dict[int, list[int]] = {a: [] for a in strings}
    for r in relocs:
        if r.dst in refs:
            refs[r.dst].append(r.src)

    starts = sorted(a for a in strings if refs[a] or _is_prose(strings[a]))

    catalog = []
    for i, a in enumerate(starts):
        raw = strings[a]
        # Usable slot = up to the next string start or next 4-byte boundary after the NUL, whichever is smaller.
        end = a + len(raw) + 1
        slot_end = (end + 3) & ~3
        if i + 1 < len(starts):
            slot_end = min(slot_end, starts[i + 1])
        catalog.append(
            {
                "addr": f"{a:08x}",
                "size": slot_end - a,
                "ja": raw.decode("cp932"),
                "refs": [f"{s:08x}" for s in refs[a]],
                "unreferenced": not refs[a],
            }
        )

    out = WORK / "catalog.json"
    out.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")

    unref = [c for c in catalog if c["unreferenced"]]
    multi = [c for c in catalog if len(c["refs"]) > 1]
    print(f"strings: {len(catalog)}  bytes: {sum(len(c['ja'].encode('cp932')) for c in catalog)}")
    print(f"directly referenced: {len(catalog) - len(unref)}  unreferenced (kept for review): {len(unref)}")
    print(f"multi-ref: {len(multi)}")
    print(f"wrote {out}")
    return 0


def _is_prose(raw: bytes) -> bool:
    return len(_FULLWIDTH_JA_RE.findall(raw.decode("cp932"))) >= MIN_UNREFERENCED_JA_CHARS


if __name__ == "__main__":
    sys.exit(main())
