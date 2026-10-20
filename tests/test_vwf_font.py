import pytest

from vwf_font import FALLBACK, ROWS, FontError, load_font, parse_font, to_binary

MINIMAL = """
@ 3F
1 .##.
2 #..#
@ 41 adv=7
1 #.#
"""


def test_row_bits_are_msb_first():
    glyphs = parse_font(MINIMAL)
    assert glyphs[0x3F].rows[1] == 0b0110_0000
    assert glyphs[0x3F].rows[2] == 0b1001_0000


def test_default_advance_is_width_plus_one():
    assert parse_font(MINIMAL)[0x3F].advance == 5


def test_explicit_advance_overrides_default():
    assert parse_font(MINIMAL)[0x41].advance == 7


def test_unlisted_rows_are_blank():
    glyph = parse_font(MINIMAL)[0x41]
    assert glyph.rows[0] == 0 and glyph.rows[ROWS - 1] == 0


def test_binary_layout_and_fallback_for_missing_bytes():
    data = to_binary(parse_font(MINIMAL))
    assert len(data) == 256 + 256 * ROWS
    assert data[0x42] == data[FALLBACK]  # 'B' undefined -> '?'
    assert data[256 + 0x42 * ROWS : 256 + 0x43 * ROWS] == data[256 + FALLBACK * ROWS : 256 + (FALLBACK + 1) * ROWS]


@pytest.mark.parametrize(
    "src, message",
    [
        ("@ 3F\n1 ##\n2 ###\n", "differing widths"),
        ("@ 3F\n1 #########\n", "max 8"),
        ("@ 3F\n12 #\n", "out of range"),
        ("@ 3F\n1 #\n@ 3F\n1 #\n", "defined twice"),
        ("@ 41\n1 #\n", "fallback"),
        ("@ 3F\n1 #\n@ 82\n1 #\n", "not drawable"),
        ("1 #\n", "expected"),
    ],
)
def test_invalid_fonts_are_rejected(src, message):
    with pytest.raises(FontError, match=message):
        parse_font(src)


def test_project_font_covers_printable_ascii():
    glyphs = load_font()
    missing = [chr(c) for c in range(0x20, 0x7F) if c not in glyphs and chr(c) not in "!#<>"]
    assert missing == []


def test_project_font_digits_are_tabular():
    glyphs = load_font()
    assert {glyphs[c].advance for c in range(0x30, 0x3A)} == {6}
