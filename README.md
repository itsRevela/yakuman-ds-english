# Yakuman DS English Translation

An English fan translation of *Yakuman DS*, the 2005 Nintendo DS mahjong game with Mario and
friends that was only released in Japan.

Menus, rules, matches, the tutorial, the mahjong dictionary and the game's text graphics are in
English. Mahjong terms follow the English version of *Mahjong Soul* (Riichi, Tsumo, Ron, Pon,
"All Simples" and so on), and characters use their official English names. The tiles themselves
are left as they are.

**[Download the latest patch](https://github.com/itsRevela/yakuman-ds-english/releases/latest)**

## How to patch your game

The patch turns your Japanese copy of the game into an English one. It takes a couple of minutes
and works in a web browser on a PC, Mac or phone. Nothing needs to be installed.

### What you need

1. **The patch:** `Yakuman.DS.English.bps`, from the
   [latest release](https://github.com/itsRevela/yakuman-ds-english/releases/latest) (look under
   "Assets").
2. **Your Yakuman DS ROM:** a backup of your own Japanese cartridge, as a `.nds` file. This
   project doesn't provide ROMs. If your backup is in a `.zip` or `.7z` file, extract the `.nds`
   first.

The patch only works on the standard, untouched dump of the game:

| Check | Expected value |
|---|---|
| File size | 33,554,432 bytes (32 MB) |
| CRC32 | `925E2F90` |
| SHA-1 | `19fa78ba37a623e028dd36dabf28b9c2e258e099` |

You don't have to check these yourself: the patcher shows them and refuses a ROM that doesn't
match.

### Steps

1. Open [Rom Patcher JS](https://www.marcrobledo.com/RomPatcher.js/).
2. Next to **ROM:**, choose your `.nds` file. The page lists its checksums; CRC32 should be
   `925E2F90`.
3. Next to **Patch file:**, choose `Yakuman.DS.English.bps`.
4. Click **Apply patch**. Your browser saves the English ROM.
5. Play the new file the same way you played the original: open it in your emulator (for
   example melonDS) or copy it to your flashcart.

**Keep your original ROM.** The patch always needs the untouched Japanese file. When a new
version of the patch comes out, apply it to the original again, not to a ROM you already
patched.

**Your saves carry over.** The English version reads the same save data as the Japanese one.
Emulators usually name the save after the ROM, so to keep your progress, copy your old save file
and rename it to match the new ROM's file name (for example `Yakuman DS (English).sav`).

### Other patchers

Any patcher that supports the BPS format works, for example Floating IPS (Flips) on Windows or
UniPatcher on Android. In Floating IPS: click **Apply Patch**, choose the `.bps` file, then your
ROM, then where to save the English copy.

### If it doesn't work

- **The patcher refuses your ROM or reports a checksum mismatch.** Your file isn't the standard
  dump. The usual causes:
  - It's **trimmed**: some tools remove the empty space at the end of DS ROMs, which makes the
    file smaller than 32 MB. Use an untrimmed backup.
  - It was already patched, it's a different version of the game, or the backup is damaged.
- **The game is still in Japanese.** Make sure you're loading the new file the patcher saved,
  not the original.
- **Something else is wrong.** Please
  [open an issue](https://github.com/itsRevela/yakuman-ds-english/issues) and describe what
  happened and which screen it was on.

## What's translated

- Every menu, the options and rule settings, records and stats, character select and profiles
- Matches: calls and shouts, hand results and scoring, Professor Lakitu's hints, round banners
- The Mahjong Basics tutorial and the full Mahjong Dictionary (all 220 entries)
- Challenge Mode, Ranking Mode, the title screen, the opening captions and the wireless menus

## Known limitations

- **DS Download Play guests see Japanese.** Hosting a Download Play game works and the host's
  screens are in English, but the program sent to the other consoles is still Japanese. Nintendo
  signs that program and consoles refuse a modified one, so translating it would break Download
  Play on real hardware.
- The large embossed title on the dictionary's book cover is part of the background art and is
  still Japanese.
- A few long yaku names are shortened on the hand result screen so they fit next to the han
  count (for example "Pure Dbl. Seq."). The dictionary uses the full names.
- The patch has been tested in the melonDS emulator.

## For developers

Everything below is about building the patch from source. To just play the game in English, you
only need the steps above.

### Status

| Phase | State |
|---|---|
| 0. Tooling, ROM extraction and rebuild, string catalog | done |
| 1. English variable-width font and engine hacks | done (VWF, word wrap, widths, dictionary) |
| 2. Text insertion pipeline | done |
| 3. Translation of the main program's strings | done (1,845 strings, name-entry keyboard) |
| 4. Text graphics | done, except the dictionary book cover art |
| 5. Download Play child program (`main.srl`) | on hold: it's RSA-signed, and modifying it breaks Download Play on real consoles |
| 6. In-game QA and releases | v0.1.0 released; QA continues |

See `CHANGELOG.md` for what changed in each version and `docs/TECHNICAL_NOTES.md` for the
reverse-engineering details.

### Requirements

- The original ROM `Yakuman DS (Japan).nds` (checksums above) in the project folder
- Python 3.12 or newer
- [`ds-decomp`](https://github.com/AetiasHax/ds-decomp) (`dsd`), built with Rust 1.95 or newer
  (`cargo +1.99.1 build --release` inside `ds-decomp/`)
- [`armips`](https://github.com/Kingcom/armips) v0.11.0, placed at `tools/bin/armips.exe`

### Layout

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

### Setup (once)

```sh
dsd rom extract --rom "Yakuman DS (Japan).nds" --output-path work/extract
dsd init --rom-config work/extract/config.yaml --output-path work/dsd --build-path work/build
dsd dis --config-path work/dsd/arm9/config.yaml --asm-path work/asm
python tools/scan_strings.py        # -> work/catalog.json
```

### Build

```sh
python tools/insert_text.py         # validate every translation file
python tools/build.py               # -> out/Yakuman DS (English).nds
python -m pytest tests
python tools/make_patch.py          # -> out/Yakuman DS (English).bps (verified by re-applying)
```

### Translating

Translations live in `text/<category>.json` (`addr`, exact `ja`, `en`, optional layout keys).
Markup: `\n` newline, `{term}` highlighted glossary link, `^` instant-draw toggle. See
`docs/STYLE_GUIDE.md` for terminology and `tools/insert_text.py` for the layout keys.

### Testing in the emulator

The harness uses RetroArch's melonDS DS core (`H:\RetroArch\cores`, override with
`YAKUMAN_CORE`/`YAKUMAN_SYSTEM_DIR`). Example: boot to the main menu with the fixture save and
take a screenshot:

```sh
python tools/emu/explore.py "out/Yakuman DS (English).nds" work/shots/menu \
    --sram work/fixtures/profile1.srm @main shot:menu
```

### Releasing

Releases are automated by `.github/workflows/release.yml` on every push to `master`:

1. Describe the changes under `## [Unreleased]` in `CHANGELOG.md`.
2. Rebuild and publish the patch (it needs the original ROM, so CI can't build it):
   `python tools/build.py && python tools/make_patch.py --publish`, then commit `patch/`.
3. Commit with a Conventional Commit message: `feat:` makes a minor version, `fix:` or `perf:` a
   patch version, and `feat!:` or a `BREAKING CHANGE:` footer a major version (minor before 1.0).
   `docs:`, `chore:`, `test:`, `ci:` and `refactor:` don't make a release.
4. Push. The workflow runs the tests, refuses a stale or wrong patch (`tools/patch_manifest.py`),
   moves the changelog notes under the new version, makes a signed release commit and a signed
   `vX.Y.Z` tag, and publishes the GitHub release with the `.bps`.

Commits and tags are GPG-signed with the maintainer key `DC969E4797BBDBD4` (repository config
`commit.gpgsign` and `tag.gpgSign`; the workflow uses the `GPG_PRIVATE_KEY` and `GPG_PASSPHRASE`
repository secrets). Pull after each release to get the workflow's changelog commit.
