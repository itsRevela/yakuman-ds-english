import random
import zlib

import pytest

from make_patch import PatchError, apply_bps, encode_bps, varint


def sample(seed: int, size: int) -> bytes:
    rng = random.Random(seed)
    return bytes(rng.getrandbits(8) for _ in range(size))


def test_varint_matches_beat_encoding():
    assert varint(0) == b"\x80"
    assert varint(127) == b"\xff"
    assert varint(128) == b"\x00\x80"


def test_round_trip_with_edits_and_relocated_data():
    source = sample(1, 20000)
    target = bytearray(source)
    target[100:110] = b"English!!!"                       # edited in place
    target[5000:9000] = source[12000:16000]                # data moved from elsewhere
    target += sample(2, 300)                               # grown
    patch = encode_bps(source, bytes(target))
    assert apply_bps(source, patch) == bytes(target)


def test_relocated_data_is_copied_not_stored():
    source = sample(3, 50000)
    target = source[25000:] + source[:25000]               # same bytes, shifted
    assert len(encode_bps(source, target)) < 500


def test_round_trip_when_target_is_shorter():
    source = sample(4, 5000)
    target = source[:3000]
    assert apply_bps(source, encode_bps(source, target)) == target


def test_patch_header_and_footer_checksums():
    source, target = sample(5, 1000), sample(6, 1000)
    patch = encode_bps(source, target)
    assert patch[:4] == b"BPS1"
    assert int.from_bytes(patch[-12:-8], "little") == zlib.crc32(source)
    assert int.from_bytes(patch[-8:-4], "little") == zlib.crc32(target)
    assert int.from_bytes(patch[-4:], "little") == zlib.crc32(patch[:-4])


def test_apply_rejects_the_wrong_source():
    source, target = sample(7, 1000), sample(8, 1000)
    patch = encode_bps(source, target)
    with pytest.raises(PatchError):
        apply_bps(sample(9, 1000), patch)
