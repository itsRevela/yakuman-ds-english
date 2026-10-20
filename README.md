# Yakuman DS — English Translation Patch

Fan translation of *Yakuman DS* (Nintendo DS, 2005, Japan, game code `AMJJ`).

Goals:

- Translate all text and text graphics into English. Mahjong tiles stay as they are.
- Use terminology and abbreviations in the style of the English version of *Mahjong Soul*
  (e.g. Riichi / Tsumo / Ron / Chii / Pon / Kan; English yaku names such as "All Simples").
- Use the official English names for Mario characters (Toad, Boo, Birdo, Petey Piranha, ...).

## Status

Work in progress. See `CHANGELOG.md` for what has been done and `docs/TECHNICAL_NOTES.md` for the
reverse-engineering details.

| Phase | State |
|---|---|
| 0. Tooling, ROM extraction/rebuild, string catalog | done |
| 1. English variable-width font + engine hacks | done (VWF, word wrap, widths, dictionary) |
| 2. Text insertion pipeline | done |
| 3. Translation of all strings in the main program | 1,845 strings done; name-entry keyboard pending |
| 4. Text graphics (menus, character profiles, headers, buttons, match graphics) | mostly done (recipes in `gfx/`) |
| 5. Download Play child program (`main.srl`) | on hold: RSA-signed, modifying it breaks Download Play on real consoles |
| 6. In-game QA, BPS patch release | in progress (`tools/make_patch.py` done) |

## Requirements

- An unmodified ROM: `Yakuman DS (Japan).nds`, SHA-1 `19fa78ba37a623e028dd36dabf28b9c2e258e099`
- Python 3.12+
- [`ds-decomp`](https://github.com/AetiasHax/ds-decomp) (`dsd`), built with Rust ≥ 1.95
  (`cargo +1.99.1 build --release` inside `ds-decomp/`)
- [`armips`](https://github.com/Kingcom/armips) v0.11.0, placed at `tools/bin/armips.exe`

## Layout

```
asm/           armips patches (VWF engine, width calculations, dictionary layout, screen fixes)
docs/          Technical notes and translation style guide
font/          English VWF font source (text-art glyphs)
gfx/           Graphics recipes: text styles, texture labels/patches, sprite sheets, layouts
patch/         The released BPS patch and its manifest (built locally, published by CI)
.github/       Release workflow
text/          Translation files, one JSON per category (Japanese + English)
tools/         Python build, analysis, translation and graphics scripts
tools/emu/     Headless libretro test harness (screenshots, scripted input)
tests/         pytest suite
work/          Generated: extracted ROM, dsd analysis, disassembly, builds (gitignored)
```

## Setup (once)

```sh
dsd rom extract --rom "Yakuman DS (Japan).nds" --output-path work/extract
dsd init --rom-config work/extract/config.yaml --output-path work/dsd --build-path work/build
dsd dis --config-path work/dsd/arm9/config.yaml --asm-path work/asm
python tools/scan_strings.py        # -> work/catalog.json
```

## Build

```sh
python tools/insert_text.py         # validate every translation file
python tools/build.py               # -> out/Yakuman DS (English).nds
python -m pytest tests
python tools/make_patch.py          # -> out/Yakuman DS (English).bps (verified by re-applying)
```

## Releasing

Releases are automated by `.github/workflows/release.yml` on every push to `master`:

1. Describe the changes under `## [Unreleased]` in `CHANGELOG.md`.
2. Rebuild and publish the patch (it needs the original ROM, so CI cannot build it):
   `python tools/build.py && python tools/make_patch.py --publish`, then commit `patch/`.
3. Commit with a Conventional Commit message: `feat:` → minor version, `fix:`/`perf:` → patch,
   `feat!:` or a `BREAKING CHANGE:` footer → major (minor before 1.0). `docs:`, `chore:`,
   `test:`, `ci:`, `refactor:` don't release.
4. Push. The workflow runs the tests, refuses a stale or wrong patch (`tools/patch_manifest.py`),
   rolls the changelog into the new version, makes a signed release commit and signed `vX.Y.Z`
   tag, and publishes the GitHub release with the `.bps`.

Commits and tags are GPG-signed with the maintainer key `DC969E4797BBDBD4` (repository config
`commit.gpgsign` / `tag.gpgSign`; the workflow uses the `GPG_PRIVATE_KEY` and `GPG_PASSPHRASE`
repository secrets). Pull after each release to get the workflow's changelog commit.

## Applying the patch (players)

Apply `Yakuman DS (English).bps` to an unmodified `Yakuman DS (Japan).nds` (SHA-1 above) with any
BPS patcher, e.g. [Rom Patcher JS](https://www.marcrobledo.com/RomPatcher.js/) or Floating IPS.
The patch checks the ROM's CRC32 and refuses a different dump.

## Translating

Translations live in `text/<category>.json` (`addr`, exact `ja`, `en`, optional layout keys).
Markup: `\n` newline, `{term}` highlighted glossary link, `^` instant-draw toggle. See
`docs/STYLE_GUIDE.md` for terminology and `tools/insert_text.py` for the layout keys.

## Testing in the emulator

The harness uses RetroArch's melonDS DS core (`H:\RetroArch\cores`, override with
`YAKUMAN_CORE`/`YAKUMAN_SYSTEM_DIR`). Example: boot to the main menu with the fixture save and
take a screenshot:

```sh
python tools/emu/explore.py "out/Yakuman DS (English).nds" work/shots/menu \
    --sram work/fixtures/profile1.srm @main shot:menu
```
