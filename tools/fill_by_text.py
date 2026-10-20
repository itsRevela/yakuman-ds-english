"""Fill a category from a Japanese->English mapping (useful when the same line repeats).

The mapping file is a TSV of <japanese>\t<english>[\t<json options>] lines; "\\n" is a newline in
both columns and "!" in the Japanese column is the game's own newline code, so lines can be pasted
exactly as they appear in the catalog. Entries already translated are left alone unless --force.

Usage: python tools/fill_by_text.py <category> <mapping.tsv> [--force]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fill_text import fill
from insert_text import TEXT_DIR


def load_mapping(path: Path) -> dict[str, tuple[str, dict]]:
    mapping: dict[str, tuple[str, dict]] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("# ") or line.strip() == "#":
            continue
        parts = line.split("\t")
        if len(parts) not in (2, 3):
            raise ValueError(f"{path}:{n}: expected 2 or 3 tab-separated columns")
        ja = parts[0].replace("\\n", "\n")
        if ja in mapping:
            raise ValueError(f"{path}:{n}: duplicate Japanese key {ja!r}")
        mapping[ja] = (parts[1].replace("\\n", "\n"), json.loads(parts[2]) if len(parts) == 3 else {})
    return mapping


def main(argv: list[str]) -> int:
    force = "--force" in argv
    args = [a for a in argv if a != "--force"]
    if len(args) != 2:
        print(__doc__)
        return 2
    category, mapping = args[0], load_mapping(Path(args[1]))
    doc = json.loads((TEXT_DIR / f"{category}.json").read_text(encoding="utf-8"))
    rows, missing, used = [], [], set()
    for e in doc["entries"]:
        if e["ja"] in mapping:
            used.add(e["ja"])
        if e.get("en") and not force:
            continue
        if e["ja"] in mapping:
            en, opts = mapping[e["ja"]]
            rows.append((e["addr"], en, opts))
        elif e.get("note") != "data?":
            missing.append(e)
    fill(category, rows)
    print(f"{category}: {len(rows)} filled, {len(missing)} still untranslated, "
          f"{len(set(mapping) - used)} unused mapping keys")
    for e in missing:
        print(f"  missing {e['addr']}: {e['ja']!r}")
    for ja in sorted(set(mapping) - used):
        print(f"  unused: {ja!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
