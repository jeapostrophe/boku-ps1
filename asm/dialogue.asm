; The dialogue surface of SCPS_100.88, horizontal and proportional (PLAN TXT-05, prototype).
; Included by vwf.asm, which owns the file, the equates and the free space.
;
; Surface: msg_open -> dialog_open -> dialog_draw -> glyph_draw, and the ant-count message,
; which is the only other caller of dialog_open. Nothing else in the game goes through
; dialog_draw (research/text-renderer.md § 3), so nothing else changes.

; ---- msg_open: the three literal arguments of dialog_open(x, y, vertical, text) -----------
; a2 becomes bit 0x10 of g_text_flags. After this patch the flag still picks the newline
; rule in dialog_draw (0x8002BF1C) but no longer picks the advance, so a caller passing 1
; would draw garbage; the two callers patched here are the only ones in any image.
.org 0x8002CFC4
.area 3*4
.if ORIGINAL
    addiu   a0, zero, 0x129         ; stock: x = 297, the rightmost vertical column
    addiu   a1, zero, 0x16          ; stock: y = 22
    addiu   a2, zero, 1             ; stock: vertical
.else
    addiu   a0, zero, PEN_X
    addiu   a1, zero, PEN_Y
    addiu   a2, zero, 0             ; horizontal
.endif
.endarea

; ---- the ant-count message: the same three literals, with one live instruction between ----
.org 0x8003206C
.area 4*4
.if ORIGINAL
    addiu   a0, zero, 0x129
    addiu   v0, v0, 0x34            ; digit -> glyph id (52 + n); not ours, restated to keep one area
    addiu   a1, zero, 0x16
    addiu   a2, zero, 1
.else
    addiu   a0, zero, PEN_X
    addiu   v0, v0, 0x34
    addiu   a1, zero, PEN_Y
    addiu   a2, zero, 0
.endif
.endarea

; ---- g_dlgbox_x (s16 data, never written by the game) -------------------------------------
; dialog_panel_draw makes the tile (0x145 - g_dlgbox_x) wide and draws a 5-px gouraud fade
; ending at g_dlgbox_x + 5. At -5 the tile is 330 wide (clipped to the screen) and the fade
; lies wholly off-screen to the left.
.org 0x8002911C
.area 2
.if ORIGINAL
    .dh     260                     ; stock: the strip starts at x = 265
.else
    .dh     -5
.endif
.endarea

; ---- dialog_panel_draw: the right-hand strip becomes a band ("band2") ---------------------
; s0 -> the TILE: x at +8, y at +0xA, w at +0xC, h at +0xE; v1 = g_dlgbox_x. The stock code
; stores y = 0 and x = v1 + 5. Swapping the two store offsets frees the second immediate, so
; top and height are independent in the same six slots.
.org 0x8002EA34
.area 6*4
.if ORIGINAL
    addiu   s1, zero, 0xF0          ; stock: h = 240, the full-height strip
    sh      zero, 0xA(s0)           ; stock: y = 0
    sh      s1, 0xE(s0)
    addiu   a0, a0, 8
    addiu   v0, v1, 5               ; stock: x = g_dlgbox_x + 5
    sh      v0, 8(s0)
.else
    addiu   s1, zero, BAND_H
    sh      zero, 8(s0)             ; x = 0
    sh      s1, 0xE(s0)             ; (unchanged) h = s1
    addiu   a0, a0, 8               ; (unchanged)
    addiu   v0, zero, BAND_Y
    sh      v0, 0xA(s0)             ; y = BAND_Y
.endif
.endarea

; ---- dialog_draw, newline in horizontal mode: x = origin.x (0x8002BF40), then this --------
.org 0x8002BF48
.area 4
.if ORIGINAL
    addiu   s1, s1, 0xD             ; stock: 13 rows per line
.else
    addiu   s1, s1, LINE_PITCH
.endif
.endarea

; ---- dialog_draw: the advance after each glyph --------------------------------------------
; Reached straight after `jal glyph_draw`. s0 -> the word just drawn, s1 = pen y, s2 = pen x;
; glyph_draw preserves s0-s7; v0 v1 at are dead here. Falls into 0x8002BF80 `addiu s0,s0,2`,
; which the control-word paths also jump to, so the nine slots are the whole budget.
.org 0x8002BF5C
.area 9*4
.if ORIGINAL
    lui     v0, 0x8003
    lw      v0, 0x59E4(v0)          ; stock: g_text_flags
    nop
    andi    v0, v0, 0x10            ; stock: vertical?
    beqz    v0, @@horizontal
    nop
    j       0x8002BF80
    addiu   s1, s1, 0xD             ; stock, vertical: y += 13
@@horizontal:
    addiu   s2, s2, 0xE             ; stock, horizontal: x += 14
.else
    ; The R3000 has a load delay slot: the instruction after a load still sees the old
    ; register. So the table byte is fetched unconditionally and the range test sits in its
    ; delay slot. The fetch is harmless for any id: a glyph word is < 0x8000, and
    ; vwf_advance + 0x7FFF is still inside main RAM.
    lhu     v0, 0(s0)               ; glyph id
    lui     v1, hi(vwf_advance)     ; (load delay of v0)
    addu    v1, v1, v0
    lbu     v1, lo(vwf_advance)(v1)
    sltiu   at, v0, TABLE_IDS       ; (load delay of v1)
    bnez    at, @@advance
    nop
    addiu   v1, zero, FIXED_ADVANCE ; ids past the table keep the stock pitch
@@advance:
    addu    s2, s2, v1
.endif
.endarea
