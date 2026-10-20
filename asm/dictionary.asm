; Mahjong Dictionary description pages.
;
; The dictionary lays out descriptions itself, in three functions that must agree:
;   func_02074b24  pager      - counts lines/pages (wraps after 40 bytes, '!' = newline, 8 lines/page)
;   func_02074ecc  drawer     - draws runs of text with func_02020e7c at x = byte column * 6 + 3
;   func_02074cac  hit-test   - rebuilds link boxes for touch input with the same byte * 6 geometry
;
; English descriptions are pre-wrapped by tools/insert_text.py ("wrap" layout key), so the byte
; count wrap is disabled (threshold raised past any line), and the column counters now count
; pixels using the VWF advance table.

DICT_NO_WRAP equ 0xFF

; --- pager --------------------------------------------------------------------------------------
.org 0x02074BCC
    cmp     lr, #DICT_NO_WRAP

; --- drawer -------------------------------------------------------------------------------------
.org 0x02074F30
    mov     r5, r7                  ; was: mul r5, r7, r0 (x = column * 6)
.org 0x02074F8C
    cmp     r7, #DICT_NO_WRAP
.org 0x0207504C
    bl      dict_adv_r12_r7         ; was: add r7, r7, #1
.org 0x02075054
    add     r0, r7, #3              ; run width = end x - start x (was: bytes * 6)
    sub     r0, r0, r9

; --- hit-test -----------------------------------------------------------------------------------
.org 0x02074CF8
    mov     r5, r6                  ; was: mul r5, r6, r4
.org 0x02074D3C
    cmp     r6, #DICT_NO_WRAP
.org 0x02074D80
    blne    dict_adv_r0_r6          ; was: addne r6, r6, #1 (flags must survive)
.org 0x02074D88
    add     r9, r6, #3              ; link width = end x - start x (was: bytes * 6)
    sub     r9, r9, r5
