"""Merge translations from a simple tab-separated list into text/<category>.json.

Input lines:  <addr>\t<english>[\t<json options>]
  - "\\n" in the English is a line break (stored as a real newline in the JSON).
  - Options (optional third column) is a JSON object merged into the entry, e.g. {"center": 36}.
  - Blank lines and lines starting with "# " (hash + space) are ignored.

Usage: python tools/fill_text.py <category> <tsv file>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from export_text import _dump
from insert_text import TEXT_DIR


def parse_lines(text: str) -> list[tuple[str, str, dict]]:
    rows = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("# ") or line.strip() == "#":
            continue
        parts = line.split("\t")
        if len(parts) not in (2, 3):
            raise ValueError(f"line {n}: expected 2 or 3 tab-separated columns: {line!r}")
        addr = parts[0].strip().lower()
        int(addr, 16)  # validate
        en = parts[1].replace("\\n", "\n")
        opts = json.loads(parts[2]) if len(parts) == 3 else {}
        if not isinstance(opts, dict):
            raise ValueError(f"line {n}: options must be a JSON object")
        rows.append((addr, en, opts))
    return rows


def fill(category: str, rows: list[tuple[str, str, dict]]) -> int:
    path = TEXT_DIR / f"{category}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    by_addr = {e["addr"]: e for e in doc["entries"]}
    for addr, en, opts in rows:
        if addr not in by_addr:
            raise KeyError(f"{path.name}: no entry {addr}")
        entry = by_addr[addr]
        entry["en"] = en
        entry.pop("note", None) if entry.get("note") == "data?" else None
        entry.update(opts)
    path.write_text(_dump(doc), encoding="utf-8")
    return len(rows)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    n = fill(argv[0], parse_lines(Path(argv[1]).read_text(encoding="utf-8")))
    print(f"{argv[0]}: {n} translations merged")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
