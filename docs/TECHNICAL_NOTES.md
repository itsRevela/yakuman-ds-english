# Yakuman DS (AMJJ) — Technical Notes

Reverse-engineering findings that the translation patch depends on. Addresses are ARM9 RAM
addresses (the main module loads at `0x02000000`). Function names follow `dsd`'s auto-generated
`func_XXXXXXXX` symbols.

## ROM layout

| Item | Value |
|---|---|
| Game code | `AMJJ` (Japan), maker `01` |
| ROM size | 32 MiB card, `0x1230620` bytes used |
| ARM9 | `0x02000000`, `0x110258` bytes, **uncompressed**, no overlays |
| ARM9 static BSS | `0x0210FBE0`–`0x0212A200` |
| Autoloads | ITCM (`0x01FF8000`, 0x600 bytes), DTCM (`0x027C0000`, 0x60 bytes) |
| `OS_GetInitArenaLo(MAIN)` literal | `0x02006050` = `0x0212A200` |

NitroFS highlights:

- `/main.srl` — a complete second DS program (`NTRJ`, ARM9 `0x17CCF8` bytes, no FS). This is the
  DS Download Play child; it has its own copy of the engine and ~350 strings.
- `/vdata/**` — `.gcd` (character/tile data), `.gbd` (BG data), `.plt` (palettes). Headerless.
- `/vtex/**` — `.ntft` (texture texels) / `.ntfp` (texture palette). Headerless; dimensions and
  formats come from code.
- `/snd/sound_data.sdat` — standard SDAT (voices are Japanese; not translated).

`dsd rom extract` + `dsd rom build` round-trips the ROM; only the secure-area CRC (`0x6C`) and
header CRC (`0x15E`) differ, which is expected for a decrypted dump.

## Text storage

- All in-game strings live in ARM9 `.rodata` (`0x020DA000`–`0x0210FBE0`) as NUL-terminated
  Shift-JIS, mostly 4-byte aligned.
- `tools/scan_strings.py` finds **2,063 strings / ~64 KB**. Every one has at least one direct
  32-bit pointer (from `dsd` `relocs.txt`), so strings can be relocated by rewriting those words.
  A few short half-width-kana "strings" with code references are false positives (binary data).
- Some strings use half-width katakana bytes (`0xA1`–`0xDF`) to save space.
- Some single-byte ASCII appears in strings (e.g. `CPU`, `ON/OFF`, `%d` format strings).

### Control codes (in `func_020209b0`)

| Byte | Meaning |
|---|---|
| `!` (0x21) | Newline (x reset; y += line spacing + 12) |
| `<` (0x3C) / `>` (0x3E) | Start/end highlight colour (glossary cross-references) |
| `#` (0x23) | Toggle "instant" mode (bypasses the typewriter counter) |
| `Π` (SJIS `0x83A1`) | Placeholder for a tile icon in the tutorial (substituted at runtime) |

Because `!` is newline, English exclamation marks must be encoded as a different byte.

## Fonts (all 1bpp, 12 px tall)

| Font | Index table | Glyphs | Glyph size |
|---|---|---|---|
| Half-width 6×12 | `0x020DAD90` (SJIS rows 0x81–0x84, 189 u16 per row) | `0x020DB378`, 752 glyphs | 14 B: 2-byte SJIS code + 12 rows × 1 byte (MSB first, 6 px used) |
| Full-width 12×12 | `0x020DDC98` (rows 0x81–0x9F, 0xE0–0xEA) | `0x020E1A9C`, 1,205 glyphs | 26 B: 2-byte SJIS code + 12 rows × u16 big-endian (MSB first, 12 px used) |

Single-byte characters are first converted to full-width SJIS by `func_02021010`
(ASCII via table `0x020DACCC`, half-width kana via `0x020DAC48`) and then looked up in the
half-width font (`func_020210d0` → `func_02020f24`). Missing glyphs fall back to `？` (`0x8148`).

## Text rendering

Text is software-rendered into an **8bpp (one byte per pixel) buffer** described by a struct
returned from `func_0201f550`: `+0x0` width (u16), `+0x2` height (u16), `+0x10` pixel pointer.

