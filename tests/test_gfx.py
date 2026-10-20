"""Tests for the graphics tooling in tools/gfx (pure functions; no ROM needed except the font)."""
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "gfx"))

import bigfont  # noqa: E402
import labels  # noqa: E402
import layout_patch  # noqa: E402
import sprites  # noqa: E402
import textimg  # noqa: E402
from regions import Region  # noqa: E402


def blank(w, h, v=0):
    return [[v] * w for _ in range(h)]


# --- labels: re-placing text regions in an atlas -------------------------------------------

def test_apply_labels_clears_old_text_and_updates_region():
    pixels = blank(32, 16)
    for x in range(4, 10):
        pixels[2][x] = 5                       # old text inside region 0
    regions = [Region(4, 2, 6, 1, 10, 20)]
    image = [[7, 7, 7]]
    out, new = labels.apply_labels(pixels, regions, [labels.Label(0, image)])
    assert sum(v == 5 for row in out for v in row) == 0
    r = new[0]
    assert (r.w, r.h) == (3, 1)
    assert [out[r.v][r.u + i] for i in range(3)] == [7, 7, 7]


def test_apply_labels_centres_offset_on_old_region():
    regions = [Region(0, 0, 10, 2, 100, 50)]
    _, new = labels.apply_labels(blank(32, 8), regions, [labels.Label(0, [[1] * 4] * 2)])
    assert new[0].x == 100 + (10 - 4) // 2


def test_apply_labels_keeps_pixels_of_overlapping_kept_regions():
    pixels = blank(16, 4, 3)
    regions = [Region(0, 0, 16, 4, 0, 0), Region(0, 0, 4, 4, 0, 0)]   # region 1 is kept
    out, _ = labels.apply_labels(pixels, regions, [labels.Label(0, [[0]])])
    assert all(out[y][x] == 3 for y in range(4) for x in range(4))


def test_apply_labels_raises_when_atlas_is_full():
    pixels = blank(8, 8, 1)
    regions = [Region(0, 0, 2, 2, 0, 0), Region(0, 0, 8, 8, 0, 0)]
    with pytest.raises(labels.LabelError):
        labels.apply_labels(pixels, regions, [labels.Label(0, [[1] * 9])])


def test_patch_sample_x_restores_each_row_from_column():
    pixels = [[r] * 8 for r in range(4)]       # row-wise stripes
    for y in range(4):
        pixels[y][3] = 9                       # "text"
    out = labels.apply_patches(pixels, [labels.Patch((2, 0, 4, 4), None, None, None, sample_x=7)])
    assert [out[y][3] for y in range(4)] == [0, 1, 2, 3]


def test_patch_rejects_sample_column_inside_rect():
    with pytest.raises(labels.LabelError):
        labels.apply_patches(blank(8, 4), [labels.Patch((2, 0, 4, 4), None, None, None, sample_x=3)])


def test_patch_rejects_rect_outside_image():
    with pytest.raises(labels.LabelError):
        labels.apply_patches(blank(8, 4), [labels.Patch((6, 0, 4, 4), 0, None, None)])


# --- packing and colouring ---------------------------------------------------------------

def test_shelf_pack_ffd_places_widest_first_without_overlap():
    sizes = [(10, 4), (30, 4), (20, 4), (25, 4)]
    pos = textimg.shelf_pack_ffd(sizes, 50, 16)
    rects = [(x, y, w, h) for (x, y), (w, h) in zip(pos, sizes)]
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert not (a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])
    assert pos[1] == (0, 0)                   # the widest strip starts the first shelf


def test_shelf_pack_ffd_raises_when_full():
    with pytest.raises(ValueError):
        textimg.shelf_pack_ffd([(30, 8)] * 5, 50, 16)


def test_colorize_outline_surrounds_ink_and_outline2_surrounds_outline():
    img = textimg.colorize([[1]], 5, outline=6, outline2=7)
    assert len(img) == 5 and len(img[0]) == 5
    assert img[2][2] == 5
    assert img[1][1] == 6 and img[2][3] == 6
    assert img[0][0] == 7 and img[4][2] == 7


def test_colorize_outline2_list_adds_one_ring_per_colour_innermost_first():
    img = textimg.colorize([[1]], 5, outline=6, outline2=[7, 8])
    assert len(img) == 7 and len(img[0]) == 7
    assert [img[3][x] for x in range(7)] == [8, 7, 6, 5, 6, 7, 8]
    assert img[0][0] == 8 and img[1][1] == 7


def test_colorize_shadow_follows_the_outermost_ring():
    img = textimg.colorize([[1]], 5, outline2=[7, 8], shadow=9)
    assert len(img) == 6 and len(img[0]) == 6
    assert img[5][5] == 9 and img[0][0] == 8 and img[2][2] == 5


