"""Create a screen signature from a verified screenshot: python tools/emu/make_sig.py NAME PNG X,Y,W,H"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from explore import SIG_DIR  # noqa: E402
from pngio import read_png  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    name, png, rect = argv
    x, y, w, h = (int(v) for v in rect.split(","))
    _, _, rows = read_png(png)
    rgb = bytes(c for row in rows[y : y + h] for px in row[x : x + w] for c in px[:3])
    SIG_DIR.mkdir(parents=True, exist_ok=True)
    (SIG_DIR / f"{name}.json").write_text(json.dumps({"rect": [x, y, w, h], "rgb": rgb.hex()}))
    print(f"signature {name}: {rect} from {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
