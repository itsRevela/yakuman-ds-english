; Draw banner words (func_0207aae4): word w is shown from the record list at
; 0x021039D0 + w * 0x18 -- up to 7 records (sprite, 0x65, 0) ended by (0xFF, 0x66, 0) -- as
; 32x32 sprites of vdata/majan/obj_strResult placed side by side, centred on screen, at y 80.
; The Japanese words shared kanji sprites (四, 流). The English words are split over the sheet
; as drawn by gfx/sprites.json ("majan/obj_strResult"); keep the two in step. "Four" is one
; two-sprite piece shared by Four Kans / Four Winds / Four Riichi.

RESULT_WORDS    equ 0x021039D0
RESULT_WORD_LEN equ 0x18

.macro result_word_end, n
    .if . != RESULT_WORDS + (n + 1) * RESULT_WORD_LEN
        .error "result word table entry is not 0x18 bytes"
    .endif
.endmacro

.org RESULT_WORDS
; 0 流局 -> Draw
    .byte  0, 0x65, 0,   1, 0x65, 0,   0xFF, 0x66, 0
    .byte  0, 0, 0,   0, 0, 0,   0, 0, 0,   0, 0, 0,   0, 0, 0
    result_word_end 0
; 1 四槓流れ -> Four Kans
    .byte  2, 0x65, 0,   3, 0x65, 0,   4, 0x65, 0,   5, 0x65, 0,   0xFF, 0x66, 0
    .byte  0, 0, 0,   0, 0, 0,   0, 0, 0
    result_word_end 1
; 2 四風連打 -> Four Winds
    .byte  2, 0x65, 0,   3, 0x65, 0,   6, 0x65, 0,   7, 0x65, 0,   0xFF, 0x66, 0
    .byte  0, 0, 0,   0, 0, 0,   0, 0, 0
    result_word_end 2
; 3 九種九牌 -> Nine Terminals
    .byte 10, 0x65, 0,  11, 0x65, 0,  12, 0x65, 0,  13, 0x65, 0,  14, 0x65, 0,   0xFF, 0x66, 0
    .byte  0, 0, 0,   0, 0, 0
    result_word_end 3
; 4 四家リーチ流れ -> Four Riichi
    .byte  2, 0x65, 0,   3, 0x65, 0,   8, 0x65, 0,   9, 0x65, 0,   0xFF, 0x66, 0
    .byte  0, 0, 0,   0, 0, 0,   0, 0, 0
    result_word_end 4
; 5 チョンボ -> Chombo
    .byte 15, 0x65, 0,  16, 0x65, 0,  17, 0x65, 0,   0xFF, 0x66, 0
    .byte  0, 0, 0,   0, 0, 0,   0, 0, 0,   0, 0, 0
    result_word_end 5
; 6 三家和 -> Triple Ron
    .byte 18, 0x65, 0,  19, 0x65, 0,  20, 0x65, 0,  21, 0x65, 0,   0xFF, 0x66, 0
    .byte  0, 0, 0,   0, 0, 0,   0, 0, 0
    result_word_end 6
