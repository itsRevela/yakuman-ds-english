# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.0] - 2026-10-20

### Added

- Project scaffolding: README with goals and phase plan, `.gitignore` that keeps ROMs, build
  output and third-party tool checkouts out of version control.
- `docs/TECHNICAL_NOTES.md`: ROM layout, text storage and control codes, font formats, the
  text-rendering call graph, the dictionary layout engine, and the free-space strategy, so later
  work (and future sessions) don't need to repeat the reverse engineering.
- `docs/STYLE_GUIDE.md`: terminology table (Mahjong Soul English yaku and terms, official Mario
  character names) and text conventions, so ~2,000 strings stay consistent.
- String tooling: `tools/scan_strings.py` catalogs all 2,063 Shift-JIS strings with the pointers
  that reference them; `tools/export_text.py`, `tools/fill_text.py` and `tools/fill_by_text.py`
  manage the translation files in `text/*.json`; `tools/insert_text.py` validates and inserts them.
- Translation validation: Japanese source must match the ROM; printf specifiers, `{link}` counts,
  tile placeholders (`Π`) and instant-draw toggles must match; pixel-width limits per entry
  (`max`, `center`, `leader`, `pad`) and offline word wrap (`wrap`) using the real font metrics.
- English variable-width font (`font/vwf12.txt`, 12 px tall, proportional, tabular digits) with
  extra glyphs for `! # < >` (which are control codes) and typographic symbols.
- ARM9 engine hacks (armips, `asm/`):
  - VWF glyph blitter (8 px wide glyphs, per-glyph advance) for all text renderers;
  - pixel-based word wrap at spaces for the dialogue and link renderers;
  - removal of the 256-byte stack copies in both wrapping renderers (long English text);
  - `vwf_strwidth` replacing 21 `strlen() * 6` centering/sizing calculations;
  - dictionary pager/drawer/link hit-test switched from byte columns to pixel columns.
- Free space: the ARM9 image is extended past static BSS and the heap start is moved after the
  new code and text (about 57 KB).
- Build pipeline `tools/build.py` (extract copy → font → armips → text → arena patch → dsd build).
- Headless test harness: `tools/emu/libretro_host.py` drives the melonDS DS libretro core
  (RetroArch install) via ctypes for scripted input, screenshots, save states and SRAM;
  `tools/emu/explore.py` adds an action language with screen-signature waits and routes.
- Translations (1,845 strings): menus/options/rules, records, characters, Mahjong Basics
  tutorial, the full Mahjong Dictionary (220 entries; romaji headwords with English glosses for
  terms, Mahjong Soul names for yaku), Support/advice hints, scoring and result screens,
  wireless/Download Play messages, credits, save dialogs.
- Graphics groundwork: `tools/gfx/ntft.py` decodes the headerless texture files.
- Tests (`tests/`, pytest): font compiler, text codec, inserter, layout options.
- Graphics translation pipeline (`tools/gfx/`, run by `tools/build.py`), driven by data recipes so
  every graphic is rebuilt from the original ROM on each build:
  - `gfx/strip_atlases.json`: one-line-per-region text atlases (menu descriptions, profiles);
  - `gfx/labels.json`: shared text styles plus per-texture labels (re-placed in free atlas
    space, region table updated) and in-place patches for 3D textures;
  - `gfx/sprites.json`: 2D sprite sheets and bitmaps in `vdata/` and graphics embedded in ARM9;
  - `gfx/*_conditions.json`: sentences the game assembles from sprite pieces at hard-coded
    positions, re-laid out by rewriting the `mov` immediates.
- Translated graphics: main menu and submenus, challenge mode (header, course buttons, goals,
  conditions), character select and profiles, records/stats tabs and buttons, ranking screen,
  name entry and save select buttons, call buttons and shouts, pause menu, seat winds, win banners
  (Mangan…Yakuman), round banner, Mahjong Dictionary titles/menus/fu tables, Mahjong Basics title,
  opening-movie captions, title-screen button.
