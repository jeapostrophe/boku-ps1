; The fortune (exe@80036750, fortune_draw 0x8003A7A4) and the kite crash banner (tako@440,
; tako_crash_draw TAKO 0x8007C684), which the retail game stacks a glyph per row in a tall
; panel, drawn as one centred line (PLAN TXT-05). Included by vwf.asm inside the PC-host
; island after labels.asm, so TAKO reaches it too. Nothing here is a site: `boku build`
; hooks the drawer's entry as it hooks the date labels (boku.code_text.drawer_hook) and
; widens the panel (boku.code_text.BANNERS), only when the array is translated. The text is
; the line's centre x and y, then the items: cells, each ended by 0x8000.

TEXT_NTH       equ 0x800438F0       ; text_nth(base, n): the item after n 0x8000 words
FORTUNE_DRAWS  equ 0x8003E052       ; three bytes, each 1 or 2; the result counts the 2s
FORTUNE_LUCK   equ 0x8003DD1D       ; where fortune_draw leaves that count

; Draw the cells at a0 centred on x a2 at y a1, then glyph_flush.
vwf_banner_line:
    addiu   sp, sp, -32
    sw      ra, 24(sp)
    sw      s0, 20(sp)
    sw      s1, 16(sp)
    sw      s2, 28(sp)
    move    s0, a0
    move    s1, a1
    move    s2, a2
    move    a1, zero
    move    a2, zero
    jal     vwf_label_cells         ; measured only: v0 = the width
    addiu   a3, zero, 1
    srl     v0, v0, 1
    subu    a1, s2, v0
    move    a0, s0
    move    a2, s1
    jal     vwf_label_cells
    move    a3, zero
    jal     GLYPH_FLUSH
    nop
    lw      ra, 24(sp)
    lw      s0, 20(sp)
    lw      s1, 16(sp)
    lw      s2, 28(sp)
    jr      ra
    addiu   sp, sp, 32

; fortune_draw in English: t0 -> x, y, the four results. The result is how many of the three
; draws came up 2, left where the retail drawer leaves it.
vwf_fortune_banner:
    lui     t1, hi(FORTUNE_DRAWS)
    addiu   t1, t1, lo(FORTUNE_DRAWS)
    move    a1, zero
    addiu   t2, t1, 3
@@count:
    lbu     t3, 0(t1)
    addiu   t1, t1, 1
    xori    t3, t3, 2
    sltiu   t3, t3, 1               ; 1 when the draw was a 2
    bne     t1, t2, @@count
    addu    a1, a1, t3
    lui     at, hi(FORTUNE_LUCK)
    sb      a1, lo(FORTUNE_LUCK)(at)
    addiu   sp, sp, -24
    sw      ra, 16(sp)
    sw      s0, 20(sp)
    move    s0, t0
    jal     TEXT_NTH
    addiu   a0, t0, 4
    move    a0, v0
    lh      a1, 2(s0)               ; y
    lh      a2, 0(s0)               ; x
    jal     vwf_banner_line
    nop
    lw      ra, 16(sp)
    lw      s0, 20(sp)
    jr      ra
    addiu   sp, sp, 24

; tako_crash_draw in English: t0 -> x, y, the one item.
vwf_crash_banner:
    lh      a2, 0(t0)
    lh      a1, 2(t0)
    j       vwf_banner_line
    addiu   a0, t0, 4
