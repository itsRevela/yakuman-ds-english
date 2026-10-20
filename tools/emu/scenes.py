"""Scripted walk through known screens, for before/after screenshots.

The DeSmuME core cannot be re-initialised inside one process, so a run is one linear script:
each step performs some input and then screenshots the result.

Usage: python tools/emu/scenes.py <rom> <out_dir> [script]
Scripts are defined in SCRIPTS below; default "boot".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from libretro_host import Emulator  # noqa: E402
from pngio import contact_sheet  # noqa: E402

# Each step: (screenshot name, list of actions). Actions: ("run", n) | ("press", btn, hold, wait)
# | ("touch", x, y, hold, wait)
SCRIPTS: dict[str, list[tuple[str, list[tuple]]]] = {
    "boot": [
        ("title", [("run", 600), ("press", "A", 6, 120)]),
        ("save_select", [("press", "A", 6, 120)]),
        ("name_entry", [("press", "A", 6, 90)]),
    ],
}


def perform(emu: Emulator, action: tuple) -> None:
    kind = action[0]
    if kind == "run":
        emu.run(action[1])
    elif kind == "press":
        emu.press(action[1], frames=action[2], release=action[3])
    elif kind == "touch":
        emu.touch(action[1], action[2], frames=action[3], release=action[4])
    else:
        raise ValueError(f"unknown action {action!r}")


def run_script(rom: Path, out_dir: Path, script: str) -> list[Path]:
    if script not in SCRIPTS:
        raise KeyError(f"unknown script {script!r}; known: {sorted(SCRIPTS)}")
    shots = []
    with Emulator(rom) as emu:
        for name, actions in SCRIPTS[script]:
            for action in actions:
                perform(emu, action)
            shots.append(emu.screenshot(out_dir / f"{name}.png"))
    return shots


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    rom, out_dir = Path(argv[0]), Path(argv[1])
    shots = run_script(rom, out_dir, argv[2] if len(argv) > 2 else "boot")
    contact_sheet(shots, out_dir / "sheet.png", columns=len(shots))
    print(f"wrote {len(shots)} screenshots to {out_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
