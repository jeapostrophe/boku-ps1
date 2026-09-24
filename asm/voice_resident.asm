; Voice-subtitle routines kept in vwf.asm's PC-host island because voice.asm's own islands
; are full (PLAN VO-06); voice.asm's header is the design.

; The block from its sectors to a0, as movie_sub_load reads it (asm/movie.asm): up to 8
; tries, and when every one fails no block rather than part of one.
clip_sub_read:
    addiu   sp, sp, -40
    sw      ra, 32(sp)
    sw      s0, 28(sp)
    sw      s1, 24(sp)
    move    s1, a0
    addiu   s0, zero, 8
@@read:
    beqz    s0, @@give_up
    addiu   s0, s0, -1
    addiu   a0, zero, MOVIE_SUB_LBA
    lui     a1, hi(clip_sub_loc)
    jal     CD_INT_TO_POS
    addiu   a1, a1, lo(clip_sub_loc)
    lui     a0, hi(clip_sub_loc)
    addiu   a0, a0, lo(clip_sub_loc)
    addiu   a1, zero, MOVIE_SUB_SECTORS
    move    a2, s1
    jal     CD_READ
    addiu   a3, zero, 0x80
    beqz    v0, @@read
    nop
@@sync:
    jal     CD_READ_SYNC
    addiu   a0, sp, 16              ; its 8-byte result buffer
    beqz    v0, @@out
    addiu   at, zero, -1
    beq     v0, at, @@read
    nop
    b       @@sync
    nop
@@give_up:
    sw      zero, 0(s1)
@@out:
    lw      ra, 32(sp)
    lw      s0, 28(sp)
    lw      s1, 24(sp)
    jr      ra
    addiu   sp, sp, 40

; g_modes[7]'s init, in place of its call to MUSI's init: that call, then the movie-subtitle
; block from the disc to level C's base, where clip_sub_block looks for it in bug sumo. The
; drive is idle here: MUSI's init has made its own loads.
sumo_sub_init:
    addiu   sp, sp, -24
    sw      ra, 16(sp)
    jal     MUSI_INIT               ; the call this replaces
    nop
    lw      ra, 16(sp)
    lui     a0, hi(LEVEL_C_BASE)
    lw      a0, lo(LEVEL_C_BASE)(a0)
    j       clip_sub_read           ; which returns to g_modes[7]'s init
    addiu   sp, sp, 24
