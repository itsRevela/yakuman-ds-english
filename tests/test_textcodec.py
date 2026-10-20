import pytest

from textcodec import EncodeError, decode, encode, line_widths
from vwf_font import load_font


def test_plain_ascii_is_unchanged():
    assert encode("Riichi") == b"Riichi"


def test_newline_becomes_bang_control_code():
    assert encode("a\nb") == b"a!b"


def test_literal_exclamation_is_remapped_away_from_newline():
    assert encode("Ron!") == b"Ron\xa1"


def test_highlight_markup():
    assert encode("{Dora}") == b"<Dora>"


def test_literal_angle_brackets_and_hash_are_remapped():
    assert encode("<#>") == b"\xbc\xa3\xbe"


def test_fullwidth_fallback_uses_shift_jis():
    assert encode("Π") == "Π".encode("cp932")


def test_fullwidth_fallback_can_be_disallowed():
    with pytest.raises(EncodeError):
        encode("麻", allow_fullwidth=False)


def test_unencodable_character_raises():
    with pytest.raises(EncodeError):
        encode("😀")


@pytest.mark.parametrize("text", ["Ron!", "{Riichi} wins\nnext", "Pokémon… “hi” ×3", "ΠΠ and ^instant^"])
def test_decode_round_trips(text):
    assert decode(encode(text)) == text


def test_line_widths_skip_control_codes_and_split_lines():
    glyphs = load_font()
    widths = line_widths(encode("{ab}\n1"), glyphs)
    assert widths == [glyphs[ord("a")].advance + glyphs[ord("b")].advance, 6]


def test_line_widths_count_fullwidth_as_12px():
    assert line_widths(encode("Π"), load_font()) == [12]


def test_line_widths_empty_string():
    assert line_widths(b"", load_font()) == [0]
