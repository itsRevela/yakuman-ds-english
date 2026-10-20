"""Build translated graphics into the patched ROM tree.

Strip atlases (gfx/strip_atlases.json): textures that hold one line of text per region (e.g. the
main menu descriptions). Every strip is re-rendered in English with the VWF font, the strips are
shelf-packed into the texture, and the texture's region table in ARM9 gets the new u/v/w/h (the
on-screen position stays the same).

Labels (gfx/labels.json): individual text regions of mixed atlases are re-rendered and re-placed
(tools/gfx/labels.py); patches redraw text in place inside larger graphics.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bigfont  # noqa: E402
import labels as labelmod  # noqa: E402
import layout_patch  # noqa: E402
import namefont  # noqa: E402
import sprites  # noqa: E402
import ntft  # noqa: E402
import textimg  # noqa: E402
from regions import read_regions, table_counts, write_region  # noqa: E402
from romdata import ARM9_BASE, ROOT  # noqa: E402
from textures import GX_FORMATS, find_textures  # noqa: E402

GFX_DIR = ROOT / "gfx"
REGION_SIZE = 12  # 6 x s16: u, v, w, h, screen x, screen y
MAX_COLOR_DISTANCE = 30  # sum of |dR|+|dG|+|dB| allowed when matching "#rrggbb" to a palette


class GfxError(ValueError):
    pass


def _style(spec: dict) -> textimg.TextStyle:
    return textimg.TextStyle(fill=spec["fill"], outline=spec.get("outline"), shadow=spec.get("shadow"),
                             spacing=spec.get("spacing", 0))


def build_strip_atlas(name: str, spec: dict, files_dir: Path, arm9: bytearray, textures: dict) -> None:
    tex = textures.get(name)
    if tex is None:
        raise GfxError(f"{name}: no texture descriptor")
    bpp = ntft.FORMAT_BPP[GX_FORMATS[tex.gx_format]]
    style = _style(spec["style"])
    strip_h = spec.get("strip_height", 17)
    pad_x, pad_y = spec.get("pad_x", 2), spec.get("pad_y", 2)
    max_w = spec.get("max_width")
    table = int(spec["regions"], 16)

    images = []
    for i, strip in enumerate(spec["strips"]):
        img = textimg.render(strip["en"], style) if strip["en"] else textimg.blank(1, 1)
        w = len(img[0]) + pad_x
        if max_w is not None and w > max_w:
            raise GfxError(f"{name} strip {i}: {strip['en']!r} is {w} px, limit {max_w}")
        if len(img) + pad_y > strip_h:
            raise GfxError(f"{name} strip {i}: text taller than the {strip_h} px strip")
        images.append((img, w))

    positions = textimg.shelf_pack_ffd([(w, strip_h) for _, w in images], tex.width, tex.height)
    atlas = textimg.blank(tex.width, tex.height)
    for (img, w), (u, v) in zip(images, positions):
        textimg.paste(atlas, img, u + pad_x, v + pad_y)

    for i, ((img, w), (u, v)) in enumerate(zip(images, positions)):
        off = table + i * REGION_SIZE - ARM9_BASE
        _, _, _, _, sx, sy = struct.unpack_from("<6h", arm9, off)
        struct.pack_into("<6h", arm9, off, u, v, w, strip_h, sx, sy)

    out = files_dir / "vtex" / f"{name}.ntft"
    flat = [i for row in atlas for i in row]
    data = ntft.encode_indices(flat, bpp)
    if len(data) != out.stat().st_size:
        raise GfxError(f"{name}: encoded size {len(data)} != original {out.stat().st_size}")
    out.write_bytes(data)


class Palette:
    def __init__(self, colors: list[tuple[int, int, int]], name: str):
        self.colors, self.name = colors, name

    def index(self, value: int | str) -> int:
        if isinstance(value, int):
            if not 0 < value < len(self.colors):
                raise GfxError(f"{self.name}: palette index {value} out of range")
            return value
        if not (isinstance(value, str) and value.startswith("#") and len(value) == 7):
            raise GfxError(f"{self.name}: bad colour {value!r} (use an index or '#rrggbb')")
        want = tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
        best = min(range(1, len(self.colors)),
                   key=lambda i: sum(abs(a - b) for a, b in zip(self.colors[i], want)))
        dist = sum(abs(a - b) for a, b in zip(self.colors[best], want))
        if dist > MAX_COLOR_DISTANCE:
            raise GfxError(f"{self.name}: no palette colour near {value} (closest #{bytes(self.colors[best]).hex()})")
        return best


def render_text(text: str, style: dict, pal: Palette) -> list[list[int]]:
    font = style["font"]
    if font == "display":
        ds = namefont.DisplayStyle(outline=pal.index(style["outline"]),
                                   bands=tuple(pal.index(c) for c in style["bands"]),
                                   spacing=style.get("spacing", -1))
        return namefont.render(text, ds)
    fill = style["fill"]
    fill_idx = [pal.index(c) for c in fill] if isinstance(fill, list) else pal.index(fill)
    outline = pal.index(style["outline"]) if "outline" in style else None
    shadow = pal.index(style["shadow"]) if "shadow" in style else None
    if font == "small":
        mask = bigfont.text_mask(text)
    elif font == "big":
        mask = bigfont.big_mask(text, bold=style.get("bold", True))
    elif font == "tiny":
        mask = bigfont.tiny_mask(text)
    elif font == "huge":
        mask = bigfont.huge_mask(text, bold=style.get("bold", True))
    elif font == "small_bold":
        mask = bigfont.embolden(bigfont.text_mask(text))
    else:
        raise GfxError(f"unknown font {font!r}")
    if style.get("trim_rows"):
        mask = bigfont.trim_rows(mask)
    outline2 = style.get("outline2")
    if outline2 is not None:
        outline2 = [pal.index(c) for c in outline2] if isinstance(outline2, list) else pal.index(outline2)
    return textimg.colorize(mask, fill_idx, outline=outline, outline_width=style.get("outline_width", 1),
                            shadow=shadow, outline2=outline2)


def render_item(item: dict, styles: dict, pal: Palette) -> list[list[int]]:
    """Render an item's "en": a string in item["style"], or [[text, style], ...] segments."""
    en = item["en"]
    segments = [[en, item["style"]]] if isinstance(en, str) else en
    images = []
    for text, style_name in segments:
        if style_name not in styles:
            raise GfxError(f"unknown style {style_name!r}")
        images.append(render_text(text, styles[style_name], pal))
    height = max(len(img) for img in images)
    gap = item.get("segment_gap", 0)
    width = sum(len(img[0]) for img in images) + gap * (len(images) - 1)
    out = textimg.blank(width, height)
    x = 0
    for img in images:
        textimg.paste(out, img, x, (height - len(img)) // 2)
        x += len(img[0]) + gap
    fixed = item.get("width")
    if fixed is not None:
        if width > fixed:
            raise GfxError(f"{item['en']!r} is {width} px wide, fixed width {fixed}")
        padded = textimg.blank(fixed, height)
        slack = fixed - width
        offset = {"left": 0, "right": slack}.get(item.get("width_align", "center"), slack // 2)
        textimg.paste(padded, out, offset, 0)
        out, width = padded, fixed
    max_w = item.get("max_width")
    if max_w is not None and width > max_w:
        raise GfxError(f"{item['en']!r} is {width} px wide, limit {max_w}")
    return out


def render_lines(item: dict, styles: dict, pal: Palette) -> list[list[int]] | None:
    """Several lines of one style stacked every line_height px (a paragraph patch)."""
    line_h = item["line_height"]
    images = [render_item({"en": text, "style": item["style"]}, styles, pal) if text else None
              for text in item["lines"]]
    drawn = [img for img in images if img is not None]
    if not drawn:
        return None
    width = max(len(img[0]) for img in drawn)
    height = line_h * (len(images) - 1) + max(len(img) for img in drawn)
    out = textimg.blank(width, height)
    for i, img in enumerate(images):
        if img is not None:
            textimg.paste(out, img, 0, i * line_h)
    limit = item.get("max_width")
    if limit is not None and width > limit:
        widest = max((t for t in item["lines"] if t), key=lambda t: len(render_item({"en": t, "style": item["style"]}, styles, pal)[0]))
        raise GfxError(f"line {widest!r} is wider than {limit} px")
    return out


def render_any(item: dict, styles: dict, colors: list[tuple[int, int, int]]) -> list[list[int]] | None:
    """Render an item's "en" or "lines" against a raw palette (used for vdata sprite sheets)."""
    pal = Palette(colors, "vdata")
    return render_lines(item, styles, pal) if "lines" in item else render_item(item, styles, pal)


def build_patches(item: dict, styles: dict, pal: Palette) -> list[labelmod.Patch]:
    """One patch, or several when "rects" lists screen-contiguous pieces of one text line.

    With "rects" the text is centred across the pieces' total width and sliced into them, for
    graphics the game draws from separate atlas places side by side (e.g. a split header plate).
    """
    if "lines" in item:
        image = render_lines(item, styles, pal)
    else:
        image = render_item(item, styles, pal) if item.get("en") else None
    clear = None
    if "clear" in item:
        clear = 0 if item["clear"] == 0 else pal.index(item["clear"])
    if "rects" not in item:
        return [labelmod.Patch(rect=tuple(item["rect"]), clear=clear, image=image,
                               at=tuple(item["at"]) if "at" in item else None,
                               sample_x=item.get("sample_x"))]
    rects = [tuple(r) for r in item["rects"]]
    samples = item.get("sample_x", [None] * len(rects))
    if len(samples) != len(rects):
        raise GfxError(f"{item.get('ja')}: need one sample_x per rect")
    total = sum(r[2] for r in rects)
    if image is not None and len(image[0]) > total:
        raise GfxError(f"{item['en']!r} is {len(image[0])} px wide, the rects hold {total}")
    start = (total - len(image[0])) // 2 if image is not None else 0
    out, cursor = [], 0
    for rect, sample in zip(rects, samples):
        x, y, w, h = rect
        piece = None
        if image is not None:
            lo, hi = max(0, cursor - start), min(len(image[0]), cursor + w - start)
            if hi > lo:
                piece = [row[lo:hi] for row in image]
        at = None
        if piece is not None:
            at = (x + max(0, start - cursor), y + (h - len(piece)) // 2)
        out.append(labelmod.Patch(rect=rect, clear=clear, image=piece, at=at, sample_x=sample))
        cursor += w
    return out


def build_label_texture(name: str, spec: dict, styles: dict, files_dir: Path, arm9: bytearray,
                        textures: dict, counts: dict) -> int:
    tex = textures.get(name)
    if tex is None:
        raise GfxError(f"{name}: no texture descriptor")
    bpp = ntft.FORMAT_BPP[GX_FORMATS[tex.gx_format]]
    path = files_dir / "vtex" / f"{name}.ntft"
    pal = Palette(ntft.read_palette((files_dir / "vtex" / f"{name}.ntfp").read_bytes()), name)
    flat = ntft.decode_indices(path.read_bytes(), bpp)
    pixels = [flat[y * tex.width:(y + 1) * tex.width] for y in range(tex.height)]

    patches = []
    for item in spec.get("patches", []):
        patches.extend(build_patches(item, styles, pal))
    try:
        pixels = labelmod.apply_patches(pixels, patches)
    except labelmod.LabelError as exc:
        raise GfxError(f"{name}: {exc}") from exc

    items = spec.get("labels", [])
    if items:
        count = counts[tex.regions_addr]
        regions = read_regions(bytes(arm9), tex.regions_addr, count)
        labs = [labelmod.Label(region=item["region"], image=render_item(item, styles, pal),
                               align=item.get("align", "center"),
                               keep_height=item.get("keep_height", True))
                for item in items]
        try:
            pixels, new_regions = labelmod.apply_labels(pixels, regions, labs)
        except labelmod.LabelError as exc:
            raise GfxError(f"{name}: {exc}") from exc
        for i, (old, new) in enumerate(zip(regions, new_regions)):
            if old != new:
                write_region(arm9, tex.regions_addr, i, new)

    data = ntft.encode_indices([v for row in pixels for v in row], bpp)
    if len(data) != path.stat().st_size:
        raise GfxError(f"{name}: encoded size {len(data)} != original {path.stat().st_size}")
    path.write_bytes(data)
    return len(items) + len(patches)


COURSE_BUTTON_WIDTH = 94
COURSE_NAME_REGIONS = (1, 2, 3, 4)   # Challenge/TexChallenge course names, in course order


def fill_course_name_dx(arm9: bytearray, symbols: dict[str, int], textures: dict, counts: dict) -> None:
    """Write per-course x offsets that centre each course name on its button (asm/challenge.asm)."""
    addr = symbols.get("course_name_dx")
    if addr is None:
        raise GfxError("course_name_dx symbol missing from armips output")
    tex = textures["Challenge/TexChallenge"]
    regions = read_regions(bytes(arm9), tex.regions_addr, counts[tex.regions_addr])
    for course, index in enumerate(COURSE_NAME_REGIONS):
        dx = (COURSE_BUTTON_WIDTH - regions[index].w) // 2
        if not 0 <= dx <= 127:
            raise GfxError(f"course name region {index} ({regions[index].w} px) does not fit the button")
        arm9[addr - ARM9_BASE + course] = dx


def build_all(files_dir: Path, arm9_bin: Path, symbols: dict[str, int], verbose: bool = True) -> None:
    arm9 = bytearray(arm9_bin.read_bytes())
    tex_list = find_textures(bytes(arm9))
    textures = {t.name: t for t in tex_list}
    counts = table_counts(tex_list)
    atlases = json.loads((GFX_DIR / "strip_atlases.json").read_text(encoding="utf-8"))
    for name, spec in atlases.items():
        build_strip_atlas(name, spec, files_dir, arm9, textures)
    label_spec = json.loads((GFX_DIR / "labels.json").read_text(encoding="utf-8"))
    n_items = 0
    for name, spec in label_spec["textures"].items():
        n_items += build_label_texture(name, spec, label_spec["styles"], files_dir, arm9, textures, counts)
    n_sprites = sprites.build_all(files_dir, label_spec["styles"], render_any, arm9)
    fill_course_name_dx(arm9, symbols, textures, counts)
    n_calls = 0
    tables = layout_patch.texture_tables(tex_list, counts)
    for layout_file in sorted(GFX_DIR.glob("*_conditions.json")):
        spec = json.loads(layout_file.read_text(encoding="utf-8"))
        try:
            n_calls += layout_patch.apply_layout(arm9, spec, tables)
        except layout_patch.LayoutError as exc:
            raise GfxError(f"{layout_file.name}: {exc}") from exc
    arm9_bin.write_bytes(bytes(arm9))
    if verbose:
        print(f"gfx: {len(atlases)} strip atlases, {n_items} labels/patches in "
              f"{len(label_spec['textures'])} textures, {n_calls} draw positions re-laid out, "
              f"{n_sprites} sprite patches")


def preview(name: str, files_dir: Path, out_png: Path) -> None:
    """Decode a (patched) texture to PNG for review."""
    tex = {t.name: t for t in find_textures()}[name]
    bpp = ntft.FORMAT_BPP[GX_FORMATS[tex.gx_format]]
    pal = ntft.read_palette((files_dir / "vtex" / f"{name}.ntfp").read_bytes())
    img = ntft.to_image((files_dir / "vtex" / f"{name}.ntft").read_bytes(), pal, bpp, tex.width)
    ntft.write_png(out_png, img)
