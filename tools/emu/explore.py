"""Drive the game with a tiny action language and collect screenshots.

Usage: python tools/emu/explore.py <rom> <out_dir> [--sram FILE] [--save-sram] [--state-in F] [--state-out F] ACTION...

Actions:
  run:N            run N frames
  A, B, X, Y, L, R, START, SELECT, UP, DOWN, LEFT, RIGHT
                   press a button (6 frames held, 40 frames wait); suffix "*K" repeats, e.g. DOWN*3
  hold:BTN:F:W     press with explicit hold/wait frames
  t:X,Y[:W]        tap the bottom screen at (X, Y), then wait W frames (default 40)
  shot[:name]      screenshot
  sig:NAME:X,Y,W,H save a screen signature (region of the current frame) to work/signatures/NAME.json
  until:NAME[:MAX] run frames until the screen matches signature NAME (default max 1200 frames)
  untilA:NAME[:MAX] like until, but press A every 30 frames while waiting
  save:NAME        save an emulator state to work/states/NAME.st at this point
  ram:NAME         dump main RAM (0x02000000, 4 MB) to work/ram/NAME.bin
  @ROUTE           expand a named route from ROUTES (e.g. @main: boot to the main menu)
Writes <out_dir>/sheet.png with all screenshots.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libretro_host import JOYPAD_IDS, Emulator  # noqa: E402
from pngio import contact_sheet  # noqa: E402

DEFAULT_HOLD, DEFAULT_WAIT = 6, 40
# Named action sequences. Needs --sram with a save that has one profile (work/fixtures/profile1.srm).
ROUTES = {
    "main": ["run:400", "untilA:save_select", "run:60", "A", "until:main_menu", "run:150"],
}
SIG_DIR = Path(__file__).resolve().parents[2] / "work" / "signatures"
SIG_TOLERANCE = 6  # mean absolute difference per channel
STATE_DIR = Path(__file__).resolve().parents[2] / "work" / "states"
RAM_DIR = Path(__file__).resolve().parents[2] / "work" / "ram"


def _sig_path(name: str) -> Path:
    return SIG_DIR / f"{name}.json"


def difference(emu: Emulator, name: str) -> float:
    sig = json.loads(_sig_path(name).read_text())
    current = emu.region(*sig["rect"])
    ref = bytes.fromhex(sig["rgb"])
    return sum(abs(a - b) for a, b in zip(current, ref)) / len(ref)


def matches(emu: Emulator, name: str) -> bool:
    return difference(emu, name) <= SIG_TOLERANCE


def wait_until(emu: Emulator, name: str, limit: int, press_a: bool) -> None:
    if not _sig_path(name).is_file():
        raise FileNotFoundError(f"no signature {name!r}; create it with sig:{name}:x,y,w,h")
    best = float("inf")
    for frame in range(limit):
        diff = difference(emu, name)
        best = min(best, diff)
        if diff <= SIG_TOLERANCE:
            return
        if press_a and frame % 30 == 15:
            emu.press("A", frames=4, release=4)
        else:
            emu.run(1)
    debug = SIG_DIR / f"timeout_{name}.png"
    emu.screenshot(debug)
    raise TimeoutError(f"screen never matched signature {name!r} within {limit} frames "
                       f"(closest diff {best:.1f}, tolerance {SIG_TOLERANCE}); last frame saved to {debug}")


def perform(emu: Emulator, action: str, out_dir: Path, shots: list[Path]) -> None:
    name, _, rest = action.partition(":")
    count = 1
    if "*" in name:
        name, _, n = name.partition("*")
        count = int(n)
    upper = name.upper()
    for _ in range(count):
        if upper == "RUN":
            emu.run(int(rest))
        elif upper in JOYPAD_IDS:
            emu.press(upper, frames=DEFAULT_HOLD, release=DEFAULT_WAIT)
        elif upper == "HOLD":
            btn, hold, wait = rest.split(":")
            emu.press(btn.upper(), frames=int(hold), release=int(wait))
        elif upper == "T":
            xy, _, wait = rest.partition(":")
            x, y = (int(v) for v in xy.split(","))
            emu.touch(x, y, frames=DEFAULT_HOLD, release=int(wait or DEFAULT_WAIT))
        elif upper == "SIG":
            sig_name, _, rect = rest.partition(":")
            x, y, w, h = (int(v) for v in rect.split(","))
            SIG_DIR.mkdir(parents=True, exist_ok=True)
            _sig_path(sig_name).write_text(json.dumps({"rect": [x, y, w, h], "rgb": emu.region(x, y, w, h).hex()}))
        elif upper in ("UNTIL", "UNTILA"):
            sig_name, _, limit = rest.partition(":")
            wait_until(emu, sig_name, int(limit or 1200), upper == "UNTILA")
        elif upper == "SAVE":
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            (STATE_DIR / f"{rest}.st").write_bytes(emu.save_state())
        elif upper == "RAM":
            RAM_DIR.mkdir(parents=True, exist_ok=True)
            (RAM_DIR / f"{rest}.bin").write_bytes(emu.read_ram(0x02000000, 0x400000))
        elif upper == "SHOT":
            label = rest or f"{len(shots):02d}"
            shots.append(emu.screenshot(out_dir / f"{len(shots):02d}_{label}.png"))
        else:
            raise ValueError(f"unknown action {action!r}")


def expand(actions: list[str]) -> list[str]:
    out = []
    for action in actions:
        if action.startswith("@"):
            if action[1:] not in ROUTES:
                raise KeyError(f"unknown route {action}; known: {sorted(ROUTES)}")
            out += ROUTES[action[1:]]
        else:
            out.append(action)
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("actions", nargs="+")
    ap.add_argument("--sram", type=Path)
    ap.add_argument("--save-sram", action="store_true")
    ap.add_argument("--state-in", type=Path)
    ap.add_argument("--state-out", type=Path)
    ap.add_argument("--columns", type=int, default=6)
    args = ap.parse_args(argv)

    shots: list[Path] = []
    with Emulator(args.rom, sram=args.sram, persist_sram=args.save_sram) as emu:
        if args.state_in:
            emu.run(1)
            emu.load_state(args.state_in.read_bytes())
        for action in expand(args.actions):
            perform(emu, action, args.out_dir, shots)
        if args.state_out:
            args.state_out.parent.mkdir(parents=True, exist_ok=True)
            args.state_out.write_bytes(emu.save_state())
    if shots:
        contact_sheet(shots, args.out_dir / "sheet.png", columns=min(args.columns, len(shots)))
    print(f"{len(shots)} screenshots in {args.out_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
