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
