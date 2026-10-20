"""Insert English translations into arm9.bin.

Translation files: text/*.json, each {"entries": [{"addr": "020eb448", "ja": "...", "en": "..."}, ...]}.
An entry with a missing/empty "en" is left untranslated.

For every translated string:
  * the "ja" field must match the ROM string at "addr" exactly (guards against stale files);
  * if the encoded text fits the original slot it is written in place, otherwise it is appended
    to the extension region and every pointer to the original is rewritten;
  * printf conversion specifiers and the number of {highlights} must match the Japanese.

Optional per-entry layout keys (pixel widths, measured with the VWF font):
  "center": W   pad with spaces on both sides to centre the text in W pixels
  "leader": W   append '.' leader dots until the line is W pixels wide
  "pad": W      append spaces (inside a trailing {highlight}) until the text is W pixels wide
  "max": W      only check that no line is wider than W pixels
  "wrap": W     insert line breaks at spaces so no line is wider than W pixels (for screens that
                lay text out themselves, e.g. the dictionary); text must be single-byte only
  "max_bytes": N  the game copies the string into an N-byte buffer: the encoded text plus its
                NUL must fit (relocating the source does not make the destination any larger)
"""
from __future__ import annotations

import json
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import textcodec
import vwf_font
from romdata import ARM9_BASE, ROOT, WORK

TEXT_DIR = ROOT / "text"
CATALOG = WORK / "catalog.json"
ALIGN = 4

_PRINTF_RE = re.compile(r"%[-+ 0#]*\d*(?:\.\d+)?[hlL]?[diouxXscpf%]")


class TranslationError(ValueError):
    pass


LAYOUT_KEYS = ("center", "leader", "pad", "wrap", "max", "max_bytes")


@dataclass(frozen=True)
class Entry:
    addr: int
    ja: str
    en: str
    source: str
    layout: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class CatalogString:
    addr: int
    size: int
    ja: str
    refs: tuple[int, ...]


def load_catalog(path: Path = CATALOG) -> dict[int, CatalogString]:
    if not path.is_file():
        raise TranslationError(f"{path} missing; run tools/scan_strings.py first")
    out = {}
    for c in json.loads(path.read_text(encoding="utf-8")):
        addr = int(c["addr"], 16)
        out[addr] = CatalogString(addr, c["size"], c["ja"], tuple(int(r, 16) for r in c["refs"]))
    return out