| Function | Role |
|---|---|
| `func_02020764` | Blit one 12×12 full-width glyph |
| `func_0202068c` | Blit one 6×12 half-width glyph (inner loop `cmp ip, #6`) |
| `func_02020514` / `func_020205d0` | Coloured half/full-width blit wrappers |
| `func_02020e7c` | Draw a string, single colour, no wrap. Advance **hard-coded 6 / 12** (45 callers) |
| `func_02020d84` | Draw a string with colour + optional outline (flags 4/8). Advance **hard-coded 6 / 12** (57 callers) |
| `func_02020840` / `func_02020934` | 2 px / 1 px outline passes (call `func_02020e7c` repeatedly) |
| `func_020209b0` | Main wrapped/typewriter renderer. Handles control codes, auto-wrap by **character count** (`style+0x20`), kinsoku for `、`/`。`. Advance **hard-coded 6 / 12** + `style+0x0` spacing |
| `func_02020d00` / `func_02020d38` | Wrappers; `d38` draws the whole string at once (loops the typewriter index) |

Style struct used by `func_020209b0` (`r8`): `+0x0` letter spacing, `+0x4` line spacing,
`+0x8/+0xC/+0x10` normal colour/outline/flags, `+0x14/+0x18/+0x1C` highlight colour/outline/flags,
`+0x20` max characters per line (half-width units; 0 = no wrap).

**Constraint:** `func_020209b0` `strcpy`s the string into a 256-byte stack buffer
(`func_02018620` is an unbounded `strcpy`). Strings routed through it must stay < 256 bytes or
the routine must be patched. Glossary entries (up to 410 bytes) are drawn by other code.

## Free space strategy

Extend the ARM9 main module past the end of static BSS: pad `arm9.bin` up to `0x0212A200`, then
append new data/code there. `ds-rom` places the autoload blocks after whatever the main module
contains and keeps `bss_start`/`bss_end`, so at boot the padding is zeroed by the BSS clear and
the appended data survives. Then patch the arena-lo literal at `0x02006050` so the heap starts
after the new data.

Reclaimable once translated: the Japanese string pool (~64 KB) and most of the full-width
kanji glyphs (~31 KB), if heap pressure becomes a problem.

## Implemented engine changes (asm/)

| File | What it changes |
|---|---|
| `vwf.asm` | `func_0202068c` → `vwf_blit` (8 px glyphs from our font, returns advance); advance sites in `func_02020e7c`, `func_02020d84`, `func_020209b0`, `func_0208ec24`; pixel word wrap (`vwf_wrap_check`) replacing the character-count wrap in both wrapping renderers; no `strcpy` into 256-byte stack buffers (source pointer kept at `[sp+0x30]` / `[sp+0x4C]`) |
| `strwidth.asm` | 21 `strlen() * 6` (or `* 12 / 2`) centering/sizing sites call `vwf_strwidth` (pixel width of widest line) |
| `dictionary.asm` | Dictionary pager `func_02074b24`, page drawer `func_02074ecc` and link hit-test `func_02074cac` use pixel columns; byte-count wrap disabled (descriptions are pre-wrapped at 240 px by the inserter) |
| `fullwidth.asm` | Full-width Latin/digits drawn with VWF glyphs (names are stored full-width for TexNameFont) |
| `name_entry.asm` | Generated by `tools/gen_keyboard.py`: Latin / digits / hiragana / katakana keyboard pages |
| `challenge.asm` | Course buttons (`func_02042978`): name centred via `course_name_dx` (filled by tools/gfx), "Course" moved |
| `records.asm` | Records screen leader dots placed from the label's pixel width (`vwf_width_units6`) |
| `winning_tiles.asm` | "Winning Tiles" panel (`func_0208d1bc`): four fixed-length inline copies of wait names replaced with strcpy |
| `result_words.asm` | Draw-banner word table `0x021039D0` (7 × 0x18: `(sprite, 0x65, 0)` records ending `(0xFF, 0x66, 0)`), re-split to match `majan/obj_strResult` in `gfx/sprites.json` |
| `vwf_routines.asm`, `challenge_routines.asm` | New routines, placed at `0x0212A200` |

