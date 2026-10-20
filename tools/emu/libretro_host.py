"""Minimal headless libretro frontend for automated screenshots of the DS game.

Drives a libretro core DLL (melonDS DS by default; DeSmuME's software rasterizer samples the
game's 3D-composited UI textures inaccurately) through ctypes: boots a ROM, runs frames with
scripted joypad/touch input, captures the video output and writes PNGs. Stdlib only.

Usage from Python:
    with Emulator(rom) as emu:
        emu.run(300)
        emu.press("A", frames=5)
        emu.touch(128, 96, frames=5)    # bottom-screen coordinates (0..255, 0..191)
        emu.screenshot("work/shots/menu.png")
"""
from __future__ import annotations

import ctypes as C
import os
import struct
import zlib
from pathlib import Path

DEFAULT_CORE = Path(os.environ.get("YAKUMAN_CORE", r"H:\RetroArch\cores\melondsds_libretro.dll"))
DEFAULT_SYSTEM_DIR = Path(os.environ.get("YAKUMAN_SYSTEM_DIR", r"H:\RetroArch\system"))

SCREEN_W, SCREEN_H = 256, 192

# libretro constants
ENV_GET_CAN_DUPE = 3
ENV_SET_PERFORMANCE_LEVEL = 8
ENV_GET_SYSTEM_DIRECTORY = 9
ENV_SET_PIXEL_FORMAT = 10
ENV_SET_INPUT_DESCRIPTORS = 11
ENV_SET_HW_RENDER = 14
ENV_GET_VARIABLE = 15
ENV_SET_VARIABLES = 16
ENV_GET_VARIABLE_UPDATE = 17
ENV_GET_LOG_INTERFACE = 27
ENV_GET_SAVE_DIRECTORY = 31
ENV_GET_USERNAME = 38
ENV_GET_CORE_OPTIONS_VERSION = 52
PIXEL_0RGB1555, PIXEL_XRGB8888, PIXEL_RGB565 = 0, 1, 2
DEVICE_JOYPAD, DEVICE_POINTER = 1, 6
POINTER_X, POINTER_Y, POINTER_PRESSED = 0, 1, 2
JOYPAD_IDS = {
    "B": 0, "Y": 1, "SELECT": 2, "START": 3, "UP": 4, "DOWN": 5, "LEFT": 6, "RIGHT": 7,
    "A": 8, "X": 9, "L": 10, "R": 11,
}

# Core options forced for deterministic, software-rendered, top/bottom output (both cores' keys;
# each core only asks for its own).
DEFAULT_OPTIONS = {
    "melonds_render_mode": "software",
    "melonds_screen_layout1": "top-bottom",
    "melonds_number_of_screen_layouts": "1",
    "melonds_touch_mode": "pointer",
    "melonds_sysfile_mode": "builtin",
    "melonds_console_mode": "ds",
    "melonds_screen_gap": "0",
    "melonds_threaded_renderer": "disabled",
    "melonds_show_cursor": "disabled",
    "melonds_firmware_language": "english",
    "desmume_screens_layout": "top/bottom",
    "desmume_pointer_type": "touch",
    "desmume_opengl_mode": "disabled",
    "desmume_internal_resolution": "256x192",
    "desmume_frameskip": "0",
    "desmume_firmware_language": "English",
    "desmume_screens_gap": "0",
}


class GameInfo(C.Structure):
    _fields_ = [("path", C.c_char_p), ("data", C.c_void_p), ("size", C.c_size_t), ("meta", C.c_char_p)]


