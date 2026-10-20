import struct

import pytest

from insert_text import CatalogString, Entry, TranslationError, insert, validate
from romdata import ARM9_BASE

STR_A = ARM9_BASE + 0x100   # slot of 8 bytes
STR_B = ARM9_BASE + 0x108   # slot of 8 bytes
PTR_A = ARM9_BASE + 0x10
PTR_A2 = ARM9_BASE + 0x14
PTR_B = ARM9_BASE + 0x18
TEXT_START = ARM9_BASE + 0x200


@pytest.fixture
def rom(tmp_path):
    data = bytearray(0x180)
    struct.pack_into("<III", data, 0x10, STR_A, STR_A, STR_B)
    data[0x100:0x108] = "ロン".encode("cp932") + bytes(4)
    data[0x108:0x110] = "ポン".encode("cp932") + bytes(4)
    path = tmp_path / "arm9.bin"
    path.write_bytes(bytes(data))
    catalog = {
        STR_A: CatalogString(STR_A, 8, "ロン", (PTR_A, PTR_A2)),
        STR_B: CatalogString(STR_B, 8, "ポン", (PTR_B,)),
    }
    return path, catalog


def word(data, addr):
    return struct.unpack_from("<I", data, addr - ARM9_BASE)[0]


def test_short_translation_is_written_in_place(rom):
    path, catalog = rom
    insert(path, TEXT_START, catalog=catalog, entries=[Entry(STR_A, "ロン", "Ron", "t")], verbose=False)
    data = path.read_bytes()
    assert data[0x100:0x108] == b"Ron\x00\x00\x00\x00\x00"
    assert word(data, PTR_A) == STR_A


def test_long_translation_is_relocated_and_all_pointers_rewritten(rom):
    path, catalog = rom
    end = insert(path, TEXT_START, catalog=catalog, entries=[Entry(STR_A, "ロン", "Ron (win)", "t")], verbose=False)
    data = path.read_bytes()
    assert word(data, PTR_A) == TEXT_START and word(data, PTR_A2) == TEXT_START
    assert data[0x200:0x20A] == b"Ron (win)\x00"
    assert end == TEXT_START + 12  # 10 bytes padded to 4-byte alignment


def test_identical_relocated_strings_are_shared(rom):
    path, catalog = rom
    entries = [Entry(STR_A, "ロン", "Same long text", "t"), Entry(STR_B, "ポン", "Same long text", "t")]
    insert(path, TEXT_START, catalog=catalog, entries=entries, verbose=False)
    data = path.read_bytes()
    assert word(data, PTR_A) == word(data, PTR_B) == TEXT_START


def test_japanese_mismatch_is_rejected(rom):
    path, catalog = rom
    with pytest.raises(TranslationError, match="does not match"):
        insert(path, TEXT_START, catalog=catalog, entries=[Entry(STR_A, "ポン", "Pon", "t")], verbose=False)


def test_pointer_that_no_longer_matches_is_rejected(rom):
    path, catalog = rom
    data = bytearray(path.read_bytes())
    struct.pack_into("<I", data, 0x14, 0xDEADBEEF)
    path.write_bytes(bytes(data))
    with pytest.raises(TranslationError, match="pointer"):
        insert(path, TEXT_START, catalog=catalog, entries=[Entry(STR_A, "ロン", "Ron (win)", "t")], verbose=False)


def test_printf_specifiers_must_match():
    original = CatalogString(STR_A, 8, "%2d符", ())
    with pytest.raises(TranslationError, match="printf"):
        validate(Entry(STR_A, "%2d符", "%d fu", "t"), original)


def test_printf_specifiers_accepted_when_equal():
    original = CatalogString(STR_A, 8, "%2d符", ())
    assert validate(Entry(STR_A, "%2d符", "%2d fu", "t"), original) == b"%2d fu"


def test_highlight_count_must_match():
    original = CatalogString(STR_A, 32, "<ドラ>と<裏ドラ>", ())
    with pytest.raises(TranslationError, match="highlight"):
        validate(Entry(STR_A, original.ja, "{Dora} and Ura Dora", "t"), original)


def test_highlights_encode_to_control_codes():
    original = CatalogString(STR_A, 32, "<ドラ>", ())
    assert validate(Entry(STR_A, "<ドラ>", "{Dora}!", "t"), original) == b"<Dora>\xa1"


def test_tile_placeholder_count_must_match():
    original = CatalogString(STR_A, 32, "ΠとΠ", ())
    with pytest.raises(TranslationError, match="Π"):
        validate(Entry(STR_A, original.ja, "Π and tiles", "t"), original)


def test_instant_toggle_count_must_match():
    original = CatalogString(STR_A, 32, "#あ#!い", ())
    with pytest.raises(TranslationError, match="instant"):
        validate(Entry(STR_A, original.ja, "a\nb", "t"), original)


def test_max_bytes_rejects_text_that_overflows_a_copy_buffer():
    # the game strcpy's this string into a 12-byte buffer: 13 chars + NUL do not fit
    original = CatalogString(STR_A, 12, "ルール設定", ())
    with pytest.raises(TranslationError, match="overflow"):
        validate(Entry(STR_A, original.ja, "Rule Settings", "t", (("max_bytes", 12),)), original)


def test_max_bytes_counts_the_terminator():
    # 12 characters fill the 12 bytes, leaving no room for the NUL
    original = CatalogString(STR_A, 12, "ルール設定", ())
    with pytest.raises(TranslationError, match="overflow"):
        validate(Entry(STR_A, original.ja, "Rule Listxyz", "t", (("max_bytes", 12),)), original)


def test_max_bytes_accepts_text_that_fits_with_its_terminator():
    original = CatalogString(STR_A, 12, "ルール設定", ())
    assert validate(Entry(STR_A, original.ja, "Rule Listxx", "t", (("max_bytes", 12),)), original) == b"Rule Listxx"
