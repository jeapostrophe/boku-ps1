; HHON.OVL, the insect box (PLAN TXT-05). Included by vwf.asm inside
; `.open HHON_PATH, 0x80079A08`. Its two entry walkers are not patched
; (research/vwf-prototype.md § "The HHON walkers"); what is here is a consumer of
; sysmsg_draw's return value, which is now a width in pixels (asm/walkers.asm, surface 9).

; The insect's name at (0x3D, 0x1A), then the next item 12 x count after it.
.org 0x8007C46C
.area 3*4
.if ORIGINAL
    sll     v1, v0, 1
    addu    v1, v1, v0
    sll     v1, v1, 2               ; stock: v1 = 12 * count
.else
    move    v1, v0                  ; the width
    nop
    nop
.endif
.endarea
