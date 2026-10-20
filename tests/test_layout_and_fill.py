import pytest

import textcodec
from fill_text import parse_lines
from insert_text import TranslationError, apply_layout
from vwf_font import load_font

GLYPHS = load_font()


def width(data: bytes) -> int:
    return textcodec.line_widths(data, GLYPHS)[-1]


def test_leader_fills_with_dots_up_to_target_without_exceeding():
    out = apply_layout(b"Riichi", (("leader", 80),))
    assert out.startswith(b"Riichi.") and width(out) <= 80
    assert width(out + b".") > 80


def test_leader_is_noop_when_text_exactly_fills_target():
    assert apply_layout(b"Riichi", (("leader", width(b"Riichi")),)) == b"Riichi"


def test_center_balances_spaces():
    out = apply_layout(b"Fast", (("center", 40),))
    left = len(out) - len(out.lstrip(b" "))
    right = len(out) - len(out.rstrip(b" "))
    assert abs(left - right) <= 1 and width(out) <= 40


def test_pad_extends_inside_trailing_highlight():
    out = apply_layout(b"<Dora>", (("pad", 60),))
    assert out.startswith(b"<Dora ") and out.endswith(b">")
    assert width(out) <= 60


def test_unknown_layout_key_rejected():
    with pytest.raises(TranslationError):
        apply_layout(b"x", (("stretch", 3),))


def test_parse_lines_handles_newlines_options_and_comments():
    rows = parse_lines("# c\n\n020eb448\tA\\nB\n020eb449\tC\t{\"center\": 36}\n")
    assert rows == [("020eb448", "A\nB", {}), ("020eb449", "C", {"center": 36})]


def test_parse_lines_rejects_bad_address():
    with pytest.raises(ValueError):
        parse_lines("zz\tx\n")


def test_parse_lines_rejects_missing_column():
    with pytest.raises(ValueError):
        parse_lines("020eb448\n")


@pytest.mark.parametrize("key", ["leader", "center", "pad"])
def test_text_wider_than_layout_target_is_rejected(key):
    with pytest.raises(TranslationError, match="exceeds"):
        apply_layout(b"Thirteen-wait Thirteen Orphans", ((key, 40),))


def test_wrap_breaks_at_spaces_within_limit():
    text = b"Discarding that tile takes you further from winning"
    out = apply_layout(text, (("wrap", 100),))
    lines = out.split(b"!")
    assert len(lines) > 1 and all(width(line) <= 100 for line in lines)
    assert b" ".join(lines) == text


def test_wrap_keeps_existing_newlines():
    out = apply_layout(b"[1 han]!Short text", (("wrap", 200),))
    assert out == b"[1 han]!Short text"


def test_wrap_ignores_zero_width_highlight_markers():
    out = apply_layout(b"<Dora> <Dora>", (("wrap", width(b"Dora Dora")),))
    assert b"!" not in out


def test_wrap_rejects_word_wider_than_limit():
    with pytest.raises(TranslationError, match="too wide"):
        apply_layout(b"Thirteen-wait", (("wrap", 20),))


def test_max_accepts_text_within_limit_unchanged():
    assert apply_layout(b"Riichi", (("max", 100),)) == b"Riichi"


def test_max_checks_every_line():
    with pytest.raises(TranslationError, match="exceeds"):
        apply_layout(b"ok!Thirteen-wait Thirteen Orphans", (("max", 60),))


def test_scoring_link_labels_fit_before_the_han_column():
    # func_0207cf28 draws each yaku link label at x and its "%2d han" at x + 76; the digit's ink
    # starts at about x + 80, so a label may advance at most 79 px.
    import json
    from pathlib import Path

    import insert_text
    import textcodec

    glyphs = insert_text._glyphs()
    path = Path(__file__).resolve().parent.parent / "text" / "scoring.json"
    too_wide = []
    for e in json.loads(path.read_text(encoding="utf-8"))["entries"]:
        en = e.get("en") or ""
        if en.startswith("{") and en.endswith("}"):
            width = textcodec.line_widths(textcodec.encode(en), glyphs)[-1]
            if width > 79:
                too_wide.append((e["addr"], en, width))
    assert too_wide == []
