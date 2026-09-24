; HHON.OVL, the insect box (PLAN TXT-05). Included by vwf.asm inside
; `.open HHON_PATH, 0x80079A08`: a consumer of sysmsg_draw's return value, which is now a
; width in pixels (asm/walkers.asm, surface 9), and the two entry walkers' sites.

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

; ---- the two entry walkers (asm/hhon_resident.asm has the bodies and the design) ----------
; hhon_entry_draw 0x8007C278, the grid's panel.
.org 0x8007C2B0
.area 4
.if ORIGINAL
    ori     s3, zero, 0x8000        ; stock: the end word, just before the loop
.else
    jal     vwf_hhon_grid_origin    ; (its delay slot is the loop's first instruction)
.endif
.endarea

.org 0x8007C2C4
.area 4
.if ORIGINAL
    addiu   s0, s0, 2               ; stock: next word; delay slot `lhu v1,0(s0)`
.else
    jal     vwf_hhon_step
.endif
.endarea

.org 0x8007C2D8
.area 4
.if ORIGINAL
    addiu   s1, s1, 0xC             ; stock: y += 12, in the delay slot of `beqz v0`
.else
    nop                             ; vwf_hhon_step steps y for a cell that is not English
.endif
.endarea

.org 0x8007C2E4
.area 3*4
.if ORIGINAL
    addiu   s2, s2, -0xE            ; stock: a break moves one column left ...
    j       0x8007C2B4
    addiu   s1, zero, 0x20          ; ... and back to the top
.else
    j       vwf_hhon_grid_break
    nop
    nop
.endif
.endarea

; hhon_text_scroll_v 0x8007C1C4, the notebook page.
.org 0x8007C20C
.area 4
.if ORIGINAL
    ori     s5, zero, 0x8000        ; stock: the end word
.else
    jal     vwf_hhon_nb_origin      ; (its delay slot sets s4, the column top)
.endif
.endarea

.org 0x8007C228
.area 4
.if ORIGINAL
    addiu   s0, s0, 2               ; stock: next word; delay slot `lhu v1,0(s0)`
.else
    jal     vwf_hhon_step
.endif
.endarea

.org 0x8007C23C
.area 4
.if ORIGINAL
    addiu   s1, s1, 0xC             ; stock: y += 12, in the delay slot of `beqz v0`
.else
    nop
.endif
.endarea

.org 0x8007C248
.area 3*4
.if ORIGINAL
    addiu   s2, s2, -0xE            ; stock: one column left ...
    j       0x8007C214
    subu    s1, s4, s3              ; ... back to the scrolled top
.else
    j       vwf_hhon_nb_break
    nop
    nop
.endif
.endarea

; The insect box's copy of the cage HUD (asm/walkers.asm, CAGE_DATE_Y): its date goes a row
; below the size too, off the name's row.
.org 0x8007C4CC
.area 4
.if ORIGINAL
    addiu   a1, zero, 0x1A          ; stock: y 26, the name's row
.else
    addiu   a1, zero, CAGE_DATE_Y
.endif
.endarea