def test_colorize_gradient_spreads_over_inked_rows():
    img = textimg.colorize([[1], [1], [1], [1]], [10, 20])
    assert [row[0] for row in img] == [10, 10, 20, 20]


# --- fonts -------------------------------------------------------------------------------

def test_scale2x_doubles_size_and_smooths_diagonal():
    out = bigfont.scale2x([[1, 0], [0, 1]])
    assert len(out) == 4 and len(out[0]) == 4
    assert out[0][0] == 1 and out[3][3] == 1


def test_tiny_mask_widths_and_unknown_glyph():
    assert len(bigfont.tiny_mask("AB")[0]) == 4 + 1 + 4
    with pytest.raises(ValueError):
        bigfont.tiny_mask("a")


def test_rotate_ccw_moves_top_row_to_left_column():
    img = [[1, 2], [3, 4]]
    assert bigfont.rotate_ccw(img, 90) == [[2, 4], [1, 3]]
    assert bigfont.rotate_ccw(img, 360) == img


def test_text_mask_is_twelve_rows_and_trimmed_columns():
    mask = bigfont.text_mask("Hi")
    assert len(mask) == 12
    assert any(row[0] for row in mask) and any(row[-1] for row in mask)


# --- instruction patching ----------------------------------------------------------------

def test_mov_imm_word_encodes_and_rejects_large_values():
    assert layout_patch.mov_imm_word(2, 0x66) == 0xE3A02066
    with pytest.raises(layout_patch.LayoutError):
        layout_patch.mov_imm_word(2, 256)


def test_patch_mov_verifies_original_instruction():
    arm9 = bytearray(8)
    struct.pack_into("<I", arm9, 0, 0xE3A02066)
    layout_patch.patch_mov(arm9, 0x02000000, 2, 0x66, 0x70)
    assert struct.unpack_from("<I", arm9, 0)[0] == 0xE3A02070
    with pytest.raises(layout_patch.LayoutError):
        layout_patch.patch_mov(arm9, 0x02000004, 2, 0x66, 0x70)


# --- sprite sheets -----------------------------------------------------------------------

def test_inpaint_by_index_refills_from_same_row():
    src = [[1, 2, 9, 9, 3, 4]]
    img = [list(src[0])]
    sprites.inpaint(img, src, (0, 0, 6, 1), [(0, 0, 0)] * 16, {"indices": [9], "grow": 0})
    assert img[0] == [1, 2, 2, 3, 3, 4]


def test_template_votes_background_across_siblings():
    a = [[5, 5, 5], [5, 1, 5], [5, 5, 5]]   # outline-only "text" at the centre of sibling a
    b = [[5, 5, 5], [5, 5, 5], [5, 5, 5]]
    tpl = sprites.build_template([a, b], [0, 1], (0, 0, 3, 3), {1})
    assert tpl[1][1] == 5


def test_interleaved_sheet_round_trip(tmp_path):
    vdata_dir = tmp_path / "vdata" / "x"
    vdata_dir.mkdir(parents=True)
    rows = [[(y * 4 + x) % 16 for x in range(4)] for y in range(4)]
    import ntft
    raw = ntft.encode_indices([v for r in rows for v in r], 4)
    (vdata_dir / "s.gbd").write_bytes(raw)
    (vdata_dir / "s.plt").write_bytes(bytes(32))
    spec = {"ext": "gbd", "layout": "interleaved", "sprite": [4, 4], "bpp": 4}
    _, _, bpp, sheets = sprites.load_sheet("x/s", spec, tmp_path, None)
    assert sheets[0] == [rows[0], rows[2]] and sheets[1] == [rows[1], rows[3]]
    sprites.store_sheet("x/s", spec, tmp_path, None, raw, bpp, sheets)
    assert (vdata_dir / "s.gbd").read_bytes() == raw


def test_render_cells_puts_each_letter_in_its_own_cell():
    def render(item, styles, pal):
        return [[1] * 3]
    out = sprites.render_cells({"en": "AB", "style": "s"}, {}, None, render, 20)
    assert len(out[0]) == 20
    assert out[0][3:6] == [1, 1, 1] and out[0][13:16] == [1, 1, 1]


# --- palette lookup ----------------------------------------------------------------------

def test_palette_index_matches_nearest_colour_and_rejects_far_or_transparent():
    import assets
    pal = assets.Palette([(0, 0, 0), (255, 0, 0), (0, 0, 255)], "test")
    assert pal.index("#f80000") == 1
    assert pal.index(2) == 2
    with pytest.raises(assets.GfxError):
        pal.index("#00ff00")
    with pytest.raises(assets.GfxError):
        pal.index(0)
