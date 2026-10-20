; Full-width Latin letters, digits and a few symbols (Shift-JIS Ａ-Ｚ ａ-ｚ ０-９ ！？ etc.) are drawn
; with the proportional VWF glyphs. Player names are typed and stored as full-width characters
; (the 3D name font, TexNameFont, only knows full-width codes), so this keeps storage compatible
; while names look like normal English text everywhere the 2D text engine draws them.
;
; func_02020764 (12x12 full-width blitter) now returns its advance in r0, like vwf_blit.

.org 0x02020764
    ldr     pc, [pc, #-4]
    .word   vwf_blit_fw

; func_02020e7c: full-width advance (was + 12)
.org 0x02020EF8
    add     r7, r7, r0

; func_02020d84: func_020205d0's last call is the full-width blitter, so r0 = advance
.org 0x02020E48
    add     r9, r9, r0

; func_020209b0: double-byte advance of the char at [sp+0x2C] (was [sp+0x28] = 12)
.org 0x02020BF8
    blne    vwf_adv_db_sp2c

; func_0208ec24: double-byte advance into r1 (was [sp+0x24] = 12); r0 is dead here
.org 0x0208EF74
    blne    vwf_adv_db_sp28

.ifdef DEBUG_FWLOG
; Debug builds only: log every full-width glyph lookup (func_02020f90) with its caller.
.org 0x02020F90
    ldr     pc, [pc, #-4]
    .word   fw_lookup_log
.endif
