; Records (stats) screen, func_02025708.
; Each stat label is cut at its first "・" (func_020241d0); the game then draws "・" leader
; sprites from x + strlen(label) * 6 for 11 - strlen/2 sprites, i.e. up to 132 px. With the VWF
; the label's width is not strlen * 6, so measure it in 6 px units instead.
.org 0x02025828
    bl vwf_width_units6