Wrap width for `func_020209b0`/`func_0208ec24`: `style+0x20` (half-width units) → pixels as
`units * 6 + units / 2 * spacing`.

## Mahjong Dictionary

- Entry table `0x020FFB48`, 220 × 16 bytes: `+0` term, `+4` reading, `+8` description,
  `+C` link list (ASCII comma-separated entry indices; the n-th `<…>` in the description links to
  the n-th index). Entries 0–49 are yaku (yaku list, ordered by han), 50–218 are terms in kana
  order (glossary list with あかさたな… tabs, a graphic).
- Descriptions: 240 px wide, 8 lines per page, 16 px line pitch, pages computed by the pager.
- `func_02070fcc` looks up an entry by **term string** (used from the rules screen via
  `func_0203abc8`); rule names and glossary terms are linked by string equality.
- Scoring-screen link labels use a separate table at `0x021049FC` / `0x02104A54`
  (`{plain name, reading, <link text>, entry index}`); link labels were padded with `　` so tap
  boxes have a uniform width (84 px).

## Graphics with text

Many screens use pre-rendered text in textures (`vtex/**/*.ntft` + `.ntfp`, headerless):

| Texture | Format | Size | Content |
|---|---|---|---|
| `MainMenu/TexMenuText` | 4bpp | 256×256 | main menu description lines (12 px strips, two columns) |
| `MainMenu/TexMenuText2` | 4bpp | 256×128 | more menu lines |
| `CharSel/TexCharSelText` | 4bpp | 512×256 | character profile blurbs (grid of 4-line cells) |

Format can be inferred from the palette size (32 B → 4bpp, 512 B → 8bpp); width must be chosen
per file. `tools/gfx/ntft.py` decodes them. 2D `vdata` files (`.gcd`/`.gbd`/`.plt`) are referenced
by path strings in ARM9.

### Graphics pipeline

`tools/build.py` → `tools/gfx/assets.build_all` rebuilds every translated graphic from the
original files on each build, from the recipes in `gfx/` (styles are shared in `labels.json`;
colours are palette indices or `#rrggbb` matched to the nearest palette entry):

| Recipe | Tool | Covers |
|---|---|---|
| `strip_atlases.json` | `assets.py` | atlases with one text line per region |
| `labels.json` | `labels.py` | 3D texture labels (re-placed, region table updated) and in-place patches |
| `sprites.json` | `sprites.py` | `vdata` sprite sheets/bitmaps and ARM9-embedded graphics |
| `*_conditions.json` | `layout_patch.py` | sentences drawn piecewise at `mov`-immediate positions |

Facts the recipes rely on:

- 3D sprites: id = texture index × 1000 + region; `func_0206f82c(flags, id, x, y, …)`. Flag bit 0
  ignores the region's x/y offsets, so position changes need code patches, not region edits.
- Texture descriptors: 28-byte records at `0x020F01B0` (texture id = index); region tables lie
  back to back from `0x020ECEA8`.
- Some `vdata` files are unused copies; the game draws ARM9-embedded data instead:

| ARM9 address | Size / format | Palette | Content |
|---|---|---|---|
| `0x020B1B68` | 64×32 sprites, 4bpp | `0x020B1028` | Yes/No buttons (`btn_msg`) |
| `0x020B2B68` | 64×32 sprites, 4bpp | `0x020B1048` | prompt buttons (`btn_common`) |
| `0x020B8320` | 160×48 linear 4bpp | `0x020B8120` (placeholder) | round-banner glyph cells |
| `0x020BEA30` | 72×96 linear 4bpp | `0x020C9B80` (BG bank 4) | pause overlay mode label, 3 cells |
| `0x020BF7B0` | 160×80 linear 8bpp | `0x020C6AC0` | pause overlay seat-wind boxes |
| `0x020D56E4` | 624×32 linear 4bpp | `0x020D4204` (BG bank 13) | option/rule header plates, 3 × 208 |
| `0x020D7E64` | 80×48 linear 4bpp | `0x020D7E44` | Results / Scores headers |
| `0x020D85E4` | 184×24 linear 4bpp | `0x020D7E24` | DS Wireless Play header |
| `0x020D8E84` | 184×24 linear 4bpp | `0x020D7E04` | DS Download Play header |
| `0x020D9724` | 152×56 linear 4bpp | `0x020D7DE4` | Ranking Points header + two small labels |

