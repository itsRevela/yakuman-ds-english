"""Tiny stdlib-only PNG reader/writer (8-bit grayscale, RGB, RGBA, and palette images).

Images are represented as (width, height, rows) where rows is a list of lists of (r, g, b, a) tuples.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

Pixel = tuple[int, int, int, int]
Image = tuple[int, int, list[list[Pixel]]]

_SIG = b"\x89PNG\r\n\x1a\n"


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read_png(path: Path | str) -> Image:
    data = Path(path).read_bytes()
    if data[:8] != _SIG:
        raise ValueError(f"{path}: not a PNG file")
    pos, idat, palette, trns = 8, b"", None, None
    width = height = depth = ctype = interlace = 0
    while pos < len(data):
        (length,) = struct.unpack_from(">I", data, pos)
        tag = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            width, height, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif tag == b"PLTE":
            palette = [tuple(body[i : i + 3]) for i in range(0, len(body), 3)]
        elif tag == b"tRNS":
            trns = body
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
    if depth != 8 and not (ctype == 3 and depth in (1, 2, 4)):
        raise ValueError(f"{path}: unsupported bit depth {depth} for color type {ctype}")
    if interlace:
        raise ValueError(f"{path}: interlaced PNGs are not supported")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bpp = max(1, channels * depth // 8)
    stride = (width * channels * depth + 7) // 8
    raw = zlib.decompress(idat)
    rows: list[list[Pixel]] = []
    prev = bytearray(stride)
    for y in range(height):
        ftype = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1 : (y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if ftype == 1:
                line[i] = (line[i] + a) & 0xFF
            elif ftype == 2:
                line[i] = (line[i] + b) & 0xFF
            elif ftype == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif ftype == 4:
                line[i] = (line[i] + _paeth(a, b, c)) & 0xFF
        prev = line
        rows.append(_decode_row(line, width, ctype, depth, palette, trns))
    return width, height, rows


def _decode_row(line: bytearray, width: int, ctype: int, depth: int, palette, trns) -> list[Pixel]:
    if ctype == 3:
        if palette is None:
            raise ValueError("palette image without PLTE chunk")
        per = 8 // depth
        out = []
        for x in range(width):
            idx = (line[x // per] >> (8 - depth * (x % per + 1))) & ((1 << depth) - 1)
            alpha = trns[idx] if trns and idx < len(trns) else 255
            out.append((*palette[idx], alpha))
        return out
    if ctype == 0:
        return [(v, v, v, 255) for v in line[:width]]
    if ctype == 4:
        return [(line[i], line[i], line[i], line[i + 1]) for i in range(0, width * 2, 2)]
    if ctype == 2:
        return [(line[i], line[i + 1], line[i + 2], 255) for i in range(0, width * 3, 3)]
    return [tuple(line[i : i + 4]) for i in range(0, width * 4, 4)]


def write_png(path: Path | str, image: Image) -> Path:
    width, height, rows = image
    raw = bytearray()
    for row in rows:
        if len(row) != width:
            raise ValueError("row width mismatch")
        raw.append(0)
        for r, g, b, a in row:
            raw += bytes((r, g, b, a))

    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))

    png = _SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    return path


def contact_sheet(paths: list[Path | str], out: Path | str, columns: int = 4, gap: int = 4,
                  scale: int = 1) -> Path:
    """Tile screenshots into one image for quick review."""
    if not paths:
        raise ValueError("no images given")
    images = [read_png(p) for p in paths]
    cell_w = max(w for w, _, _ in images) * scale
    cell_h = max(h for _, h, _ in images) * scale
    nrows = (len(images) + columns - 1) // columns
    width = columns * cell_w + (columns - 1) * gap
    height = nrows * cell_h + (nrows - 1) * gap
    canvas = [[(40, 40, 40, 255)] * width for _ in range(height)]
    for n, (w, h, rows) in enumerate(images):
        ox = (n % columns) * (cell_w + gap)
        oy = (n // columns) * (cell_h + gap)
        for y in range(h * scale):
            src = rows[y // scale]
            dst = canvas[oy + y]
            for x in range(w * scale):
                dst[ox + x] = src[x // scale]
    return write_png(out, (width, height, canvas))
