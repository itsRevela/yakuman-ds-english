"""Release versioning for the GitHub Actions workflow (.github/workflows/release.yml).

The next version is derived from Conventional Commit messages since the last `vX.Y.Z` tag:
    feat: ...                      -> minor
    fix: ... / perf: ...           -> patch
    type!: ... or a "BREAKING CHANGE:" footer -> major (minor while the version is 0.x)
    anything else (docs, chore, test, ci, refactor, ...) -> no release

Usage:
    python tools/release.py plan                      print the next version, or nothing
    python tools/release.py changelog X.Y.Z --notes FILE [--date YYYY-MM-DD]
        move CHANGELOG.md's [Unreleased] notes under "## [X.Y.Z] - date" and write them to FILE
"""
from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
UNRELEASED = "## [Unreleased]"

_HEADER = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]*\))?(?P<bang>!)?: \S")
_BREAKING = re.compile(r"^BREAKING[ -]CHANGE: ", re.MULTILINE)
_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
_RANK = {"patch": 1, "minor": 2, "major": 3}


class ReleaseError(ValueError):
    pass


def bump_for(messages: list[str]) -> str | None:
    """The largest version bump the commit messages call for, or None."""
    best = None
    for message in messages:
        m = _HEADER.match(message.strip())
        if not m:
            continue
        if m.group("bang") or _BREAKING.search(message):
            bump = "major"
        elif m.group("type") == "feat":
            bump = "minor"
        elif m.group("type") in ("fix", "perf"):
            bump = "patch"
        else:
            continue
        if best is None or _RANK[bump] > _RANK[best]:
            best = bump
    return best


def next_version(last_tag: str | None, bump: str) -> str:
    if last_tag is None:
        major, minor, patch = 0, 0, 0
    else:
        m = _TAG.match(last_tag)
        if not m:
            raise ReleaseError(f"last tag {last_tag!r} is not vMAJOR.MINOR.PATCH")
        major, minor, patch = (int(g) for g in m.groups())
    if bump == "major" and major == 0:
        bump = "minor"                     # pre-1.0: breaking changes bump the minor version
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ReleaseError(f"unknown bump {bump!r}")


def roll_changelog(text: str, version: str, date: str) -> tuple[str, str]:
    """(new changelog text, release notes): the [Unreleased] notes move under the new version."""
    start = text.find(UNRELEASED + "\n")
    if start < 0:
        raise ReleaseError(f"CHANGELOG has no '{UNRELEASED}' heading")
    body_start = start + len(UNRELEASED) + 1
    nxt = re.compile(r"^## \[", re.MULTILINE).search(text, body_start)
    body_end = nxt.start() if nxt else len(text)
    notes = text[body_start:body_end].strip()
    if not notes:
        raise ReleaseError("CHANGELOG [Unreleased] is empty; describe the changes before releasing")
    rest = text[body_end:]
    new = (text[:start] + f"{UNRELEASED}\n\n## [{version}] - {date}\n\n{notes}\n"
           + ("\n" + rest if rest else ""))
    return new, notes


def _git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def last_tag() -> str | None:
    tags = [t for t in _git("tag", "--merged", "HEAD", "--list", "v*").split() if _TAG.match(t)]
    if not tags:
        return None
    return max(tags, key=lambda t: tuple(int(g) for g in _TAG.match(t).groups()))


def messages_since(tag: str | None) -> list[str]:
    rev = f"{tag}..HEAD" if tag else "HEAD"
    return [m for m in _git("log", "--format=%B%x1e", rev).split("\x1e") if m.strip()]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    ch = sub.add_parser("changelog")
    ch.add_argument("version")
    ch.add_argument("--notes", type=Path, required=True)
    ch.add_argument("--date", default=datetime.date.today().isoformat())
    args = ap.parse_args(argv)

    if args.cmd == "plan":
        tag = last_tag()
        bump = bump_for(messages_since(tag))
        if bump:
            print(next_version(tag, bump))
        return 0
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        raise ReleaseError(f"version {args.version!r} is not MAJOR.MINOR.PATCH")
    text, notes = roll_changelog(CHANGELOG.read_text(encoding="utf-8"), args.version, args.date)
    CHANGELOG.write_text(text, encoding="utf-8", newline="\n")
    args.notes.write_text(notes + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
