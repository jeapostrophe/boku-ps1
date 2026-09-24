; Bug sumo's desk text in English (PLAN TXT-05, PIPE-07; research/sumo.md § The desk's text).
; Included by vwf.asm in the resident routines' block after banners.asm (whose vwf_centred_cells
; it uses), so MUSI.OVL reaches it.
;
; * The button hint and the rank board are raw arrays whose cell counts are their drawers'
;   loop bounds. `boku build` hooks each drawer's entry (boku.code_text.BANNERS) with t0 at
;   the English: {s16 centre x, s16 y} then the items, each ended by 0x8000.

PANEL_SPRITE   equ 0x800368C8       ; (ot slot, 22-byte sprite record, dx, dy)
HINT_LEFT      equ 0x8007A4CC       ; MUSI's sprite records of the hint board's two halves
HINT_RIGHT     equ 0x8007A4E4
HINT_HALF      equ 64               ; each half's width
HINT_MARGINS   equ 44               ; retail: a 128-px board round an 84-px line
HINT_SLICE_U   equ 24               ; from the left half's u: plain frame and paper ...
HINT_SLICE_MAX equ 32               ; ... this wide, repeated to widen the board
HINT_OT        equ 0x2240           ; the board's ordering-table offset, as retail adds it
RANK_PITCH     equ 16               ; the rank board's rows

; One piece of the hint board: the record at a0, at x a1, its u moved by a2 and, if a3 is
; not 0, its width a3.
sumo_board_draw:
    addiu   sp, sp, -56
    sw      ra, 48(sp)
    addiu   t1, sp, 24
    addiu   t2, zero, 22
@@copy:
    lbu     t3, 0(a0)
    addiu   a0, a0, 1
    addiu   t2, t2, -1
    sb      t3, 0(t1)
    bnez    t2, @@copy
    addiu   t1, t1, 1
    sh      a1, 26(sp)              ; x
    lbu     t3, 30(sp)              ; u
    nop
    addu    t3, t3, a2
    beqz    a3, @@keep
    sb      t3, 30(sp)
    sh      a3, 32(sp)              ; w
@@keep:
    lui     t0, 0x8002
    lw      a0, 0x593C(t0)          ; g_ot
    addiu   a1, sp, 24
    addiu   a0, a0, HINT_OT
    move    a2, zero
    jal     PANEL_SPRITE
    move    a3, zero
    lw      ra, 48(sp)
    nop
    jr      ra
    addiu   sp, sp, 56

; musi_hint_draw in English: t0 -> the centre, the y, the line. The line centred, and the
; board widened by repeating a slice of its left half until it holds the line.
vwf_sumo_hint:
    addiu   sp, sp, -40
    sw      ra, 32(sp)
    sw      s0, 28(sp)
    sw      s1, 24(sp)
    sw      s2, 20(sp)
    move    s0, t0
    jal     TEXT_SET_LIGHT
    move    a0, zero
    lh      a1, 2(s0)
    lh      a2, 0(s0)
    jal     vwf_centred_cells
    addiu   a0, s0, 4
    jal     GLYPH_FLUSH
    move    s1, v0                  ; the line's width
    addiu   s2, s1, HINT_MARGINS - 2 * HINT_HALF    ; how much wider the board must be
    bgez    s2, @@even
    nop
    move    s2, zero
@@even:
    addiu   s2, s2, 1
    srl     s2, s2, 1
    lh      t1, 0(s0)
    sll     s2, s2, 1               ; even, so the board stays centred
    srl     t2, s2, 1
    addiu   s0, t1, -HINT_HALF
    subu    s0, s0, t2              ; the board's left edge
    lui     a0, hi(HINT_LEFT)
    addiu   a0, a0, lo(HINT_LEFT)
    move    a1, s0
    move    a2, zero
    jal     sumo_board_draw
    move    a3, zero
    addiu   s0, s0, HINT_HALF
@@fill:
    blez    s2, @@right
    slti    at, s2, HINT_SLICE_MAX + 1
    bnez    at, @@slice
    move    s1, s2
    addiu   s1, zero, HINT_SLICE_MAX
@@slice:
    lui     a0, hi(HINT_LEFT)
    addiu   a0, a0, lo(HINT_LEFT)
    move    a1, s0
    addiu   a2, zero, HINT_SLICE_U
    jal     sumo_board_draw
    move    a3, s1
    addu    s0, s0, s1
    b       @@fill
    subu    s2, s2, s1
@@right:
    lui     a0, hi(HINT_RIGHT)
    addiu   a0, a0, lo(HINT_RIGHT)
    move    a1, s0
    move    a2, zero
    jal     sumo_board_draw
    move    a3, zero
    lw      ra, 32(sp)
    lw      s0, 28(sp)
    lw      s1, 24(sp)
    lw      s2, 20(sp)
    jr      ra
    addiu   sp, sp, 40

; musi_rank_draw in English: t0 -> the centre, the first row's y, three rows. Each row
; centred, RANK_PITCH apart; the board is the caller's, drawn after, as retail.
vwf_sumo_rank:
    addiu   sp, sp, -40
    sw      ra, 32(sp)
    sw      s0, 28(sp)
    sw      s1, 24(sp)
    sw      s2, 20(sp)
    sw      s3, 16(sp)
    move    s0, t0
    jal     TEXT_SET_LIGHT
    move    a0, zero
    lh      s1, 2(s0)               ; this row's y
    addiu   s2, s0, 4               ; this row's cells
    addiu   s3, s1, 3 * RANK_PITCH
