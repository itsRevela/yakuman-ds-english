"""Create/refresh translation skeletons text/<category>.json from work/catalog.json.

Existing English (and options/notes) in a file are preserved; new catalogue strings in the
category's address range are added with an empty "en". Strings that look like binary data
rather than text are marked with "note": "data?" so they are skipped unless translated.

Usage: python tools/export_text.py [category ...]
"""
from __future__ import annotations

import json
import re
import sys

from insert_text import TEXT_DIR, load_catalog

# (name, first address, end address (exclusive), description)
CATEGORIES = [
    ("stats", 0x020E9C00, 0x020EA4A0, "Records screen: stat labels (dot-padded) and value units."),
    ("characters", 0x020EAEE0, 0x020EB0C0, "Character names (two lists) and the locked placeholder."),
    ("menus", 0x020EB440, 0x020ECE20, "Continue/new game, options, rule settings."),
    ("tutorial", 0x020F2300, 0x020F4A00, "Mahjong Basics tutorial (麻雀入門)."),
    ("glossary", 0x020F6100, 0x02100910, "Mahjong dictionary: terms, readings, descriptions."),
    ("scoring", 0x02100A80, 0x021055C0, "In-game errors, scoring breakdown, round labels, wait checker."),
    ("advice", 0x021055C0, 0x02109200, "In-game advice (Professor Lakitu) and tile-danger hints."),
    ("game_menus", 0x02109200, 0x0210C120, "Yaku targets, game setup, character data."),
    ("system", 0x0210C410, 0x0210CF00, "Save/system dialogs."),
    ("wireless", 0x0210CF00, 0x0210F900, "Wireless play / DS Download Play."),
    ("challenge", 0x0210F900, 0x0210FBE0, "Challenge mode messages."),
]

_HALFWIDTH_ONLY = re.compile(r"^[｡-ﾟ\]a]{1,2}$")


def looks_like_data(ja: str, refs: tuple[int, ...]) -> bool:
    return bool(_HALFWIDTH_ONLY.match(ja))


def export(name: str, lo: int, hi: int, description: str) -> tuple[int, int]:
    catalog = load_catalog()
    path = TEXT_DIR / f"{name}.json"
    existing = {}
    if path.is_file():
        for e in json.loads(path.read_text(encoding="utf-8"))["entries"]:
            existing[e["addr"]] = e
    entries = []
    added = 0
    for addr in sorted(a for a in catalog if lo <= a < hi):
        cs = catalog[addr]
        key = f"{addr:08x}"
        if key in existing:
            entry = existing.pop(key)
            if entry["ja"] != cs.ja:
                raise ValueError(f"{path.name}: {key} Japanese changed in catalog; resolve manually")
        else:
            entry = {"addr": key, "ja": cs.ja, "en": ""}
            if looks_like_data(cs.ja, cs.refs):
                entry["note"] = "data?"
            added += 1
        entries.append(entry)
    if existing:
        raise ValueError(f"{path.name}: entries no longer in catalog range: {sorted(existing)}")
    TEXT_DIR.mkdir(exist_ok=True)
    doc = {"description": description, "entries": entries}
    path.write_text(_dump(doc), encoding="utf-8")
    return len(entries), added


def _dump(doc: dict) -> str:
    """One entry per line keeps diffs readable."""
    lines = ["{", f'  "description": {json.dumps(doc["description"], ensure_ascii=False)},', '  "entries": [']
    body = [f"    {json.dumps(e, ensure_ascii=False)}" for e in doc["entries"]]
    lines.append(",\n".join(body))
    lines += ["  ]", "}", ""]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    wanted = set(argv)
    unknown = wanted - {c[0] for c in CATEGORIES}
    if unknown:
        print(f"unknown categories: {sorted(unknown)}", file=sys.stderr)
        return 2
    for name, lo, hi, desc in CATEGORIES:
        if wanted and name not in wanted:
            continue
        total, added = export(name, lo, hi, desc)
        print(f"{name}: {total} entries ({added} new)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
