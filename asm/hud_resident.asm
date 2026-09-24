; The fish-catch title (fish_name_draw 0x8003C5EC): the name centred in its panel, the box of
; research/data/text-boxes.tsv's exe@8003DA4C row, whose middle the build passes as
; FISH_TITLE_MIDDLE. Included by vwf.asm in the PC-host island. No stack frame: fishing runs
; on the field's scratchpad stack (research/vwf-prototype.md), so ra waits in t8.

; At 0x8003C68C, in place of `sll s2,v0,0x10`: v0 is the y, s0 is past the name's first word;
; the jal's delay slot (the loop's `sll a1,s1,0x10`) has already run, so a1 is set again
; here. a0, the first glyph, is untouched: vwf_width_12 writes only at and t9.
vwf_fish_title_x:
    move    t8, ra
    sll     s2, v0, 16              ; the instruction the jal replaced
    addiu   t0, s0, -2              ; the name
    move    t1, zero                ; its width
@@next:
    lhu     at, 0(t0)
    nop
    andi    t2, at, 0x8000
    bnez    t2, @@measured
    nop
    jal     vwf_width_12            ; t9 = its advance, 12 for a cell that is not English
    nop
    addu    t1, t1, t9
    b       @@next
    addiu   t0, t0, 2
@@measured:
    srl     t1, t1, 1
    addiu   s1, zero, FISH_TITLE_MIDDLE
    subu    s1, s1, t1
    jr      t8
    sll     a1, s1, 16
