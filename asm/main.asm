; Yakuman DS English translation — ARM9 patches.
; Assembled by tools/build.py:  armips asm/main.asm -strequ ARM9_BIN <path> -sym <symfile>
;
; Memory map of the extension (see docs/TECHNICAL_NOTES.md, "Free space strategy"):
;   0x0210FBE0 - 0x0212A200   original static BSS (zero padding in the file, cleared at boot)
;   0x0212A200 - CODE_END     hack code + font                   (this file)
;   TEXT_START - ...          relocated English strings          (tools/insert_text.py)
; The heap start literal (OS_GetInitArenaLo) is moved past the end by tools/build.py.

.nds
.arm

EXT_START       equ 0x0212A200
VWF_CODE_START  equ EXT_START
VWF_CODE_SIZE   equ 0x4000
TEXT_START      equ VWF_CODE_START + VWF_CODE_SIZE

.open ARM9_BIN, 0x02000000

; ---- patches to existing code (call sites) ----
.include "asm/vwf.asm"
.include "asm/strwidth.asm"
.include "asm/dictionary.asm"
.include "asm/fullwidth.asm"
.include "asm/name_entry.asm"
.include "asm/challenge.asm"
.include "asm/records.asm"
.include "asm/result_words.asm"
.include "asm/winning_tiles.asm"

; ---- new code and data ----
.org VWF_CODE_START
.area VWF_CODE_SIZE
.include "asm/vwf_routines.asm"
.include "asm/challenge_routines.asm"
.pool
.align 4
vwf_font:
    .incbin "work/build/vwf_font.bin"
.endarea

.definelabel english_text_base, TEXT_START

.close