- Match pause/standings overlay (embedded ARM9 bitmaps): game-mode label (Free Play / Ranking
  Mode / Challenge Mode) and the E/S/W/N seat-wind boxes.
- Draw banner words (Draw, Four Kans, Four Winds, Nine Terminals, Four Riichi, Chombo, Triple
  Ron): the Japanese words shared kanji pieces, so `asm/result_words.asm` re-assigns the 32×32
  sprite pieces of each word to match the English sheet (one shared "Four" piece).
- Option / rule screen header plates (Option Settings, Rule Settings, Rule List) and the "Tot"
  column header of the challenge score table.
- Gold title headers embedded in ARM9 (descriptor table `0x0210E030`): DS Wireless Play, DS
  Download Play, Results, Scores, Ranking Points (+ "Current Rank" / "Change" labels).
- `tools/make_patch.py`: standard-library BPS encoder/applier (no new dependencies). Uses
  same-offset reads, continued copies and a 32-byte block index, because the rebuilt ROM shifts
  most files; every patch is verified by applying it to the original before it is written.
  Format checked against the RomPatcher.js implementation. Current patch: about 410 KB.
- Release automation (`.github/workflows/release.yml`): every push to `master` runs the tests,
  picks the next version from Conventional Commit messages (`tools/release.py`), rolls this
  changelog, and publishes a GitHub release with the patch. The release commit and tag are
  GPG-signed with the maintainer's key, like local commits.
- `patch/` holds the released patch with a manifest of the sources it was built from
  (`tools/make_patch.py --publish`, `tools/patch_manifest.py`). CI cannot rebuild the patch
  without the original ROM, so it refuses to publish a patch that doesn't match the commit.
- DS menu banner title "Yakuman DS / Nintendo" for every language (`build.py` rewrites
  `banner.yaml`; it refuses to run if the extracted title is not the expected Japanese one).
- `colorize` accepts a list of outline colours (`"outline2": [inner, outer]`) for text with
  several rings, as on the pause-overlay mode label.
- `insert_text.py` entry key `"max_bytes": N` for strings the game copies into a fixed N-byte
  buffer: relocating such a string does not enlarge the destination, so the build now fails
  instead of silently overflowing it.

### Changed

- Rust 1.99.1 toolchain installed alongside the default (ds-decomp needs `if let` guards).
- Options screen choices are centred in the slot the cursor brackets frame (the slot width is
  the pixel width of the row's first choice, `func_02038b0c`); "Normal" → "Mid" and "Random" →
  "Rand." so three choices fit the row without the brackets covering text.

### Fixed

- Records screen froze on stat labels without the "・" terminator that `func_020241d0` cuts at;
  every label now ends in "・", and the leader dots are placed from the label's pixel width
  (`asm/records.asm`).
- Options screen showed "s/ ON" instead of "OFF / ON" on every On/Off row: the row label
  "Rule Settings" was copied into a 12-byte buffer (`func_02038108`) and overran the next
  string. The label is now "Rules" and guarded by `max_bytes`.
- PictoChat option label was covered by its icon; it keeps the original's leading indent.
- "Winning Tiles" panel cut wait names to "Single Wa" etc.: the game copied them with inline
  loops sized for the Japanese (9 / 5 bytes) and no terminator. `asm/winning_tiles.asm` uses
  strcpy instead; combined waits now read "Two-way Single Wait" / "3-way Single Wait".
- Two strings overran fixed-length inline copies (Mahjong Basics quit prompt, "fu aren't
  counted" note): reworded to fit, and all ten strings copied that way now carry `max_bytes`.
- Result-screen yaku names ran under the "1 han" column (e.g. "Fully Concealed Hand", "Pure
  Double Seq."): the 20 longest link labels use short forms (Fully Concealed, Pure Dbl. Seq.,
  Little 3 Dragons, …) and a test keeps every label within the 79 px before the han column.
