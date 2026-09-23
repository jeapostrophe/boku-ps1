; The two date labels drawn from code (PLAN PIPE-07), rebuilt around the English. Included by
; vwf.asm inside the PC-host island, so everything here is resident and nothing here is a
; site: `boku build` installs the hook -- three words at the drawer's entry,
;   lui t0, hi(text) / j <routine> / addiu t0, t0, lo(text)
; -- only when the label is translated, with the English text placed where it chose
; (boku/code_text.py, boku/array_relocate.py). An untranslated label runs the retail drawer.
;
; The text is cells ended by 0x8000, one segment per stretch of label between the numbers
; the code computes: caught_label "Date caught {month}/{day}" is three segments, save_date
; "August {day}" two. Each segment is stepped through the advance table and each number is
; placed after the measured width -- the retail drawers put them at fixed offsets sized for
; two kanji. Glyphs first, then glyph_flush, then the number sprites, in the retail order.
; Arguments are sign-extended from 16 bits, as the retail drawers do.

GLYPH_DRAW     equ 0x8002BA2C       ; glyph_draw(id, x, y)
GLYPH_FLUSH    equ 0x8002B95C       ; what both retail drawers call after their last glyph
NUMBER_DRAW    equ 0x800400F8       ; number_draw(value, x, y, 0, [16] a3, [20] colour)
LABEL_PITCH    equ 12               ; a cell that is not English steps this (code_text.py)
SPRITE_DIGIT   equ 7                ; number_draw's step per digit (0x80040224)
MONTH_GAP      equ 2                ; retail: the month sprite, then 9 px to the next glyph
CAUGHT_RIGHT   equ 77               ; retail right edge of caught_label_draw's label, from x
GLYPH_DIGIT    equ 0x34             ; glyph id of the full-width 0
DIGIT_STEP     equ 10               ; save_date_draw's step between the day's two glyphs
DIGIT_END      equ 12               ; and from the last one to what follows

; v0 = the pen after the cells at a0 from (a1, a2), drawn when a3 = 0 and only measured
; otherwise; v1 -> the next segment.
vwf_label_cells:
    addiu   sp, sp, -40
    sw      ra, 32(sp)
    sw      s0, 28(sp)
    sw      s1, 24(sp)
    sw      s2, 20(sp)
    sw      s3, 16(sp)
    move    s0, a0
    move    s1, a1
    move    s2, a2
    move    s3, a3
@@next:
    lhu     a0, 0(s0)
    nop
    andi    at, a0, 0x8000
    bnez    at, @@done
    move    a1, s1
    bnez    s3, @@measured
    nop
    jal     GLYPH_DRAW
    move    a2, s2
@@measured:
    lhu     at, 0(s0)               ; glyph_draw clobbered a0
    vwf_lookup_at LABEL_PITCH
    addu    s1, s1, t9
    b       @@next
    addiu   s0, s0, 2
@@done:
    move    v0, s1
    addiu   v1, s0, 2
    lw      ra, 32(sp)
    lw      s0, 28(sp)
    lw      s1, 24(sp)
    lw      s2, 20(sp)
    lw      s3, 16(sp)
    jr      ra
    addiu   sp, sp, 40

; save_date_draw (TITLE 0x8007BB60) in English: (a0 x, a1 y, a2 day), t0 -> 2 segments.
vwf_save_date_label:
    addiu   sp, sp, -40
    sw      ra, 32(sp)
    sw      s0, 28(sp)
    sw      s1, 24(sp)
    sw      s2, 20(sp)
    sw      s3, 16(sp)
    sll     a0, a0, 16
    sra     a0, a0, 16
    sll     a1, a1, 16
    sra     s1, a1, 16              ; y
    sll     a2, a2, 16
    sra     s2, a2, 16              ; day
    move    a1, a0
    move    a2, s1
    move    a3, zero
    jal     vwf_label_cells
    move    a0, t0
    move    s3, v0                  ; pen
    move    s0, v1                  ; the suffix
    addiu   at, zero, 10
    divu    s2, at
    mflo    a0                      ; tens
    mfhi    s2                      ; ones; the day itself is not needed again
    beqz    a0, @@ones
    move    a1, s3
    addiu   a0, a0, GLYPH_DIGIT
    jal     GLYPH_DRAW
    move    a2, s1
    addiu   s3, s3, DIGIT_STEP
