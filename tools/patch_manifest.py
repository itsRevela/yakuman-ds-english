"""The release patch committed in patch/ and the manifest that ties it to the sources.

GitHub Actions cannot rebuild the patch (that needs the original ROM, which never goes to
GitHub), so the patch is built locally and committed. patch/manifest.json records a digest of
the build inputs it was made from; the release workflow recomputes the digest and refuses to
publish a patch that is stale, corrupt, or made for a different ROM.

The digest covers the git blob ids of every build input (asm/, font/, gfx/, text/, tools/ minus
tooling that does not affect the ROM), so it is identical for CRLF (Windows) and LF checkouts.

Usage: python tools/patch_manifest.py check
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL_CRC32 = 0x925E2F90            # Yakuman DS (Japan).nds, SHA-1 19fa78ba...e099
PATCH_DIR = "patch"
PATCH_NAME = "Yakuman DS (English).bps"
MANIFEST_NAME = "manifest.json"
BUILD_INPUTS = ("asm", "font", "gfx", "text", "tools")
NOT_INPUTS = ("tools/emu/", "tools/release.py", "tools/patch_manifest.py", "tools/make_patch.py")


class ManifestError(ValueError):
    pass


def _git(root: Path, *args: str, stdin: str | None = None) -> str:
    proc = subprocess.run(["git", *args], cwd=root, input=stdin, capture_output=True, text=True,
                          encoding="utf-8")
    if proc.returncode != 0:
        raise ManifestError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def build_inputs(root: Path) -> list[str]:
    listed = _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "--", *BUILD_INPUTS)
    paths = {p for p in listed.splitlines() if p and not p.startswith(NOT_INPUTS)}
    return sorted(p for p in paths if (root / p).is_file())


def inputs_digest(root: Path) -> str:
    paths = build_inputs(root)
    if not paths:
        raise ManifestError("no build inputs found")
    blobs = _git(root, "hash-object", "--stdin-paths", stdin="\n".join(paths) + "\n").split()
    if len(blobs) != len(paths):
        raise ManifestError("git hash-object returned the wrong number of ids")
    listing = "".join(f"{p} {b}\n" for p, b in zip(paths, blobs))
    return hashlib.sha256(listing.encode("utf-8")).hexdigest()


def _footer(patch: bytes) -> tuple[int, int]:
    if patch[:4] != b"BPS1" or len(patch) < 16:
        raise ManifestError("not a BPS patch")
    if zlib.crc32(patch[:-4]) != int.from_bytes(patch[-4:], "little"):
        raise ManifestError("BPS patch checksum mismatch (corrupt file)")
    return int.from_bytes(patch[-12:-8], "little"), int.from_bytes(patch[-8:-4], "little")


def publish(root: Path, patch: bytes, expected_source_crc: int = ORIGINAL_CRC32) -> dict:
    source_crc, target_crc = _footer(patch)
    if source_crc != expected_source_crc:
        raise ManifestError(f"patch is for a source ROM with CRC32 {source_crc:08x}, "
                            f"expected {expected_source_crc:08x}")
    manifest = {
        "patch": PATCH_NAME,
        "patch_sha256": hashlib.sha256(patch).hexdigest(),
        "source_crc32": f"{source_crc:08x}",
        "target_crc32": f"{target_crc:08x}",
        "inputs_sha256": inputs_digest(root),
    }
    out = root / PATCH_DIR
    out.mkdir(exist_ok=True)
    (out / PATCH_NAME).write_bytes(patch)
    (out / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def check(root: Path, expected_source_crc: int = ORIGINAL_CRC32) -> dict:
    manifest_path = root / PATCH_DIR / MANIFEST_NAME
    patch_path = root / PATCH_DIR / PATCH_NAME
    if not manifest_path.is_file() or not patch_path.is_file():
        raise ManifestError(f"{PATCH_DIR}/ has no published patch; run tools/make_patch.py --publish")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    patch = patch_path.read_bytes()
    if hashlib.sha256(patch).hexdigest() != manifest["patch_sha256"]:
        raise ManifestError(f"{PATCH_NAME} does not match its manifest")
    source_crc, target_crc = _footer(patch)
    if source_crc != expected_source_crc or f"{source_crc:08x}" != manifest["source_crc32"]:
        raise ManifestError(f"patch source CRC32 {source_crc:08x} is not the original ROM's")
    if f"{target_crc:08x}" != manifest["target_crc32"]:
        raise ManifestError("patch target CRC32 does not match its manifest")
    if inputs_digest(root) != manifest["inputs_sha256"]:
        raise ManifestError("patch is stale: the sources changed since it was built; run "
                            "tools/build.py and tools/make_patch.py --publish, then commit patch/")
    return manifest


def main(argv: list[str]) -> int:
    if argv != ["check"]:
        print(__doc__)
        return 2
    manifest = check(ROOT)
    print(f"{PATCH_DIR}/{PATCH_NAME} is current (target CRC32 {manifest['target_crc32']})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
