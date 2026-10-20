"""Patch text inside the 2D sprite sheets in vdata/ (gfx/sprites.json).

A sheet (.gcd) is a run of fixed-size sprites with 1D-mapped 8x8 tiles. Each recipe item erases
the Japanese text in a rectangle of one or more sprites and draws English there. Erase modes:

    "clear": colour       fill the rectangle (0 = transparent)
    "sample_x": column    restore each row from that column (striped/gradient backgrounds)
    "none": true          leave the pixels (text drawn over what is there)
    "inpaint": {...}      erase bright text from a dark textured background (see inpaint())
    "template": [sprites] rebuild the background from sibling sprites that share it (the call
                          buttons' radial burst): in each sibling, pixels enclosed by the text
                          outline colour are treated as text, and every pixel takes the most
                          common background value seen at that position among the siblings.

Items whose "sprites" list several sprites treat them as one strip laid out left to right (the
game draws e.g. a word made of two 64x64 kanji sprites side by side).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bigfont  # noqa: E402
import ntft  # noqa: E402
import textimg  # noqa: E402
import vdata  # noqa: E402
from romdata import ARM9_BASE, ROOT  # noqa: E402

SPEC = ROOT / "gfx" / "sprites.json"
Indexed = list[list[int]]


class SpriteError(ValueError):
    pass


def split_sprites(tiles: list[list[int]], w: int, h: int) -> list[Indexed]:
    per = (w // 8) * (h // 8)
    if len(tiles) % per:
        raise SpriteError(f"{len(tiles)} tiles is not a whole number of {w}x{h} sprites")
    return [vdata.sprites_to_image(tiles[i:i + per], w, h, 1) for i in range(0, len(tiles), per)]


def join_sprites(sprites: list[Indexed], w: int, h: int) -> list[list[int]]:
    per = (w // 8) * (h // 8)
    tiles = []
    for img in sprites:
        tiles.extend(vdata.image_to_tiles(img, w, h, 1, per))
    return tiles


def text_mask(img: Indexed, rect: tuple[int, int, int, int], outline: set[int]) -> set[tuple[int, int]]:
    """Pixels of the rect that belong to text: outline pixels plus what they enclose.

    Background is whatever a 4-connected flood fill from the rect's border reaches without
    crossing an outline pixel.
    """
    x0, y0, w, h = rect
    inside = lambda x, y: x0 <= x < x0 + w and y0 <= y < y0 + h  # noqa: E731
    seen: set[tuple[int, int]] = set()
    stack = [(x, y) for x in range(x0, x0 + w) for y in (y0, y0 + h - 1)]
    stack += [(x, y) for y in range(y0, y0 + h) for x in (x0, x0 + w - 1)]
    while stack:
        x, y = stack.pop()
        if (x, y) in seen or not inside(x, y) or img[y][x] in outline:
            continue
        seen.add((x, y))
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    return {(x, y) for x in range(x0, x0 + w) for y in range(y0, y0 + h) if (x, y) not in seen}


def inpaint(img: Indexed, src: Indexed, rect, pal, opts: dict) -> None:
    """Erase bright text from a dark, textured background.

    Pixels brighter than opts["bright"] (sum of RGB), or with a palette index in opts["indices"],
    inside the rect, grown by opts["grow"]
    pixels, are replaced by the nearest unmarked pixel of the same row (then the row above),
    which keeps the surrounding texture instead of painting a flat block.
    """
    x0, y0, w, h = rect
    threshold, grow = opts.get("bright", 400), opts.get("grow", 2)
    indices = set(opts.get("indices", []))
    if indices:
        mask = {(x, y) for y in range(y0, y0 + h) for x in range(x0, x0 + w) if src[y][x] in indices}
    elif opts.get("warm"):
        # gold/white text on a blue background: red at least as strong as blue, or near white
        def warm(c):
            r, g, b = c
            return (r >= b and r > 100) or r + g + b > 600
        mask = {(x, y) for y in range(y0, y0 + h) for x in range(x0, x0 + w) if src[y][x] and warm(pal[src[y][x]])}
    else:
        mask = {(x, y) for y in range(y0, y0 + h) for x in range(x0, x0 + w) if sum(pal[src[y][x]]) > threshold}
    for _ in range(grow):
        mask |= {(x + dx, y + dy) for x, y in mask for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                 if x0 <= x + dx < x0 + w and y0 <= y + dy < y0 + h}
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            if (x, y) not in mask:
                continue
            for d in range(1, w):
                if x - d >= x0 and (x - d, y) not in mask:
                    img[y][x] = src[y][x - d]
                    break
                if x + d < x0 + w and (x + d, y) not in mask:
                    img[y][x] = src[y][x + d]
                    break
            else:
                img[y][x] = img[y - 1][x] if y > y0 else src[y][x]


def build_template(sprites: list[Indexed], members: list[int], rect, outline: set[int]) -> Indexed:
    x0, y0, w, h = rect
    votes: dict[tuple[int, int], Counter] = {}
    for m in members:
        mask = text_mask(sprites[m], rect, outline)
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                if (x, y) not in mask:
                    votes.setdefault((x, y), Counter())[sprites[m][y][x]] += 1
    out = [[None] * w for _ in range(h)]
    for (x, y), c in votes.items():
        out[y - y0][x - x0] = c.most_common(1)[0][0]
    # Any pixel that is text in every sibling takes its nearest known neighbour.
    for _ in range(w + h):
        missing = [(x, y) for y in range(h) for x in range(w) if out[y][x] is None]
        if not missing:
            break
        for x, y in missing:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and out[ny][nx] is not None:
                    out[y][x] = out[ny][nx]
                    break
    return out


def load_sheet(rel: str, spec: dict, files_dir: Path, arm9: bytearray | None):
    """(raw bytes, palette, bpp, sprites) for a sheet stored in a vdata file or inside ARM9.

    ARM9 sheets give "arm9": {"addr", "size", "palette", "palette_size", "palette_offset"}; a
    "layout": "bitmap" sheet is one linear image of spec["sprite"] = [width, height].
    """
    src = spec.get("arm9")
    if src is None:
        raw = (files_dir / "vdata" / f"{rel}.{spec.get('ext', 'gcd')}").read_bytes()
        plt = (files_dir / "vdata" / f"{spec.get('palette', rel)}.plt").read_bytes()
    else:
        if arm9 is None:
            raise SpriteError(f"{rel}: ARM9 sheet but no ARM9 image given")
        addr, size = int(src["addr"], 16) - ARM9_BASE, src["size"]
        raw = bytes(arm9[addr:addr + size])
        paddr = int(src["palette"], 16) - ARM9_BASE + src.get("palette_offset", 0)
        plt = bytes(arm9[paddr:paddr + src["palette_size"]])
    bpp = spec.get("bpp", vdata.palette_bpp(plt))
    pal = ntft.read_palette(plt)
    w, h = spec["sprite"]
    if spec.get("layout") in ("bitmap", "interleaved"):
        flat = ntft.decode_indices(raw, bpp)
        if len(flat) != w * h:
            raise SpriteError(f"{rel}: {len(flat)} pixels is not a {w}x{h} bitmap")
        rows = [flat[y * w:(y + 1) * w] for y in range(h)]
        # "interleaved": two images stored on alternate rows (sheet 0 = even rows, 1 = odd rows)
        sheets = [rows] if spec["layout"] == "bitmap" else [rows[0::2], rows[1::2]]
    else:
        sheets = split_sprites(vdata.decode_tiles(raw, bpp), w, h)
    return raw, pal, bpp, sheets


def store_sheet(rel: str, spec: dict, files_dir: Path, arm9: bytearray | None, raw: bytes, bpp: int,
                sheets: list[Indexed]) -> None:
    w, h = spec["sprite"]
    if spec.get("layout") == "bitmap":
        data = ntft.encode_indices([v for row in sheets[0] for v in row], bpp)
    elif spec.get("layout") == "interleaved":
        rows = [row for pair in zip(sheets[0], sheets[1]) for row in pair]
        data = ntft.encode_indices([v for row in rows for v in row], bpp)
    else:
        data = vdata.encode_tiles(join_sprites(sheets, w, h), bpp)
    if len(data) != len(raw):
        raise SpriteError(f"{rel}: re-encoded size {len(data)} != {len(raw)}")
    src = spec.get("arm9")
    if src is None:
        (files_dir / "vdata" / f"{rel}.{spec.get('ext', 'gcd')}").write_bytes(data)
    else:
        addr = int(src["addr"], 16) - ARM9_BASE
        arm9[addr:addr + len(data)] = data


def apply_file(rel: str, spec: dict, files_dir: Path, styles: dict, render,
               arm9: bytearray | None = None) -> int:
    raw, pal, bpp, sprites = load_sheet(rel, spec, files_dir, arm9)
    original = [[list(r) for r in s] for s in sprites]
    templates: dict[tuple, Indexed] = {}
    for item in spec["items"]:
        members = item["sprites"]
        x0, y0, rw, rh = item["rect"]
        total_w = rw * len(members)
        erase = item.get("erase", {"clear": 0})
        if item.get("cells"):
            image = render_cells(item, styles, pal, render, total_w)
        else:
            image = render(item, styles, pal) if item.get("en") or item.get("lines") else None
        if image is not None and item.get("rotate"):
            image = bigfont.rotate_ccw(image, item["rotate"])
        if image is not None and "text_rect" not in item and len(image[0]) > total_w:
            raise SpriteError(f"{rel}: {item.get('en')!r} is {len(image[0])} px, room for {total_w}")
        if image is not None and "text_rect" not in item and len(image) > rh:
            raise SpriteError(f"{rel}: {item.get('en')!r} is {len(image)} px tall, room for {rh}")
        text_rect = item.get("text_rect")
        if text_rect is not None:
            if len(members) != 1:
                raise SpriteError(f"{rel}: text_rect needs a single sprite")
            if image is not None and (len(image[0]) > text_rect[2] or len(image) > text_rect[3]):
                raise SpriteError(f"{rel}: {item.get('en') or item.get('lines')!r} does not fit its text_rect")
        start = 0
        if image is not None:
            slack = (text_rect[2] if text_rect else total_w) - len(image[0])
            start = {"left": min(slack, item.get("pad", 0)),
                     "right": max(0, slack - item.get("pad", 0))}.get(item.get("align"), slack // 2)
        box_y, box_h = (text_rect[1], text_rect[3]) if text_rect else (y0, rh)
        top = box_y + ((box_h - len(image)) // 2 if image is not None else 0)
        for k, s in enumerate(members):
            img = sprites[s]
            if "clear" in erase:
                fill = erase["clear"]
                fill = 0 if fill == 0 else nearest(pal, fill)
                for y in range(y0, y0 + rh):
                    for x in range(x0, x0 + rw):
                        img[y][x] = fill
            elif "sample_x" in erase:
                sx = erase["sample_x"]
                if x0 <= sx < x0 + rw:
                    raise SpriteError(f"{rel}: sample column {sx} lies inside the rect")
                for y in range(y0, y0 + rh):
                    fill = original[s][y][sx]
                    for x in range(x0, x0 + rw):
                        img[y][x] = fill
            elif erase.get("none"):
                pass
            elif "inpaint" in erase:
                inpaint(img, original[s], item["rect"], pal, erase["inpaint"])
            elif "template" in erase:
                key = (tuple(erase["template"]), tuple(item["rect"]))
                if key not in templates:
                    outline = {nearest(pal, c) if isinstance(c, str) else c for c in erase["outline"]}
                    templates[key] = build_template(original, erase["template"], item["rect"], outline)
                tpl = templates[key]
                for y in range(rh):
                    img[y0 + y][x0:x0 + rw] = list(tpl[y])
            else:
                raise SpriteError(f"{rel}: unknown erase mode {erase}")
            for lx0, lx1, ly, color in item.get("hlines", []):
                for x in range(lx0, lx1):
                    img[ly][x] = nearest(pal, color)
            if image is not None and text_rect is not None:
                for y, row in enumerate(image):
                    for x, v in enumerate(row):
                        if v:
                            img[top + y][text_rect[0] + start + x] = v
            elif image is not None:
                offset = k * rw - start
                for y, row in enumerate(image):
                    for x, v in enumerate(row):
                        px = x - offset
                        if v and 0 <= px < rw:
                            img[top + y][x0 + px] = v
    store_sheet(rel, spec, files_dir, arm9, raw, bpp, sprites)
    return len(spec["items"])


def render_cells(item: dict, styles: dict, pal, render, width: int) -> Indexed:
    """Each character of item["en"] centred in its own equal-width cell across `width` px.

    Used where the game assembles words from per-sprite pieces (e.g. HANE+MAN, SAN+BAI+MAN):
    with every piece's letters on the same cell grid the pieces join seamlessly.
    """
    text = item["en"]
    cell = width // len(text)
    glyphs = [render({"en": ch, "style": item["style"]}, styles, pal) if ch != " " else None for ch in text]
    height = max(len(g) for g in glyphs if g)
    out = textimg.blank(width, height)
    for i, g in enumerate(glyphs):
        if g is None:
            continue
        if len(g[0]) > cell:
            raise SpriteError(f"{text!r}: glyph {text[i]!r} is {len(g[0])} px, cell is {cell}")
        textimg.paste(out, g, i * cell + (cell - len(g[0])) // 2, (height - len(g)) // 2)
    return out


def nearest(pal: list[tuple[int, int, int]], value) -> int:
    if isinstance(value, int):
        return value
    want = tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    best = min(range(1, len(pal)), key=lambda i: sum(abs(a - b) for a, b in zip(pal[i], want)))
    if sum(abs(a - b) for a, b in zip(pal[best], want)) > 30:
        raise SpriteError(f"no palette colour near {value}")
    return best


def build_all(files_dir: Path, styles: dict, render, arm9: bytearray | None = None) -> int:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    return sum(apply_file(rel, s, files_dir, styles, render, arm9) for rel, s in spec["files"].items())
