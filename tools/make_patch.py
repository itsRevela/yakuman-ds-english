"""Create (and verify) a BPS patch from the original ROM to the translated ROM.

BPS is the format used by Floating IPS, beat and Rom Patcher JS. Spec (byuu): "BPS1", varint
source size, target size, metadata size, metadata, then actions until the 12-byte footer
(CRC32 of source, target and of the patch itself). Actions: varint ((length - 1) << 2 | command)
    0 SourceRead   copy from the source at the current output offset
    1 TargetRead   literal bytes follow
    2 SourceCopy   signed varint delta of the source cursor follows, then copy from there
    3 TargetCopy   (not emitted)

The encoder is greedy: at each target position it takes the longest of a same-offset source
match, a match continuing the previous copy's offset, and a match found through an index of
32-byte source blocks; anything else becomes literal bytes. The dsd rebuild shifts most files,
so the block index is what keeps the patch small.

Usage: python tools/make_patch.py [--publish] [SOURCE_ROM] [TARGET_ROM] [OUT.bps]
    --publish   also copy the patch to patch/ with its manifest (tools/patch_manifest.py), for
                the release workflow; commit patch/ afterwards
"""
from __future__ import annotations

import sys
import zlib
from pathlib import Path

from romdata import ROOT

BLOCK = 32          # index key length and source sampling step
MIN_COPY = 16       # shortest SourceCopy worth its offset bytes
MIN_READ = 4        # shortest same-offset SourceRead
DEFAULT_SOURCE = ROOT / "Yakuman DS (Japan).nds"
DEFAULT_TARGET = ROOT / "out" / "Yakuman DS (English).nds"
DEFAULT_OUT = ROOT / "out" / "Yakuman DS (English).bps"


class PatchError(ValueError):
    pass


def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        x = n & 0x7F
        n >>= 7
        if n == 0:
            out.append(0x80 | x)
            return bytes(out)
        out.append(x)
        n -= 1


def match_length(a: bytes, ai: int, b: bytes, bi: int) -> int:
    """Length of the common prefix of a[ai:] and b[bi:] (compared in shrinking chunks)."""
    limit = min(len(a) - ai, len(b) - bi)
    n, step = 0, 4096
    while n < limit:
        size = min(step, limit - n)
        if a[ai + n:ai + n + size] == b[bi + n:bi + n + size]:
            n += size
        elif size > 1:
            step = size // 2
        else:
            break
    return n


def build_index(source: bytes) -> dict[bytes, int]:
    index: dict[bytes, int] = {}
    for p in range(0, len(source) - BLOCK + 1, BLOCK):
        index.setdefault(source[p:p + BLOCK], p)
    return index


def encode_bps(source: bytes, target: bytes) -> bytes:
    index = build_index(source)
    out = bytearray(b"BPS1" + varint(len(source)) + varint(len(target)) + varint(0))
    literal = bytearray()
    src_cursor = 0          # BPS sourceRelativeOffset
    delta = 0               # target -> source offset of the last copy
    i = 0

    def flush() -> None:
        if literal:
            out.extend(varint((len(literal) - 1) << 2 | 1))
            out.extend(literal)
            literal.clear()

    while i < len(target):
        best_len, best_pos = 0, None                       # best_pos None = SourceRead
        if i < len(source):
            best_len = match_length(source, i, target, i)
        candidates = [i + delta]
        hit = index.get(target[i:i + BLOCK])
        if hit is not None:
            candidates.append(hit)
        for p in candidates:
            if 0 <= p < len(source) and p != i:
                n = match_length(source, p, target, i)
                if n > best_len:
                    best_len, best_pos = n, p
        if best_pos is None and best_len >= MIN_READ:
            flush()
            out.extend(varint((best_len - 1) << 2 | 0))
            i += best_len
        elif best_pos is not None and best_len >= MIN_COPY:
            back = 0                                       # pull matching literal bytes into the copy
            while back < len(literal) and best_pos - back > 0 and \
                    source[best_pos - back - 1] == target[i - back - 1]:
                back += 1
            if back:
                del literal[len(literal) - back:]
            flush()
            start, length = best_pos - back, best_len + back
            move = start - src_cursor
            out.extend(varint((length - 1) << 2 | 2))
            out.extend(varint(abs(move) << 1 | (move < 0)))
            src_cursor = start + length
            delta = best_pos - i
            i += best_len
        else:
            literal.append(target[i])
            i += 1
    flush()
    out.extend(zlib.crc32(source).to_bytes(4, "little"))
    out.extend(zlib.crc32(target).to_bytes(4, "little"))
    out.extend(zlib.crc32(out).to_bytes(4, "little"))
    return bytes(out)


def apply_bps(source: bytes, patch: bytes) -> bytes:
    if patch[:4] != b"BPS1" or len(patch) < 16:
        raise PatchError("not a BPS patch")
    if zlib.crc32(patch[:-4]) != int.from_bytes(patch[-4:], "little"):
        raise PatchError("patch checksum mismatch")
    if zlib.crc32(source) != int.from_bytes(patch[-12:-8], "little"):
        raise PatchError("source checksum mismatch (wrong ROM?)")
    pos = 4

    def number() -> int:
        nonlocal pos
        data, shift = 0, 1
        while True:
            x = patch[pos]
            pos += 1
            data += (x & 0x7F) * shift
            if x & 0x80:
                return data
            shift <<= 7
            data += shift

    if number() != len(source):
        raise PatchError("source size mismatch")
    target = bytearray(number())
    metadata_size = number()                               # read before moving pos past it
    pos += metadata_size
    out = src_rel = tgt_rel = 0
    end = len(patch) - 12
    while pos < end:
        data = number()
        command, length = data & 3, (data >> 2) + 1
        if command == 0:
            target[out:out + length] = source[out:out + length]
        elif command == 1:
            target[out:out + length] = patch[pos:pos + length]
            pos += length
        else:
            d = number()
            offset = -(d >> 1) if d & 1 else d >> 1
            if command == 2:
                src_rel += offset
                target[out:out + length] = source[src_rel:src_rel + length]
                src_rel += length
            else:
                tgt_rel += offset
                for k in range(length):                    # may overlap the bytes being written
                    target[out + k] = target[tgt_rel + k]
                tgt_rel += length
        out += length
    if out != len(target) or zlib.crc32(target) != int.from_bytes(patch[-8:-4], "little"):
        raise PatchError("target checksum mismatch after applying the patch")
    return bytes(target)


def main(argv: list[str]) -> int:
    publish = "--publish" in argv
    argv = [a for a in argv if a != "--publish"]
    source_path = Path(argv[0]) if len(argv) > 0 else DEFAULT_SOURCE
    target_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_TARGET
    out_path = Path(argv[2]) if len(argv) > 2 else DEFAULT_OUT
    source, target = source_path.read_bytes(), target_path.read_bytes()
    patch = encode_bps(source, target)
    if apply_bps(source, patch) != target:
        raise PatchError("patch does not reproduce the target")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(patch)
    print(f"wrote {out_path} ({len(patch):,} bytes); verified against {target_path.name}")
    if publish:
        import patch_manifest

        manifest = patch_manifest.publish(ROOT, patch)
        print(f"published {patch_manifest.PATCH_DIR}/{manifest['patch']} "
              f"(inputs {manifest['inputs_sha256'][:12]}); commit patch/ to release it")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
