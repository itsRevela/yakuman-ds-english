; Challenge mode course buttons (func_02042978).
; The Japanese course name (two big kanji) sat at the top-left of the 94x68 button with "コース"
; at its lower right. The English names differ in width, so each is centred on the button using
; a per-course x offset (course_name_dx, filled in by tools/gfx from the rendered label widths),
; and the name and "Course" are stacked and centred vertically.

; Course name: x = button x + course_name_dx[course] (was + 8), y = button y + 14 (was + 4).
; r7 holds the course index (0-3) in all three draw paths (normal/selected/locked).
.org 0x02042B98
    bl course_name_x_r2
    add r3, r3, #0xE
.org 0x02042BC0
    bl course_name_x_r1
    add r3, r0, #0xE
.org 0x02042BF0
    bl course_name_x_r1
    add r3, r0, #0xE

; "Course": (x + 30, y + 44) -> (x + 20, y + 38).
.org 0x02042B08
    add r2, r2, #0x14
    add r3, r3, #0x26
