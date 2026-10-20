import pytest

from build import BuildError, banner_with_title

BANNER = (
    "version: Original\n"
    "title:\n"
    "  japanese: |-\n"
    "    やくまんDS\n"
    "    Nintendo  \n"
    "  english: |-\n"
    "    やくまんDS\n"
    "    Nintendo\n"
    "images:\n"
    "  bitmap_path: bitmap.png\n"
)


def test_banner_title_replaced_for_every_language():
    out = banner_with_title(BANNER, ["Yakuman DS", "Nintendo"])
    assert out.count("    Yakuman DS\n    Nintendo\n") == 2
    assert "やくまん" not in out


def test_banner_keeps_other_fields():
    out = banner_with_title(BANNER, ["Yakuman DS", "Nintendo"])
    assert out.startswith("version: Original\ntitle:\n")
    assert out.endswith("images:\n  bitmap_path: bitmap.png\n")


def test_banner_rejects_unexpected_original_title():
    with pytest.raises(BuildError):
        banner_with_title(BANNER.replace("やくまんDS", "Something else"), ["Yakuman DS", "Nintendo"])
