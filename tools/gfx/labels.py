"""Replace text sub-images ("labels") of a texture atlas and update its region table.

A label recipe names a region of the texture; the original pixels of that region are cleared, the
English text is rendered, placed in any free (transparent, unreferenced) space of the atlas, and
the region entry gets the new u/v/w/h. The x/y offset is adjusted so the label keeps its anchor
(centre by default) where the game adds that offset to its own draw position.

Patches edit pixels in place without touching regions, for text drawn inside a larger graphic
(e.g. the "Back" in a "(B) Back" button).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from regions import Region

Indexed = list[list[int]]
GUTTER = 1


class LabelError(ValueError):
    pass


@dataclass(frozen=True)
class Label:
    region: int
    image: Indexed
    align: str = "center"   # center | left | right | none (keep the region's x/y offsets)
    keep_height: bool = True


@dataclass(frozen=True)
class Patch:
    rect: tuple[int, int, int, int]   # x, y, w, h to clear
    clear: int | None                 # fill index, or None to copy each row from sample_x
    image: Indexed | None
    at: tuple[int, int] | None        # top-left of image; None = centred in rect
    sample_x: int | None = None       # column whose pixel restores each row's background


class Occupancy:
    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.cells = [[False] * width for _ in range(height)]
        self._sums: list[list[int]] | None = None

    def mark(self, x: int, y: int, w: int, h: int) -> None:
        for yy in range(max(0, y), min(self.height, y + h)):
            row = self.cells[yy]
            for xx in range(max(0, x), min(self.width, x + w)):
                row[xx] = True
        self._sums = None

    def _prefix(self) -> list[list[int]]:
        if self._sums is None:
            s = [[0] * (self.width + 1) for _ in range(self.height + 1)]
            for y in range(self.height):
                acc = 0
                row = self.cells[y]
                for x in range(self.width):
                    acc += row[x]
                    s[y + 1][x + 1] = s[y][x + 1] + acc
            self._sums = s
        return self._sums

    def is_free(self, x: int, y: int, w: int, h: int) -> bool:
        if x < 0 or y < 0 or x + w > self.width or y + h > self.height:
            return False
        s = self._prefix()
        return s[y + h][x + w] - s[y][x + w] - s[y + h][x] + s[y][x] == 0

    def find(self, w: int, h: int) -> tuple[int, int] | None:
        """Top-most, then left-most free position for a w x h rectangle plus gutter."""
        gw, gh = w + GUTTER, h + GUTTER
        for y in range(0, self.height - h + 1):
            for x in range(0, self.width - w + 1):
                if self.is_free(x, y, min(gw, self.width - x), min(gh, self.height - y)):
                    return x, y
        return None


def _rect_cells(r: Region) -> tuple[int, int, int, int]:
    return r.u, r.v, r.w, r.h


def _inside(x: int, y: int, r: Region) -> bool:
    return r.u <= x < r.u + r.w and r.v <= y < r.v + r.h


def apply_labels(pixels: Indexed, regions: list[Region], labels: list[Label]
                 ) -> tuple[Indexed, list[Region]]:
    """Return new pixel rows and region list with the labels replaced."""
    height, width = len(pixels), len(pixels[0])
    targets = [lab.region for lab in labels]
    if len(set(targets)) != len(targets):
        raise LabelError(f"region listed twice: {sorted(t for t in targets if targets.count(t) > 1)}")
    for t in targets:
        if not 0 <= t < len(regions):
            raise LabelError(f"region {t} out of range (table has {len(regions)})")
    replaced = set(targets)
    # Some region tables run into unrelated data; only sane rectangles inside the atlas count.
    kept = [r for i, r in enumerate(regions)
            if i not in replaced and r.w > 0 and r.h > 0 and r.u >= 0 and r.v >= 0
            and r.u + r.w <= width and r.v + r.h <= height]

    out = [list(row) for row in pixels]
    for t in targets:
        r = regions[t]
        for y in range(max(0, r.v), min(height, r.v + r.h)):
            for x in range(max(0, r.u), min(width, r.u + r.w)):
                if not any(_inside(x, y, k) for k in kept):
                    out[y][x] = 0

    occ = Occupancy(width, height)
    for y in range(height):
        for x in range(width):
            if out[y][x]:
                occ.mark(x, y, 1, 1)
    for k in kept:
        occ.mark(*_rect_cells(k))

    def placed_height(lab: Label) -> int:
        return max(len(lab.image), regions[lab.region].h) if lab.keep_height else len(lab.image)

    new_regions = list(regions)
    # Widest first, then tallest: long strips claim the wide gaps the original text left behind.
    order = sorted(labels, key=lambda lab: (-len(lab.image[0]), -placed_height(lab)))
    for lab in order:
        old = regions[lab.region]
        img_h, img_w = len(lab.image), len(lab.image[0])
        h = placed_height(lab)
        w = img_w
        pos = occ.find(w, h)
        if pos is None:
            raise LabelError(f"no free {w}x{h} space for region {lab.region}")
        u, v = pos
        top = v + (h - img_h) // 2
        for yy, row in enumerate(lab.image):
            for xx, val in enumerate(row):
                if val:
                    out[top + yy][u + xx] = val
        occ.mark(u, v, w + GUTTER, h + GUTTER)
        if lab.align == "none":
            new_regions[lab.region] = replace(old, u=u, v=v, w=w, h=h)
            continue
        if lab.align == "left":
            x = old.x
        elif lab.align == "right":
            x = old.x + old.w - w
        elif lab.align == "center":
            x = old.x + (old.w - w) // 2
        else:
            raise LabelError(f"unknown align {lab.align!r}")
        y = old.y + (old.h - h) // 2
        new_regions[lab.region] = replace(old, u=u, v=v, w=w, h=h, x=x, y=y)
    return out, new_regions


def apply_patches(pixels: Indexed, patches: list[Patch]) -> Indexed:
    out = [list(row) for row in pixels]
    height, width = len(out), len(out[0])
    for p in patches:
        x0, y0, w, h = p.rect
        if x0 < 0 or y0 < 0 or x0 + w > width or y0 + h > height:
            raise LabelError(f"patch rect {p.rect} outside {width}x{height}")
        if (p.clear is None) == (p.sample_x is None):
            raise LabelError(f"patch {p.rect}: give exactly one of clear / sample_x")
        if p.sample_x is not None and x0 <= p.sample_x < x0 + w:
            raise LabelError(f"patch {p.rect}: sample column {p.sample_x} lies inside the rect")
        for y in range(y0, y0 + h):
            fill = p.clear if p.sample_x is None else pixels[y][p.sample_x]
            for x in range(x0, x0 + w):
                out[y][x] = fill
        if p.image is None:
            continue
        ih, iw = len(p.image), len(p.image[0])
        if p.at is None:
            ax, ay = x0 + (w - iw) // 2, y0 + (h - ih) // 2
        else:
            ax, ay = p.at
        if ax < x0 or ay < y0 or ax + iw > x0 + w or ay + ih > y0 + h:
            raise LabelError(f"patch text {iw}x{ih} at ({ax},{ay}) does not fit rect {p.rect}")
        for yy, row in enumerate(p.image):
            for xx, val in enumerate(row):
                if val:
                    out[ay + yy][ax + xx] = val
    return out