The last four are drawn through a 28-byte descriptor table at `0x0210E030`
(`{sheet width, w, h, data, palette, src x, src y}`).

- Linear BG bitmaps are blitted by `func_0201e608(bg, x, y, w, [sp] h, sheet, src_x, src_y,
  sheet_width, flags)`; the low byte of `flags` is the palette bank (pixel = bank × 16 + index).
  `func_0201e8f8` is the 8bpp variant.
- Draw-banner words (`func_0207aae4`): word w uses the record list at `0x021039D0 + w × 0x18`; its
  32×32 pieces are placed side by side at y 80, centred on (256 − 32n) / 2.
- Live palettes can differ from the ROM copy (faded); find a palette by searching ARM9 for the
  savestate colours with ±1 per channel tolerance.

Finding an unknown graphic: save a melonDS state on the screen (`explore.py … save:NAME`), take
the `GPUG` section (palette RAM at +0x20, VRAM after it), render VRAM as 256-wide 8bpp bitmaps,
then search ARM9/files for a row of the graphic, either as packed 4bpp nibbles or as an
"equality pattern" (pixels compared for sameness, so the palette offset doesn't matter); a
search hit's row stride gives the sheet width.

### Text in fixed buffers

Some strings are `strcpy`'d into fixed-size buffers, so a relocated translation can still
overflow the destination. Mark the source entry with `"max_bytes"` (see `insert_text.py`).
Known case: `func_02038108` copies Rule List / Rules into the 12-byte options label at
`0x020EBCF0`.

The compiler also inlined fixed-length copies (`ldr r3, =str` followed by an
`ldrb/strb` loop of n halfword pairs, plus one trailing byte): they copy exactly the Japanese
length, so longer English is cut off **without a terminator**. A scan of the disassembly for
string literals followed by such loops found 14 sites; the wait names in `func_0208d1bc` are
patched to strcpy (`asm/winning_tiles.asm`), the rest carry `max_bytes` equal to the copy length.

Result-screen yaku rows (`func_0207cf28`): link label at x, `"%2d han"` at x + 76, so labels
must advance ≤ 79 px (checked by `tests/test_layout_and_fill.py`).

### Options screen layout

Each row's choices are drawn at x = 104 + i × (W + width("/")), where W is the pixel width of
the row's first choice string (`func_02038b0c`, `func_02039a04`; widths via `vwf_strwidth`).
The cursor brackets (6 px wide) sit inside [x, x + W], so every choice is padded with `center`
to the same W and must keep 6 px clear at both ends.

## Download Play child (`files/main.srl`)

- A complete NDS program (ARM9 0x17CCF8 bytes at `0x02000000`, uncompressed; no file system,
  all graphics embedded). It has no banner, so `dsd rom extract` fails; giving a copy the main
  ROM's banner (header `0x68`, header CRC recomputed) makes it extractable (`work/child/`).
- About 640 strings around `0x0217xxxx` are identical to main-game strings (same engine), so
  translations and engine patches could be ported by matching functions.
- **It is RSA-signed** (`multiboot_signature.yaml`). Receiving consoles verify the signature, so
  any modified child no longer runs over Download Play on stock hardware; it only works with
  patched firmware/exploits or emulators that skip the check. It is currently left untouched.

## Test harness notes

- DeSmuME's software rasterizer samples the 3D-composited UI textures inaccurately (rows
  duplicated/dropped); melonDS DS renders them correctly, so it is the default core.
- Cores can't be re-initialised in one process: one emulator per script run.
- Fixed frame waits drift between builds (screens only accept input in windows); use screen
  signatures (`sig`/`until`) and routes (`@main`).
- Save states contain RAM (including ARM9 code), so they are only valid for the build that made
  them.
