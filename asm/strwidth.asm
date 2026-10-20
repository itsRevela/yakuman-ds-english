; Text-width calculations: the game centres/sizes text with strlen(s) * 6 (or strlen * 12 / 2),
; which assumes every byte is 6 px wide. Each such site now calls vwf_strwidth (pixel width of the
; widest line, using the VWF advances) and multiplies by 1 (or 2 / 2) instead.
; Sites found with tools/find_strlen_width.py.
;
; func_020a6b24 (strlen / 2 * 10, a 10 px per character font) is intentionally not patched.

; --- strlen * 6 -------------------------------------------------------------------------------
.org 0x02025A94
    bl      vwf_strwidth
    mov     r1, #1
.org 0x02025B3C
    bl      vwf_strwidth
    mov     r1, #1
.org 0x02025BD0
    bl      vwf_strwidth
    mov     r1, #1
.org 0x0206DE0C
    bl      vwf_strwidth
    mov     r1, #1
.org 0x02075278
    bl      vwf_strwidth
    mov     r1, #1
.org 0x020752B4
    bl      vwf_strwidth
    mov     r1, #1
.org 0x0207C06C
    bl      vwf_strwidth
    mov     r1, #1
.org 0x0207C0C0
    bl      vwf_strwidth
    mov     r1, #1
.org 0x0208176C
    bl      vwf_strwidth
    mov     r2, #1
.org 0x0208D100
    bl      vwf_strwidth
    mov     r1, #1
.org 0x0208D360
    bl      vwf_strwidth
    mov     r1, #1

; --- strlen * 12 / 2 ----------------------------------------------------------------------------
.org 0x02038B4C
    bl      vwf_strwidth            ; first of two summed strings
.org 0x02038B58
    bl      vwf_strwidth
    mov     r1, #2
.org 0x02039A24
    bl      vwf_strwidth
    mov     r1, #2
.org 0x02071484
    bl      vwf_strwidth
    mov     r1, #2
.org 0x020721E4
    bl      vwf_strwidth
    mov     r1, #2
.org 0x02090A34
    bl      vwf_strwidth
    mov     r1, #2
.org 0x0209EEA0
    bl      vwf_strwidth
    mov     r1, #2
.org 0x0209EFD0
    bl      vwf_strwidth
    mov     r1, #2
.org 0x0209EBC0
    bl      vwf_strwidth            ; max over menu items...
.org 0x0209EBD4
    mov     r0, #2                  ; ...then * 12 / 2
