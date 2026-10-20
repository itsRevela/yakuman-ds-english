; Variable-width font engine hack for Yakuman DS (AMJJ).
;
; Single-byte characters are drawn from our own 8x12 font (font/vwf12.txt -> vwf_font.bin) and
; advance by a per-glyph width instead of a fixed 6 px. The two wrapping renderers get pixel-based
; word wrap at spaces, and no longer strcpy text into 256-byte stack buffers (English glossary
; entries are longer than that).
;
; Included from asm/main.asm, which opens arm9.bin. See docs/TECHNICAL_NOTES.md for the call graph.

; ------------------------------------------------------------------------------------------------
; Game functions / data used by the hooks
GetCanvasIndex  equ 0x0201F3A4
GetCanvas       equ 0x0201F550      ; (index) -> canvas* or NULL; +0 width u16, +2 height u16, +0x10 pixels
GetFullwidthGlyph equ 0x020210B0  ; (code) -> pointer to 12 big-endian u16 rows (falls back to ？)

; ------------------------------------------------------------------------------------------------
; Glyph blitter (single-byte path). All callers pass (x, y, char, color); now returns the advance.
.org 0x0202068C
    ldr     pc, [pc, #-4]
    .word   vwf_blit

; func_02020e7c (single colour string): advance by the returned width instead of 6.
.org 0x02020F10
    add     r7, r7, r0

; func_02020d84 (coloured/bold string): func_02020514's last call is the blitter, so r0 = width.
.org 0x02020E68
    add     r9, r9, r0

; ------------------------------------------------------------------------------------------------
; func_020209b0 (main wrapped / typewriter renderer)

; Keep a pointer to the caller's string instead of copying it into the 256-byte buffer.
.org 0x02020A2C
    str     r1, [sp, #0x30]
.org 0x02020A54
    ldr     r0, [sp, #0x30]

; Single-byte advance: width of the char in the 3-byte char buffer at [sp+0x2C]. Flags must survive.
.org 0x02020BF0
    bleq    vwf_adv_sb_sp2c

; Replace the character-count wrap (and kinsoku checks) with pixel word wrap.
.org 0x02020C0C
    ldr     r0, [sp, #0x30]
    add     r0, r0, r7              ; next character
    mov     r1, r10                 ; x after the current character
    ldr     r2, [sp, #0xC]          ; line start x
    mov     r3, r8                  ; style
    bl      vwf_wrap_check
    cmp     r0, #0
    blt     0x02020C74              ; no wrap
    add     r7, r7, r0              ; skip the space we break at
    b       0x02020C5C              ; original newline code

; ------------------------------------------------------------------------------------------------
; func_0208ec24 (glossary renderer with tappable cross-references)

.org 0x0208ECBC
    str     r1, [sp, #0x4C]         ; was: strcpy(sp+0x49, entry->description)
.org 0x0208ED00
    ldr     r0, [sp, #0x4C]

; Link hit-box: x1 = x0 + advance (was x0 + units * 6)
.org 0x0208EEB4
    bl      vwf_adv_any_sp28
.org 0x0208EEBC
    add     r0, r0, r1
.org 0x0208EEF8
    bl      vwf_adv_any_sp28
.org 0x0208EEFC
    add     r1, r1, r2

; Single-byte advance (r0 is live, flags must survive).
.org 0x0208EF68
    bleq    vwf_adv_sb_sp28

; Pixel word wrap.
.org 0x0208EF9C
    mov     r6, r5                  ; original: clear the "just wrapped" flag
    ldr     r0, [sp, #0x4C]
    add     r0, r0, r9
    ldr     r1, [sp, #0x8]
    ldr     r2, [sp, #0xC]
    mov     r3, r10
    bl      vwf_wrap_check
    cmp     r0, #0
    blt     0x0208ED00
    add     r9, r9, r0
    b       0x0208EFE8
