; Helpers for asm/challenge.asm (placed in the extension code area).

; r2 = r2 + course_name_dx[r7]; preserves everything else.
course_name_x_r2:
    push {r0}
    ldr r0, =course_name_dx
    ldrsb r0, [r0, r7]
    add r2, r2, r0
    pop {r0}
    bx lr

; r2 = r1 + course_name_dx[r7]; preserves everything else.
course_name_x_r1:
    ldr r2, =course_name_dx
    ldrsb r2, [r2, r7]
    add r2, r1, r2
    bx lr

.pool
; Per-course x offsets of the course name on its button; tools/gfx/assets.py writes the real
; values (centring each rendered name on the 94 px button). 8 is the original offset.
course_name_dx:
    .byte 8, 8, 8, 8
.align 4
