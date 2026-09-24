; MUSI.OVL, bug sumo (PLAN TXT-05). Included by vwf.asm inside `.open MUSI_PATH, 0x80079A08`.
; The move-name walkers step through the width table, and the three places that turned
; sysmsg_draw's glyph count into pixels take its width instead (asm/walkers.asm, surface 9).
; The move names themselves (musi@2C) are never drawn in retail, so the build leaves their
; bytes (boku.arrays.UNREACHABLE); the walkers stay hooked for the day a path is found.

SUMO_FIELD equ 8 * 12               ; the right-aligned names' field: eight 12-px cells

; ---- surfaces 25, 26: the move names, 0x80084F64 and 0x800850D8 -------------------------
.org 0x800850A0
.area 4
.if ORIGINAL
    addiu   s1, s1, 0xC             ; stock: x += 12; delay slot `lhu a0,0(s0)`
.else
    jal     vwf_step_s1_s0
.endif
.endarea

.org 0x80085208
.area 4
.if ORIGINAL
    addiu   s1, s1, 0xC             ; stock: x += 12; delay slot `lhu a3,0(s0)`
.else
    jal     vwf_step_s1_s0
.endif
.endarea

; ---- sysmsg_draw's consumers -------------------------------------------------------------
; A name, then the next item 12 x count after it.
.org 0x8007D474
.area 3*4
.if ORIGINAL
    sll     v1, v0, 1
    addu    v1, v1, v0
    sll     s1, v1, 2               ; stock: s1 = 12 * count
.else
    nop
    nop
    move    s1, v0                  ; the width
.endif
.endarea

; Two names right-aligned in SUMO_FIELD, their count taken by drawing them off screen first
; (x 0x258): x = base + 12 * (8 - count). The first multiplies through sllv by s5, which
; is 1 there (0x8007D7C8), so both are 12 * (8 - count); now SUMO_FIELD - width.
.org 0x8007D874
.area 4
.if ORIGINAL
    addiu   v0, zero, 8             ; stock: the field in cells
.else
    addiu   v0, zero, SUMO_FIELD
.endif
.endarea

.org 0x8007D87C
.area 2*4
.if ORIGINAL
    sllv    v1, v0, s5
    addu    v1, v1, v0              ; stock: v1 = 3 * (8 - count)
.else
    nop
    nop
.endif
.endarea

.org 0x8007D88C
.area 4
.if ORIGINAL
    sll     s0, v1, 2               ; stock: s0 = 12 * (8 - count)
.else
    move    s0, v0                  ; SUMO_FIELD - width
.endif
.endarea

.org 0x8007D918
.area 4
.if ORIGINAL
    addiu   v0, zero, 8
.else
    addiu   v0, zero, SUMO_FIELD
.endif
.endarea

.org 0x8007D920
.area 2*4
.if ORIGINAL
    sll     v1, v0, 1
    addu    v1, v1, v0
.else
    nop
    nop
.endif
.endarea

.org 0x8007D930
.area 4
.if ORIGINAL
    sll     s0, v1, 2
.else
    move    s0, v0
.endif
.endarea

; ---- the exchange notebook's names: 0x8007E670 draws each at x 175 and the item after it at
; a fixed x 271; they end at that item instead (asm/musi_text.asm, vwf_name_before_sym).
.org 0x8007E6E4
.area 4
.if ORIGINAL
    jal     0x80037BA8              ; stock: sysmsg_line_draw(id, 175, y, 0, 0)
.else
    jal     vwf_name_before_sym
.endif
.endarea

.org 0x8007E8E0
.area 4
.if ORIGINAL
    jal     0x80037BA8
.else
    jal     vwf_name_before_sym
.endif
.endarea

.org 0x8007EA48
.area 4
.if ORIGINAL
    jal     0x80037BA8
.else
    jal     vwf_name_before_sym
.endif
.endarea