@@row:
    lh      a2, 0(s0)
    move    a0, s2
    jal     vwf_centred_cells
    move    a1, s1
    move    s2, v1
    addiu   s1, s1, RANK_PITCH
    bne     s1, s3, @@row
    nop
    jal     GLYPH_FLUSH
    nop
    lw      ra, 32(sp)
    lw      s0, 28(sp)
    lw      s1, 24(sp)
    lw      s2, 20(sp)
    lw      s3, 16(sp)
    jr      ra
    addiu   sp, sp, 40

; ---- the exchange notebook's names ---------------------------------------------------------
; MUSI's exchange notebook (0x8007E670) draws an insect's name at x 175 and the item after it
; at a fixed x 271; at its three name sites (musi.asm) vwf_name_before_sym draws the name to
; end there instead, measured first as MUSI measures its right-aligned names (0x8007D850: at
; OFFSCREEN_X, OFFSCREEN_Y, and a fifth argument of 1, which skips the glyph flush). All
; three pass a3 = 0 and a fifth argument of 0. A 96-px Japanese name lands where retail drew it.
;
; A name too wide to clear the size badge has a notebook-only version: a list the build writes
; and hands vwf_exchange_entry in t0 (boku.exchange_notebook). A type the list has no item for,
; or an empty one, draws its full name.
SYSNAME_DRAW   equ 0x80037BA8       ; sysmsg_line_draw(type, x, y, a3, [16]) -> v0 = its width
SYSMSG_DRAW    equ 0x800379EC       ; sysmsg_draw(list, item, x, y, [16] down) -> v0 = its width
OFFSCREEN_X    equ 0x258            ; where MUSI draws a name to measure it
OFFSCREEN_Y    equ 0x12C
NOTEBOOK_SYM_X equ 0x10F            ; the exchange notebook's item after a name
NOTEBOOK_ENTRY equ 0x8007E670       ; the notebook's page, hooked by the build
FIGHTERS_A     equ 23               ; the sumo types: 23..30, the eight beetles ...
FIGHTERS_A_N   equ 8
FIGHTERS_B     equ 56               ; ... then 56..60, the females and the mantis
FIGHTERS_B_N   equ 5

vwf_exchange_entry:                 ; t0 = the list; then the three instructions the hook took
    lui     at, hi(vwf_exchange_names)
    sw      t0, lo(vwf_exchange_names)(at)
    addiu   sp, sp, -0x30
    move    a0, zero
    j       NOTEBOOK_ENTRY + 12
    sw      ra, 0x28(sp)

vwf_exchange_names:                 ; the list, once the hooked notebook has run; 0 before
    .word   0

vwf_name_before_sym:                ; (type, -, y)
    addiu   sp, sp, -40
    sw      ra, 36(sp)
    sw      s0, 32(sp)
    sw      s1, 28(sp)
    sw      s2, 24(sp)
    sw      s3, 20(sp)
    move    s0, a0
    move    s1, a2
    lui     at, hi(vwf_exchange_names)
    lw      s2, lo(vwf_exchange_names)(at)
    sw      zero, 16(sp)            ; down = 0
    beqz    s2, @@full
    addiu   s3, s0, -FIGHTERS_A     ; s3 = the type's item in the list
    sltiu   at, s3, FIGHTERS_A_N
    bnez    at, @@listed
    nop
    addiu   s3, s0, -FIGHTERS_B
    sltiu   at, s3, FIGHTERS_B_N
    beqz    at, @@full
    addiu   s3, s3, FIGHTERS_A_N    ; unused on the way to @@full
@@listed:
    move    a0, s2
    move    a1, s3
    addiu   a2, zero, OFFSCREEN_X
    jal     SYSMSG_DRAW             ; measured: v0 = the width, 0 for an empty item
    addiu   a3, zero, OFFSCREEN_Y
    beqz    v0, @@full
    addiu   a2, zero, NOTEBOOK_SYM_X
    subu    a2, a2, v0
    move    a0, s2
    move    a1, s3
    sw      zero, 16(sp)
    jal     SYSMSG_DRAW
    move    a3, s1
    jal     GLYPH_FLUSH
    nop
    b       @@done
    nop
@@full:
    addiu   t0, zero, 1
    sw      t0, 16(sp)
    move    a0, s0
    move    a3, zero
    addiu   a2, zero, OFFSCREEN_Y
    jal     SYSNAME_DRAW            ; measured: v0 = the width
    addiu   a1, zero, OFFSCREEN_X
    addiu   a1, zero, NOTEBOOK_SYM_X
    subu    a1, a1, v0
    move    a0, s0
    move    a2, s1
    move    a3, zero
    jal     SYSNAME_DRAW
    sw      zero, 16(sp)
@@done:
    lw      ra, 36(sp)
    lw      s0, 32(sp)
    lw      s1, 28(sp)
    lw      s2, 24(sp)
    lw      s3, 20(sp)
    jr      ra
    addiu   sp, sp, 40