class Variable(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


class Geometry(C.Structure):
    _fields_ = [("base_width", C.c_uint), ("base_height", C.c_uint), ("max_width", C.c_uint),
                ("max_height", C.c_uint), ("aspect_ratio", C.c_float)]


class Timing(C.Structure):
    _fields_ = [("fps", C.c_double), ("sample_rate", C.c_double)]


class AvInfo(C.Structure):
    _fields_ = [("geometry", Geometry), ("timing", Timing)]


ENV_CB = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO_CB = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUDIO_CB = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDIO_BATCH_CB = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL_CB = C.CFUNCTYPE(None)
STATE_CB = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
# retro_log_printf_t is variadic; on x64 the extra arguments are simply ignored by this prototype.
LOG_CB = C.CFUNCTYPE(None, C.c_int, C.c_char_p)


class Emulator:
    def __init__(self, rom: Path | str, core: Path = DEFAULT_CORE, system_dir: Path = DEFAULT_SYSTEM_DIR,
                 save_dir: Path | None = None, options: dict[str, str] | None = None,
                 sram: Path | str | None = None, persist_sram: bool = False) -> None:
        """sram: cartridge save image loaded at boot (if it exists); persist_sram writes it back on close."""
        self.rom = Path(rom).resolve()
        if not self.rom.is_file():
            raise FileNotFoundError(self.rom)
        if not core.is_file():
            raise FileNotFoundError(f"libretro core not found: {core}")
        self.options = {**DEFAULT_OPTIONS, **(options or {})}
        # Strings handed to the core must outlive the callback, so keep C buffers alive here.
        self._opt_bufs = {k: C.create_string_buffer(v.encode()) for k, v in self.options.items()}
        self._system_dir = C.create_string_buffer(str(system_dir).encode())
        save_dir = Path(save_dir) if save_dir else Path(__file__).resolve().parents[2] / "work" / "saves"
        save_dir.mkdir(parents=True, exist_ok=True)
        self._save_dir = C.create_string_buffer(str(save_dir).encode())
        self._username = C.create_string_buffer(b"Player")
        self.log_lines: list[str] = []
        self._log_cb = LOG_CB(lambda level, fmt: self.log_lines.append(fmt.decode(errors="replace")))
        self.pixel_format = PIXEL_0RGB1555
        self.frame: tuple[bytes, int, int, int] | None = None
        self.buttons: set[str] = set()
        self.pointer: tuple[int, int] | None = None
        self.frame_count = 0

        self.lib = C.CDLL(str(core))
        self._callbacks = (
            ENV_CB(self._env), VIDEO_CB(self._video), AUDIO_CB(lambda l, r: None),
            AUDIO_BATCH_CB(lambda d, n: n), POLL_CB(lambda: None), STATE_CB(self._input_state),
        )
        env, video, audio, batch, poll, state = self._callbacks
        self.lib.retro_set_environment(env)
        self.lib.retro_set_video_refresh(video)
        self.lib.retro_set_audio_sample(audio)
        self.lib.retro_set_audio_sample_batch(batch)
        self.lib.retro_set_input_poll(poll)
        self.lib.retro_set_input_state(state)
        self.lib.retro_init()

        self.lib.retro_load_game.restype = C.c_bool
        # Provide both path and data: cores with needs_fullpath=false only read the data buffer.
        self._rom_data = C.create_string_buffer(self.rom.read_bytes())
        info = GameInfo(str(self.rom).encode(), C.cast(self._rom_data, C.c_void_p), len(self._rom_data.raw) - 1, None)
        if not self.lib.retro_load_game(C.byref(info)):
            self.lib.retro_deinit()
            raise RuntimeError(f"core refused to load {self.rom}")
        self._loaded = True
        self.sram_path = Path(sram) if sram else None
        self.persist_sram = persist_sram
        if self.sram_path and self.sram_path.is_file():
            self._write_sram(self.sram_path.read_bytes())

    # -- libretro callbacks -------------------------------------------------------------------
    def _env(self, cmd: int, data: int) -> bool:
        cmd &= 0xFFFF
        if cmd == ENV_GET_CAN_DUPE:
            C.cast(data, C.POINTER(C.c_bool))[0] = True
            return True
        if cmd == ENV_GET_SYSTEM_DIRECTORY:
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.addressof(self._system_dir)
            return True
        if cmd == ENV_GET_LOG_INTERFACE:
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.cast(self._log_cb, C.c_void_p).value
            return True
        if cmd == ENV_GET_USERNAME:
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.addressof(self._username)
            return True
        if cmd == ENV_GET_SAVE_DIRECTORY:
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.addressof(self._save_dir)
            return True
        if cmd == ENV_SET_PIXEL_FORMAT:
            fmt = C.cast(data, C.POINTER(C.c_uint))[0]
            if fmt not in (PIXEL_0RGB1555, PIXEL_XRGB8888, PIXEL_RGB565):
                return False
            self.pixel_format = fmt
            return True
        if cmd == ENV_GET_VARIABLE:
            slots = C.cast(data, C.POINTER(C.c_void_p))  # [0] = key, [1] = value
            key = C.string_at(slots[0]).decode() if slots[0] else ""
            buf = self._opt_bufs.get(key)
            if buf is None:
                return False
            slots[1] = C.addressof(buf)
            return True
        if cmd == ENV_GET_VARIABLE_UPDATE:
            C.cast(data, C.POINTER(C.c_bool))[0] = False
            return True
        if cmd == ENV_GET_CORE_OPTIONS_VERSION:
            C.cast(data, C.POINTER(C.c_uint))[0] = 0
            return True
        if cmd in (ENV_SET_PERFORMANCE_LEVEL, ENV_SET_INPUT_DESCRIPTORS, ENV_SET_VARIABLES):
            return True
        if cmd == ENV_SET_HW_RENDER:
            return False
        return False

    def _video(self, data: int, width: int, height: int, pitch: int) -> None:
        if data:
            self.frame = (C.string_at(data, pitch * height), width, height, pitch)

    def _input_state(self, port: int, device: int, index: int, ident: int) -> int:
        if port != 0:
            return 0
        if device == DEVICE_JOYPAD:
            return int(any(JOYPAD_IDS[b] == ident for b in self.buttons))
        if device == DEVICE_POINTER and self.pointer is not None:
            x, y = self.pointer
            if ident == POINTER_PRESSED:
                return 1
            # Pointer space spans the full (top+bottom) output: -0x7fff..0x7fff.
            if ident == POINTER_X:
                return int((x + 0.5) / SCREEN_W * 0xFFFE) - 0x7FFF
            if ident == POINTER_Y:
                return int((y + SCREEN_H + 0.5) / (SCREEN_H * 2) * 0xFFFE) - 0x7FFF
        return 0

    # -- control ------------------------------------------------------------------------------
    def run(self, frames: int = 1) -> None:
        for _ in range(frames):
            self.lib.retro_run()
            self.frame_count += 1

    def press(self, *buttons: str, frames: int = 4, release: int = 4) -> None:
        unknown = set(buttons) - JOYPAD_IDS.keys()
        if unknown:
            raise ValueError(f"unknown buttons: {unknown}")
        self.buttons = set(buttons)
        self.run(frames)
        self.buttons = set()
        self.run(release)

    def touch(self, x: int, y: int, frames: int = 4, release: int = 4) -> None:
        if not (0 <= x < SCREEN_W and 0 <= y < SCREEN_H):
            raise ValueError(f"touch ({x},{y}) outside the bottom screen")
        self.pointer = (x, y)
        self.run(frames)
        self.pointer = None
        self.run(release)

    def save_state(self) -> bytes:
        self.lib.retro_serialize_size.restype = C.c_size_t
        size = self.lib.retro_serialize_size()
        buf = C.create_string_buffer(size)
        self.lib.retro_serialize.restype = C.c_bool
        if not self.lib.retro_serialize(buf, C.c_size_t(size)):
            raise RuntimeError("retro_serialize failed")
        return buf.raw

    def load_state(self, state: bytes) -> None:
        self.lib.retro_unserialize.restype = C.c_bool
        if not self.lib.retro_unserialize(state, C.c_size_t(len(state))):
            raise RuntimeError("retro_unserialize failed")

    def _sram(self) -> tuple[int, int]:
        self.lib.retro_get_memory_data.restype = C.c_void_p
        self.lib.retro_get_memory_size.restype = C.c_size_t
        base, size = self.lib.retro_get_memory_data(0), self.lib.retro_get_memory_size(0)
        if not base or not size:
            raise RuntimeError("core does not expose RETRO_MEMORY_SAVE_RAM")
        return base, size

    def _write_sram(self, data: bytes) -> None:
        base, size = self._sram()
        if len(data) != size:
            raise ValueError(f"save image is {len(data)} bytes, core expects {size}")
        C.memmove(base, data, size)

    def read_sram(self) -> bytes:
        base, size = self._sram()
        return C.string_at(base, size)

    def read_ram(self, addr: int, size: int) -> bytes:
        """Read main RAM (0x02000000-0x023FFFFF) via RETRO_MEMORY_SYSTEM_RAM if the core exposes it."""
        self.lib.retro_get_memory_data.restype = C.c_void_p
        self.lib.retro_get_memory_size.restype = C.c_size_t
        base = self.lib.retro_get_memory_data(2)
        total = self.lib.retro_get_memory_size(2)
        off = addr - 0x02000000
        if not base or off < 0 or off + size > total:
            raise RuntimeError("main RAM not exposed by core or address out of range")
        return C.string_at(base + off, size)

    # -- output -------------------------------------------------------------------------------
    def rgb(self) -> tuple[bytes, int, int]:
        if self.frame is None:
            raise RuntimeError("no frame has been rendered yet")
        data, w, h, pitch = self.frame
        out = bytearray(w * h * 3)
        o = 0
        for y in range(h):
            row = data[y * pitch : y * pitch + pitch]
            if self.pixel_format == PIXEL_XRGB8888:
                for x in range(w):
                    b, g, r = row[x * 4], row[x * 4 + 1], row[x * 4 + 2]
                    out[o : o + 3] = bytes((r, g, b))
                    o += 3
            else:
                for (p,) in struct.iter_unpack("<H", row[: w * 2]):
                    if self.pixel_format == PIXEL_RGB565:
                        r, g, b = (p >> 11) & 31, (p >> 5) & 63, p & 31
                        out[o : o + 3] = bytes((r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2))
                    else:
                        r, g, b = (p >> 10) & 31, (p >> 5) & 31, p & 31
                        out[o : o + 3] = bytes((r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2))
                    o += 3
        return bytes(out), w, h

    def region(self, x: int, y: int, w: int, h: int) -> bytes:
        """RGB bytes of a rectangle of the current frame (y spans both screens, 0..383).
        Decodes only the requested pixels, so it is cheap enough to call every frame."""
        if self.frame is None:
            raise RuntimeError("no frame has been rendered yet")
        data, width, height, pitch = self.frame
        if x < 0 or y < 0 or x + w > width or y + h > height:
            raise ValueError(f"region {x},{y},{w},{h} outside {width}x{height}")
        out = bytearray()
        for row in range(y, y + h):
            if self.pixel_format == PIXEL_XRGB8888:
                line = data[row * pitch + x * 4 : row * pitch + (x + w) * 4]
                for i in range(0, len(line), 4):
                    out += bytes((line[i + 2], line[i + 1], line[i]))
            else:
                line = data[row * pitch + x * 2 : row * pitch + (x + w) * 2]
                for (p,) in struct.iter_unpack("<H", line):
                    if self.pixel_format == PIXEL_RGB565:
                        r, g, b = (p >> 11) & 31, (p >> 5) & 63, p & 31
                        out += bytes((r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2))
                    else:
                        r, g, b = (p >> 10) & 31, (p >> 5) & 31, p & 31
                        out += bytes((r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2))
        return bytes(out)

    def screenshot(self, path: Path | str) -> Path:
        rgb, w, h = self.rgb()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_png(path, rgb, w, h)
        return path

    def close(self) -> None:
        if getattr(self, "_loaded", False):
            if self.persist_sram and self.sram_path:
                self.sram_path.parent.mkdir(parents=True, exist_ok=True)
                self.sram_path.write_bytes(self.read_sram())
            self.lib.retro_unload_game()
            self.lib.retro_deinit()
            self._loaded = False

    def __enter__(self) -> "Emulator":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def write_png(path: Path, rgb: bytes, w: int, h: int) -> None:
    raw = b"".join(b"\x00" + rgb[y * w * 3 : (y + 1) * w * 3] for y in range(h))

    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    path.write_bytes(png)
