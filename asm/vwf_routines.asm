; VWF engine routines (placed in the extension area by asm/main.asm).

; vwf_blit(r0 = x, r1 = y, r2 = char, r3 = colour) -> r0 = advance in pixels
vwf_blit:
.ifdef DEBUG_FWLOG
    stmdb   sp!, {r0, r1, r3}
    ldr     r0, =fwlog
    ldr     r1, [r0, #4]            ; single-byte glyph count
    add     r1, r1, #1
    str     r1, [r0, #4]
    cmp     r2, #0x100              ; a 2-byte code reaching the single-byte blitter: log it
    blo     @@nolog
    ldr     r1, [r0]
    and     r3, r1, #0x7F
    add     r3, r0, r3, lsl #3
    str     r2, [r3, #8]
    str     lr, [r3, #12]
    add     r1, r1, #1
    str     r1, [r0]
@@nolog:
    ldmia   sp!, {r0, r1, r3}
.endif
    stmdb   sp!, {r4-r10, lr}
    mov     r4, r0
    mov     r5, r1
    and     r6, r2, #0xFF
    and     r7, r3, #0xFF
    ldr     r8, =vwf_font
    ldrb    r9, [r8, r6]            ; advance = return value
    bl      GetCanvasIndex
    bl      GetCanvas
    cmp     r0, #0
    beq     @@done
    cmp     r4, #0
    blt     @@done
    cmp     r5, #0
    blt     @@done
    ldrh    r1, [r0, #2]            ; height
    add     r2, r5, #12
    cmp     r2, r1
    bge     @@done                  ; same vertical rule as the original blitter
    ldrh    r1, [r0]                ; width = row stride
    sub     r10, r1, r4             ; columns left on this row
    cmp     r10, #0
    ble     @@done
    cmp     r10, #8
    movgt   r10, #8
    ldr     r2, [r0, #0x10]
    mla     r3, r5, r1, r4
    add     r2, r2, r3              ; destination of the glyph's top-left pixel
    add     r3, r8, #0x100
    add     r6, r6, r6, lsl #1
    add     r3, r3, r6, lsl #2      ; rows = font + 0x100 + char * 12
    mov     r6, #12
@@row:
    ldrb    r12, [r3], #1
    cmp     r12, #0
    beq     @@next_row
    mov     r0, #0
@@col:
    mov     lr, #0x80
    tst     r12, lr, lsr r0
    strneb  r7, [r2, r0]
    add     r0, r0, #1
    cmp     r0, r10
    blt     @@col
@@next_row:
    add     r2, r2, r1
    subs    r6, r6, #1
    bne     @@row
@@done:
    mov     r0, r9
    ldmia   sp!, {r4-r10, lr}
    bx      lr

; Called with bleq from func_020209b0: r0 = advance of the single-byte char at caller's [sp+0x2C].
; Must not touch the flags. Clobbers r1.
vwf_adv_sb_sp2c:
    ldrb    r0, [sp, #0x2C]
    ldr     r1, =vwf_font
    ldrb    r0, [r1, r0]
    bx      lr

; Called with bleq from func_0208ec24: r1 = advance of the single-byte char at caller's [sp+0x28].
; Must not touch the flags or r0. Clobbers r12.
vwf_adv_sb_sp28:
    ldrb    r1, [sp, #0x28]
    ldr     r12, =vwf_font
    ldrb    r1, [r12, r1]
    bx      lr

; r1 = advance of the (single- or double-byte) char at caller's [sp+0x28]. Preserves r0, r2.
vwf_adv_any_sp28:
    ldrb    r1, [sp, #0x28]
    cmp     r1, #0x81
    blo     @@single
    cmp     r1, #0x9F
    bls     @@double
    cmp     r1, #0xE0
    blo     @@single
    cmp     r1, #0xEA
    bhi     @@single
@@double:
    stmdb   sp!, {r0, lr}
    ldrb    r0, [sp, #0x28 + 8]
    ldrb    r1, [sp, #0x29 + 8]
    orr     r0, r1, r0, lsl #8
    bl      fw_advance
    mov     r1, r0
    ldmia   sp!, {r0, lr}
    bx      lr
@@single:
    ldr     r12, =vwf_font
    ldrb    r1, [r12, r1]
    bx      lr

; vwf_wrap_check(r0 = next char ptr, r1 = x after current char, r2 = line start x, r3 = style)
;   -> r0 = bytes to skip before breaking the line, or -1 for no break.
; Breaks only at a space, when the following word would end past the box. Box width comes from the
; style's character limit (style+0x20, half-width units): units * 6 + units/2 * spacing.
vwf_wrap_check:
    stmdb   sp!, {r4-r8, lr}
    ldr     r4, [r3, #0x20]
    cmp     r4, #0
    ble     @@no_wrap
    ldrb    r5, [r0]
    cmp     r5, #0x20
    bne     @@no_wrap
    ldr     r6, [r3]                ; letter spacing
    add     r7, r4, r4, lsl #1
    add     r2, r2, r7, lsl #1      ; start + units * 6
    mov     r7, r4, lsr #1
    mla     r2, r7, r6, r2          ; + units / 2 * spacing = right edge
    ldr     r8, =vwf_font
    ldrb    r7, [r8, #0x20]
    add     r1, r1, r7
    add     r1, r1, r6              ; past the space
    add     r0, r0, #1
@@word:
    ldrb    r5, [r0], #1
    cmp     r5, #0x00
    cmpne   r5, #0x20
    cmpne   r5, #0x21               ; newline
    beq     @@measured
    cmp     r5, #0x3C
    cmpne   r5, #0x3E
    cmpne   r5, #0x23
    beq     @@word                  ; zero-width control codes
    cmp     r5, #0x81
    blo     @@single
    cmp     r5, #0x9F
    bls     @@double
    cmp     r5, #0xE0
    blo     @@single
    cmp     r5, #0xEA
    bhi     @@single
@@double:
    ldrb    r7, [r0], #1
    cmp     r7, #0
    beq     @@measured
    stmdb   sp!, {r0-r2}
    orr     r0, r7, r5, lsl #8
    bl      fw_advance
    mov     r7, r0
    ldmia   sp!, {r0-r2}
    add     r1, r1, r7
    add     r1, r1, r6
    b       @@word
@@single:
    ldrb    r7, [r8, r5]
    add     r1, r1, r7
    add     r1, r1, r6
    b       @@word
@@measured:
    sub     r1, r1, r6              ; no spacing after the last character
    sub     r1, r1, #1              ; glyph advances include a 1 px gap on the right
    cmp     r1, r2
    movgt   r0, #1
    bgt     @@return
@@no_wrap:
    mvn     r0, #0
@@return:
    ldmia   sp!, {r4-r8, lr}
    bx      lr

; vwf_strwidth(r0 = string) -> r0 = pixel width of its widest line. Replaces strlen() * 6.
; Control codes < > # are zero-width, '!' starts a new line, Shift-JIS characters use fw_advance
; (12 px, or the VWF width for full-width Latin). Preserves r3 and r12 (the strlen it replaces
; only touched r0-r2).
vwf_strwidth:
    stmdb   sp!, {r3, r12, lr}
    ldr     r3, =vwf_font
    mov     r1, #0                  ; current line
    mov     r2, #0                  ; widest line
@@loop:
    ldrb    r12, [r0], #1
    cmp     r12, #0
    beq     @@end
    cmp     r12, #0x21
    beq     @@newline
    cmp     r12, #0x3C
    cmpne   r12, #0x3E
    cmpne   r12, #0x23
    beq     @@loop
    cmp     r12, #0x81
    blo     @@single
    cmp     r12, #0x9F
    bls     @@double
    cmp     r12, #0xE0
    blo     @@single
    cmp     r12, #0xEA
    bhi     @@single
@@double:
    ldrb    r3, [r0], #1            ; trail byte (r3 is restored below)
    cmp     r3, #0
    beq     @@end
    stmdb   sp!, {r0-r2}
    orr     r0, r3, r12, lsl #8
    bl      fw_advance
    mov     r12, r0
    ldmia   sp!, {r0-r2}
    add     r1, r1, r12
    ldr     r3, =vwf_font
    b       @@loop
@@single:
    ldrb    r12, [r3, r12]
    add     r1, r1, r12
    b       @@loop
@@newline:
    cmp     r1, r2
    movgt   r2, r1
    mov     r1, #0
    b       @@loop
@@end:
    cmp     r1, r2
    movgt   r2, r1
    mov     r0, r2
    ldmia   sp!, {r3, r12, lr}
    bx      lr

; Width of the string at r0 in units of 6 px, rounded up: a drop-in for strlen() where the game
; positions things at strlen * 6 (e.g. the records screen's dot leaders). Clobbers r1, r2.
vwf_width_units6:
    stmdb   sp!, {lr}
    bl      vwf_strwidth
    add     r0, r0, #5
    ldr     r1, =0xAAAB             ; n / 6 == (n * 0xAAAB) >> 18 for n < 0x10000
    mul     r2, r0, r1
    mov     r0, r2, lsr #18
    ldmia   sp!, {lr}
    bx      lr

; Dictionary drawer: r7 (pixel column) += advance of the character in r12. Preserves r0-r3.
dict_adv_r12_r7:
    stmdb   sp!, {r0}
    and     r12, r12, #0xFF
    ldr     r0, =vwf_font
    ldrb    r12, [r0, r12]
    add     r7, r7, r12
    ldmia   sp!, {r0}
    bx      lr

; Dictionary hit-test: r6 (pixel column) += advance of the character in r0. Must not touch the
; flags (called with blne). Clobbers r0.
dict_adv_r0_r6:
    stmdb   sp!, {r1}
    and     r0, r0, #0xFF
    ldr     r1, =vwf_font
    ldrb    r0, [r1, r0]
    add     r6, r6, r0
    ldmia   sp!, {r1}
    bx      lr

; ------------------------------------------------------------------------------------------------
; Full-width Latin support (see asm/fullwidth.asm)

; fw_ascii(r0 = Shift-JIS code) -> r0 = single-byte glyph to draw with the VWF font, or 0 if the
; character keeps its 12x12 full-width glyph. Clobbers r1, r2.
fw_ascii:
    ldr     r1, =0x824F             ; ０-９
    sub     r2, r0, r1
    cmp     r2, #9
    addls   r0, r2, #0x30
    bxls    lr
    ldr     r1, =0x8260             ; Ａ-Ｚ
    sub     r2, r0, r1
    cmp     r2, #25
    addls   r0, r2, #0x41
    bxls    lr
    ldr     r1, =0x8281             ; ａ-ｚ
    sub     r2, r0, r1
    cmp     r2, #25
    addls   r0, r2, #0x61
    bxls    lr
    ldr     r1, =fw_symbol_table
@@symbol:
    ldrh    r2, [r1], #4
    cmp     r2, #0
    beq     @@none
    cmp     r2, r0
    bne     @@symbol
    ldrh    r0, [r1, #-2]
    bx      lr
@@none:
    mov     r0, #0
    bx      lr

; fw_advance(r0 = Shift-JIS code) -> r0 = advance in pixels. Preserves r1-r3, r12.
fw_advance:
    stmdb   sp!, {r1-r3, r12, lr}
    bl      fw_ascii
    cmp     r0, #0
    moveq   r0, #12
    ldrne   r1, =vwf_font
    ldrneb  r0, [r1, r0]
    ldmia   sp!, {r1-r3, r12, lr}
    bx      lr

; Replacement for func_02020764 (12x12 full-width blitter): (r0 = x, r1 = y, r2 = code, r3 = colour)
; -> r0 = advance. Full-width Latin goes through vwf_blit; everything else is drawn as before.
vwf_blit_fw:
.ifdef DEBUG_FWLOG
    ; Debug builds only (build.py --asm-define DEBUG_FWLOG): record (code, caller) of every
    ; full-width glyph drawn into a 128-entry ring buffer, to find which code draws a string.
    stmdb   sp!, {r0, r1, r3}
    ldr     r0, =fwlog
    ldr     r1, [r0]
    and     r3, r1, #0x7F
    add     r3, r0, r3, lsl #3
    str     r2, [r3, #8]
    str     lr, [r3, #12]
    add     r1, r1, #1
    str     r1, [r0]
    ldmia   sp!, {r0, r1, r3}
.endif
    stmdb   sp!, {r4-r8, lr}
    mov     r4, r0
    mov     r5, r1
    mov     r6, r2
    mov     r7, r3
    mov     r0, r2
    bl      fw_ascii
    cmp     r0, #0
    beq     @@fullwidth
    mov     r2, r0
    mov     r0, r4
    mov     r1, r5
    mov     r3, r7
    ldmia   sp!, {r4-r8, lr}
    b       vwf_blit
@@fullwidth:
    bl      GetCanvasIndex
    bl      GetCanvas
    movs    r8, r0
    beq     @@done
    cmp     r4, #0
    blt     @@done
    cmp     r5, #0
    blt     @@done
    ldrh    r2, [r8]                ; width
    add     r0, r4, #12
    cmp     r0, r2
    bge     @@done
    ldrh    r2, [r8, #2]            ; height
    add     r0, r5, #12
    cmp     r0, r2
    bge     @@done
    mov     r0, r6
    bl      GetFullwidthGlyph
    cmp     r0, #0
    beq     @@done
    ldrh    r2, [r8]
    ldr     r3, [r8, #0x10]
    mla     r1, r5, r2, r4
    add     r3, r3, r1              ; destination of the top-left pixel
    and     r7, r7, #0xFF
    mov     r6, #12
@@row:
    ldrb    r1, [r0], #1
    ldrb    r12, [r0], #1
    orr     r12, r12, r1, lsl #8    ; 16-bit row, bit 15 = leftmost pixel
    mov     r1, #0
@@col:
    mov     lr, #0x8000
    tst     r12, lr, lsr r1
    strneb  r7, [r3, r1]
    add     r1, r1, #1
    cmp     r1, #12
    blt     @@col
    add     r3, r3, r2
    subs    r6, r6, #1
    bne     @@row
@@done:
    mov     r0, #12
    ldmia   sp!, {r4-r8, lr}
    bx      lr

; Called with blne from func_020209b0: r0 = advance of the double-byte char at caller's [sp+0x2C].
vwf_adv_db_sp2c:
    ldrb    r0, [sp, #0x2C]
    ldrb    r1, [sp, #0x2D]
    orr     r0, r1, r0, lsl #8
    b       fw_advance

; Called with blne from func_0208ec24: r1 = advance of the double-byte char at caller's [sp+0x28].
vwf_adv_db_sp28:
    stmdb   sp!, {lr}
    ldrb    r0, [sp, #0x28 + 4]
    ldrb    r1, [sp, #0x29 + 4]
    orr     r0, r1, r0, lsl #8
    bl      fw_advance
    mov     r1, r0
    ldmia   sp!, {lr}
    bx      lr

.align 4
fw_symbol_table:                    ; Shift-JIS code, glyph byte
    .halfword 0x8149, 0xA1          ; ！
    .halfword 0x8148, 0x3F          ; ？
    .halfword 0x8195, 0x26          ; ＆
    .halfword 0x8193, 0x25          ; ％
    .halfword 0x8190, 0x24          ; ＄
    .halfword 0x8147, 0x3B          ; ；
    .halfword 0x8146, 0x3A          ; ：
    .halfword 0x8166, 0x27          ; ’
    .halfword 0x8144, 0x2E          ; ．
    .halfword 0x8143, 0x2C          ; ，
    .halfword 0x815E, 0x2F          ; ／
    .halfword 0x817B, 0x2B          ; ＋
    .halfword 0x817C, 0x2D          ; －
    .halfword 0, 0

.ifdef DEBUG_FWLOG
; Replaces the first two instructions of func_02020f90 (code in r0, caller in lr); uses only
; registers that are free at that function's entry, then resumes it.
fw_lookup_log:
    ldr     r2, =fwlog
    ldr     r1, [r2]
    and     r3, r1, #0x7F
    add     r3, r2, r3, lsl #3
    str     r0, [r3, #8]
    str     lr, [r3, #12]
    add     r1, r1, #1
    str     r1, [r2]
    mov     r1, r0, asr #0x8
    and     r12, r0, #0xFF
    ldr     pc, =0x02020F98
.pool
.align 4
fwlog:
    .word 0, 0
    .fill 0x400
.endif