def load_entries(text_dir: Path = TEXT_DIR) -> list[Entry]:
    entries: list[Entry] = []
    seen: dict[int, str] = {}
    for path in sorted(text_dir.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for i, e in enumerate(doc.get("entries", [])):
            where = f"{path.name}[{i}]"
            try:
                addr = int(e["addr"], 16)
                ja = e["ja"]
            except (KeyError, ValueError) as exc:
                raise TranslationError(f"{where}: needs hex 'addr' and 'ja'") from exc
            if addr in seen:
                raise TranslationError(f"{where}: address {addr:08x} already translated in {seen[addr]}")
            seen[addr] = where
            en = e.get("en") or ""
            layout = tuple((k, int(e[k])) for k in LAYOUT_KEYS if k in e)
            if en:
                entries.append(Entry(addr, ja, en, where, layout))
    return entries


def validate(entry: Entry, original: CatalogString) -> bytes:
    if entry.ja != original.ja:
        raise TranslationError(f"{entry.source}: 'ja' does not match ROM at {entry.addr:08x}: "
                               f"{entry.ja!r} != {original.ja!r}")
    ja_fmt = _PRINTF_RE.findall(original.ja)
    en_fmt = _PRINTF_RE.findall(entry.en)
    if ja_fmt != en_fmt:
        raise TranslationError(f"{entry.source}: printf specifiers differ: {ja_fmt} vs {en_fmt}")
    if original.ja.count("Π") != entry.en.count("Π"):
        raise TranslationError(f"{entry.source}: tile placeholder Π count {entry.en.count('Π')} must equal "
                               f"the Japanese count {original.ja.count('Π')}")
    if original.ja.count("#") != entry.en.count("^"):
        raise TranslationError(f"{entry.source}: instant-draw ^ count must equal the Japanese # count")
    ja_links = original.ja.count("<")
    en_links = entry.en.count("{")
    if ja_links != en_links or entry.en.count("}") != en_links:
        raise TranslationError(f"{entry.source}: {{highlight}} count {en_links} must equal the Japanese <> count {ja_links}")
    single_byte = any(key == "wrap" for key, _ in entry.layout)
    try:
        data = apply_layout(textcodec.encode(entry.en, allow_fullwidth=not single_byte), entry.layout)
    except textcodec.EncodeError as exc:
        raise TranslationError(f"{entry.source}: {exc}") from exc
    if b"\x00" in data:
        raise TranslationError(f"{entry.source}: NUL byte in encoded text")
    for key, limit in entry.layout:
        if key == "max_bytes" and len(data) + 1 > limit:
            raise TranslationError(f"{entry.source}: {len(data) + 1} bytes with NUL overflow the "
                                   f"{limit}-byte buffer the game copies it into: {data!r}")
    return data


_GLYPHS = None


def _glyphs() -> dict:
    global _GLYPHS
    if _GLYPHS is None:
        _GLYPHS = vwf_font.load_font()
    return _GLYPHS


def _width(data: bytes) -> int:
    return textcodec.line_widths(data, _glyphs())[-1]


def _wrap(data: bytes, limit: int) -> bytes:
    out_lines = []
    for paragraph in data.split(bytes([textcodec.NEWLINE])):
        line = b""
        for word in paragraph.split(b" "):
            candidate = word if not line else line + b" " + word
            if _width(candidate) <= limit or not line:
                line = candidate
            else:
                out_lines.append(line)
                line = word
            if _width(line) > limit:
                raise TranslationError(f"word too wide to wrap at {limit} px: {word!r}")
        out_lines.append(line)
    return bytes([textcodec.NEWLINE]).join(out_lines)


def apply_layout(data: bytes, layout: tuple[tuple[str, int], ...]) -> bytes:
    glyphs = _glyphs()
    space = glyphs[0x20].advance
    for key, target in layout:
        if key not in LAYOUT_KEYS:
            raise TranslationError(f"unknown layout key {key!r}")
        if key == "wrap":
            data = _wrap(data, target)
            continue
        if key == "max_bytes":      # a byte limit, checked in validate()
            continue
        widest = max(textcodec.line_widths(data, _glyphs()))
        if widest > target:
            raise TranslationError(f"text is {widest} px wide, exceeds {key} width {target}: {data!r}")
        if key == "leader":
            dot = glyphs[0x2E].advance
            while _width(data) + dot <= target:
                data += b"."
        elif key == "center":
            spare = target - _width(data)
            if spare >= 2 * space:
                left = (spare // 2 + space // 2) // space
                right = (spare - left * space) // space
                data = b" " * left + data + b" " * right
        elif key == "pad":
            closing = data.endswith(bytes([textcodec.HL_END]))
            body = data[:-1] if closing else data
            while _width(body) + space <= target:
                body += b" "
            data = body + (bytes([textcodec.HL_END]) if closing else b"")
    return data


def insert(arm9_bin: Path, text_start: int, *, catalog: dict[int, CatalogString] | None = None,
           entries: list[Entry] | None = None, verbose: bool = True) -> int:
    """Apply all translations to arm9_bin; returns the end address of the appended text."""
    catalog = load_catalog() if catalog is None else catalog
    entries = load_entries() if entries is None else entries
    data = bytearray(arm9_bin.read_bytes())
    start_off = text_start - ARM9_BASE
    if len(data) > start_off:
        raise TranslationError(f"arm9.bin already extends past the text area ({len(data):#x} > {start_off:#x})")
    data += bytes(start_off - len(data))

    appended: dict[bytes, int] = {}
    in_place = relocated = 0
    for entry in entries:
        original = catalog.get(entry.addr)
        if original is None:
            raise TranslationError(f"{entry.source}: no catalogued string at {entry.addr:08x}")
        encoded = validate(entry, original)
        off = entry.addr - ARM9_BASE
        if len(encoded) + 1 <= original.size:
            data[off : off + original.size] = encoded + bytes(original.size - len(encoded))
            in_place += 1
            continue
        if not original.refs:
            raise TranslationError(f"{entry.source}: too long for its slot ({len(encoded) + 1} > "
                                   f"{original.size}) and has no pointers to relocate")
        new_addr = appended.get(encoded)
        if new_addr is None:
            new_addr = ARM9_BASE + len(data)
            data += encoded + b"\x00"
            data += bytes(-len(data) % ALIGN)
            appended[encoded] = new_addr
        for ref in original.refs:
            ref_off = ref - ARM9_BASE
            (current,) = struct.unpack_from("<I", data, ref_off)
            if current != entry.addr:
                raise TranslationError(f"{entry.source}: pointer at {ref:08x} is {current:08x}, expected {entry.addr:08x}")
            struct.pack_into("<I", data, ref_off, new_addr)
        # Leave a visible marker in the old slot so stray users of the old address are obvious.
        data[off : off + original.size] = b"?" + bytes(original.size - 1)
        relocated += 1

    arm9_bin.write_bytes(bytes(data))
    end = ARM9_BASE + len(data)
    if verbose:
        print(f"text: {len(entries)} translated ({in_place} in place, {relocated} relocated, "
              f"{len(appended)} unique appended), {end - text_start} bytes appended")
    return end


if __name__ == "__main__":
    # Validation-only run: checks every translation file against the catalog.
    cat = load_catalog()
    errors = 0
    for ent in load_entries():
        try:
            if ent.addr not in cat:
                raise TranslationError(f"{ent.source}: no catalogued string at {ent.addr:08x}")
            validate(ent, cat[ent.addr])
        except TranslationError as exc:
            print(exc, file=sys.stderr)
            errors += 1
    print(f"{errors} error(s)")
    sys.exit(1 if errors else 0)