@@ones:
    addiu   a0, s2, GLYPH_DIGIT
    move    a1, s3
    jal     GLYPH_DRAW
    move    a2, s1
    addiu   a1, s3, DIGIT_END
    move    a0, s0
    move    a2, s1
    jal     vwf_label_cells
    move    a3, zero
    jal     GLYPH_FLUSH
    nop
    lw      ra, 32(sp)
    lw      s0, 28(sp)
    lw      s1, 24(sp)
    lw      s2, 20(sp)
    lw      s3, 16(sp)
    jr      ra
    addiu   sp, sp, 40

; caught_label_draw (0x80037544) in English: (a0 x, a1 y, a2 day, a3 and [16] number_draw's
; own), t0 -> 3 segments. Right-aligned where the retail label ends (x + CAUGHT_RIGHT): its
; callers put it against the screen's right edge. The frame is the retail one's 0x40, so the
; caller's fifth argument is at 0x50(sp) as the retail drawer read it.
vwf_caught_label:
    addiu   sp, sp, -0x40
    sw      ra, 0x3C(sp)
    sw      s0, 0x38(sp)
    sw      s1, 0x34(sp)
    sw      s2, 0x30(sp)
    sw      s3, 0x2C(sp)
    sw      s4, 0x28(sp)
    sw      s5, 0x24(sp)
    sw      s6, 0x20(sp)
    sw      s7, 0x1C(sp)
    sll     a0, a0, 16
    sra     s1, a0, 16              ; x
    sll     a1, a1, 16
    sra     s2, a1, 16              ; y
    sll     a2, a2, 16
    sra     s3, a2, 16              ; day
    move    s4, a3                  ; number_draw's fourth-slot argument, from the caller
    lbu     s5, 0x50(sp)            ; the colour byte
    move    s0, t0                  ; the segments
    ; measure: prefix, month, middle, day, suffix
    move    a0, t0
    move    a1, zero
    jal     vwf_label_cells
    addiu   a3, zero, 1
    addiu   a1, v0, SPRITE_DIGIT + MONTH_GAP
    move    a0, v1
    jal     vwf_label_cells
    addiu   a3, zero, 1
    addiu   a1, v0, SPRITE_DIGIT
    slti    at, s3, 10
    bnez    at, @@short
    move    a0, v1
    addiu   a1, a1, SPRITE_DIGIT
@@short:
    jal     vwf_label_cells
    addiu   a3, zero, 1
    subu    s1, s1, v0
    addiu   s1, s1, CAUGHT_RIGHT    ; the left edge that puts the right edge where it was
    ; draw
    move    a0, s0
    move    a1, s1
    move    a2, s2
    jal     vwf_label_cells
    move    a3, zero
    move    s6, v0                  ; the month's x
    addiu   a1, v0, SPRITE_DIGIT + MONTH_GAP
    move    a0, v1
    move    a2, s2
    jal     vwf_label_cells
    move    a3, zero
    move    s7, v0                  ; the day's x
    slti    at, s3, 10
    addiu   a1, v0, SPRITE_DIGIT
    bnez    at, @@short2
    move    a0, v1
    addiu   a1, a1, SPRITE_DIGIT
@@short2:
    move    a2, s2
    jal     vwf_label_cells
    move    a3, zero
    jal     GLYPH_FLUSH
    nop
    addiu   s0, s2, 1               ; the sprites sit a row lower, as the retail drawer puts them
    sw      s4, 0x10(sp)
    sw      s5, 0x14(sp)
    addiu   a0, zero, 8             ; August
    andi    a1, s6, 0xFFFF
    andi    a2, s0, 0xFFFF
    jal     NUMBER_DRAW
    move    a3, zero
    sw      s4, 0x10(sp)
    sw      s5, 0x14(sp)
    move    a0, s3
    andi    a1, s7, 0xFFFF
    andi    a2, s0, 0xFFFF
    jal     NUMBER_DRAW
    move    a3, zero
    lw      ra, 0x3C(sp)
    lw      s0, 0x38(sp)
    lw      s1, 0x34(sp)
    lw      s2, 0x30(sp)
    lw      s3, 0x2C(sp)
    lw      s4, 0x28(sp)
    lw      s5, 0x24(sp)
    lw      s6, 0x20(sp)
    lw      s7, 0x1C(sp)
    jr      ra
    addiu   sp, sp, 0x40
