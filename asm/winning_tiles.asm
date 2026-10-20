; "Winning Tiles" panel (func_0208d1bc): the wait name is built in a 256-byte stack buffer at
; sp+0x1C. Four names were copied with inline loops sized for the Japanese (9 bytes for
; 単騎待ち / 嵌張待ち / 辺張待ち, 5 for 両面), which cut the English short and left it
; unterminated. Each loop is replaced by strcpy; the literal load before each loop is kept.

Strcpy          equ 0x02018620      ; (dst, src) -> dst

; 単騎待ち (r3 = name), then falls through to func_0208d3c8, which takes no arguments.
.org 0x0208D200
    add r0, sp, #0x1C
    mov r1, r3
    bl Strcpy
    b 0x0208D228

; 嵌張待ち (r3 = name)
.org 0x0208D238
    add r0, sp, #0x1C
    mov r1, r3
    bl Strcpy
    b 0x0208D35C

; 辺張待ち (r3 = name)
.org 0x0208D270
    add r0, sp, #0x1C
    mov r1, r3
    bl Strcpy
    b 0x0208D35C

; 両面 (r2 = prefix); the code then appends 単騎待ち with strcat at 0x0208D334.
.org 0x0208D2F4
    add r0, sp, #0x1C
    mov r1, r2
    bl Strcpy
    b 0x0208D334
