; The insect box's two entry walkers, drawn in rows for English (PLAN TXT-05; Jay,
; 2026-09-24): the step, origin and break bodies that asm/hhon.asm's sites jump to. Included
; by vwf.asm in the PC-host island, resident; they run only while HHON.OVL is loaded, so
; they may jump back into it.
;
; hhon@5328's entries are drawn by hhon_entry_draw (0x8007C278, the grid's panel) and
; hhon_text_scroll_v (0x8007C1C4, the notebook page), each walking an E item down a column
; (y += 12 a glyph) with 0x8001 moving one column left (x -= 14) and back to the top. The
; origin decides once per entry, by its first glyph: English is drawn in rows -- x steps
; by each cell's width (12 for a sheet cell such as a sex mark), a break starts a row -- and
; anything else in its retail columns, so an entry the build left in Japanese is drawn
; exactly as retail draws it. research/vwf-prototype.md § "The `HHON` walkers".

HHON_GRID_LEFT  equ 218             ; the grid's cream panel, less its frame (text-boxes.tsv)
HHON_GRID_TOP   equ 16              ; Jay's option A: 11-px rows from y 16, the whole entry
HHON_GRID_PITCH equ 11
HHON_GRID_LOOP  equ 0x8007C2B4      ; hhon_entry_draw's glyph loop
HHON_GRID_COLUMN_TOP equ 0x20       ; retail: a break's new column starts here
HHON_NB_LEFT    equ 16              ; the notebook page (research/vwf-prototype.md)
HHON_NB_PITCH   equ 12
HHON_NB_LOOP    equ 0x8007C214      ; hhon_text_scroll_v's glyph loop

vwf_width_0:                        ; t9 = advance[at], 0 for a cell that is not English
    vwf_lookup_at 0                 ; (vwf_width_12's 12 cannot: English may be 12 wide)
    jr      ra
    nop

vwf_hhon_rows:                      ; 1 while the entry being drawn is English
    .byte   0
    .align  4

.macro hhon_rows_to, reg             ; reg = vwf_hhon_rows, its load delay spent
    lui     reg, hi(vwf_hhon_rows)
    lbu     reg, lo(vwf_hhon_rows)(reg)
    nop
.endmacro

; Both glyph steps: the jal takes `addiu s0,s0,2`, whose delay slot `lhu v1,0(s0)` read the
; glyph just drawn; the retail `addiu s1,s1,0xC` after it is gone (asm/hhon.asm).
vwf_hhon_step:
    hhon_rows_to t9
    bnez    t9, @@across
    move    t8, ra
    addiu   s1, s1, 12              ; retail: down a cell
    b       @@next
    nop
@@across:
    jal     vwf_width_12            ; its width, or the sheet's 12 for a cell with none
    lhu     at, 0(s0)
    addu    s2, s2, t9
@@next:
    addiu   s0, s0, 2
    jr      t8
    lhu     v1, 0(s0)               ; the next word, for the caller's test (after a nop)

; The origins: the instruction just before each loop (`ori s3/s5,zero,0x8000`) becomes a jal
; here. t9 = the first glyph's width, 0 when it is not English; the mode is kept for the
; step and the breaks.
vwf_hhon_origin:
    move    t8, ra
    jal     vwf_width_0
    lhu     at, 0(s0)
    sltu    t9, zero, t9
    lui     at, hi(vwf_hhon_rows)
    jr      t8
    sb      t9, lo(vwf_hhon_rows)(at)

; The grid: the jal's delay slot is the loop's `move a1,s2` and the return lands after it,
; so a1 is set again here.
vwf_hhon_grid_origin:
    move    t7, ra
    jal     vwf_hhon_origin
    ori     s3, zero, 0x8000        ; the retail instruction
    beqz    t9, @@japanese
    nop
    addiu   s2, zero, HHON_GRID_LEFT
    addiu   s1, zero, HHON_GRID_TOP
@@japanese:
    jr      t7
    move    a1, s2

; The notebook: y stays the retail top less the scroll.
vwf_hhon_nb_origin:
    move    t7, ra
    jal     vwf_hhon_origin
    ori     s5, zero, 0x8000        ; the retail instruction
    beqz    t9, @@japanese
    nop
    addiu   s2, zero, HHON_NB_LEFT
@@japanese:
    jr      t7
    nop

; The breaks, reached by `j` (ra is free: the walker saved its own).
vwf_hhon_grid_break:
    hhon_rows_to at
    beqz    at, @@column
    nop
    addiu   s1, s1, HHON_GRID_PITCH
    j       HHON_GRID_LOOP
    addiu   s2, zero, HHON_GRID_LEFT
@@column:
    addiu   s2, s2, -0xE
    j       HHON_GRID_LOOP
    addiu   s1, zero, HHON_GRID_COLUMN_TOP

vwf_hhon_nb_break:
    hhon_rows_to at
    beqz    at, @@column
    nop
    addiu   s1, s1, HHON_NB_PITCH
    j       HHON_NB_LOOP
    addiu   s2, zero, HHON_NB_LEFT
@@column:
    addiu   s2, s2, -0xE
    j       HHON_NB_LOOP
    subu    s1, s4, s3              ; retail: the column top (s4) less the scroll
