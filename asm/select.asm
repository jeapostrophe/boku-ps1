; SELECT menus of SCPS_100.88 as horizontal rows (PLAN TXT-05, prototype). Included by
; vwf.asm, which owns the file, the equates and the hook routines vwf_select_advance and
; vwf_select_box.
;
; Surface: select_draw (0x8002C234), select_cursor_update (0x8002C330) and select_box_draw
; (0x8002C150), run every frame by the event SELECT op (0x8002D0xx) and by select_run_ptr
; (0x8002D10C) for the eight native menus (research/text-renderer.md § 3 row 2, § 4c). The
; stock layout is columns right to left: g_select_pos holds each line's column top, the
; glyph loop steps y by 12, and the cursor sprite sits above its column.
;
; Here every layout is the same list of rows at (SEL_X, SEL_Y + i * SEL_PITCH): the loop
; steps x by the width table, the cursor sits SEL_CURSOR_DX/DY from its row's origin, the
; pad moves it up and down, and the box is measured from the text every frame (the hooks
; in vwf.asm) with the table's x and y as its top-left corner.

; ---- select_draw: the step after each glyph --------------------------------------------
; The loop is `jal glyph_draw` / `move a2,s0` / this / `lhu a0,0(s1)` / `nop` / `andi` /
; `beqz`. The jal's delay slot is the stock `lhu a0,0(s1)`, so the hook returns to the nop
; with a0 already reloaded; s1 is past the word drawn, and ra is dead in the loop (the
; function saved its own and `jal glyph_draw` clobbers it every glyph).
.org 0x8002C2D0
.area 4
.if ORIGINAL
    addiu   s0, s0, 0xC             ; stock: y += 12, down the column
.else
    jal     vwf_select_advance      ; x += vwf_advance[id]; records xmax and the row's y
.endif
.endarea

; ---- select_box_draw: the tile's w and h ---------------------------------------------------
; s1 -> g_select_rect[type - 1] {x, y, w, h}; s0 -> the TILE (w at +0xC, h at +0xE). The
; hook returns v0 = w and v1 = h, and the two stores that follow are the stock ones.
.org 0x8002C1D0
.area 4*4
.if ORIGINAL
    lhu     v0, 4(s1)               ; stock: w from the table
    move    a0, s2
    sh      v0, 0xC(s0)
    lhu     v0, 6(s1)               ; stock: h from the table
.else
    jal     vwf_select_box
    move    a0, s2                  ; (unchanged, delay slot)
    sh      v0, 0xC(s0)             ; (unchanged) w
    move    v0, v1                  ; h, stored by the unchanged `sh v0,0xE(s0)` at 0x8002C1E8
.endif
.endarea

; ---- select_cursor_update: which hand, and where ------------------------------------------
; a1 = the line's x, a2 = its y from g_select_pos; the hand drawer (0x80042B64) is between
; the two immediates and is restated unchanged. It draws ONMEM.BIN sprite 0, the game's own
; right-pointing hand (the title menu's), when a3 is non-zero, and sprite 1, pointing down,
; when it is 0. Sprite 1 is the hand every Back button is pointed at, so the rows choose
; sprite 0 here rather than the build turning the shared one.
.org 0x8002C3D0
.area 4*4
.if ORIGINAL
    move    a3, zero                ; stock: sprite 1, pointing down
    addiu   a1, a1, -2              ; stock: 2 px left of the column
    jal     0x80042B64
    addiu   a2, a2, -0x18           ; stock: 24 px above it
.else
    addiu   a3, zero, SEL_CURSOR_SIDE
    addiu   a1, a1, SEL_CURSOR_DX
    jal     0x80042B64
    addiu   a2, a2, SEL_CURSOR_DY
.endif
.endarea

; ---- select_cursor_update: the pad --------------------------------------------------------
; Stock: with fewer than 4 options, left = +1 and right = -1 (the columns run right to
; left); with 4 or more, left/right = +-2 and up/down = -+1 (two rows of columns). Rows
; have one rule: down = +1, up = -1. The first word makes the "fewer than 4" test always
; true so the two-column block never runs; the two masks re-key its branches.
.org 0x8002C3E0
.area 4
.if ORIGINAL
    slti    v0, s1, 4               ; stock: s1 = option count
.else
    addiu   v0, zero, 1             ; every layout is one column of rows
.endif
.endarea

.org 0x8002C3F4
.area 4
.if ORIGINAL
    andi    v0, v1, 0x8000          ; stock: LEFT -> cursor + 1
.else
    andi    v0, v1, 0x4000          ; DOWN -> cursor + 1
.endif
.endarea

.org 0x8002C3FC
.area 4
.if ORIGINAL
    andi    v0, v1, 0x2000          ; stock: RIGHT -> cursor - 1
.else
    andi    v0, v1, 0x1000          ; UP -> cursor - 1
.endif
.endarea

; ---- g_select_pos: 12 layouts x 5 lines of {s16 x, s16 y} -------------------------------
; Stock values are column tops (research/text-renderer.md § 1 "SELECT geometry"). Patched,
; every layout is the same five row origins; a layout with n lines reads the first n.
.macro select_rows
    .dh     SEL_X, SEL_Y + 0 * SEL_PITCH
    .dh     SEL_X, SEL_Y + 1 * SEL_PITCH
    .dh     SEL_X, SEL_Y + 2 * SEL_PITCH
    .dh     SEL_X, SEL_Y + 3 * SEL_PITCH
    .dh     SEL_X, SEL_Y + 4 * SEL_PITCH
.endmacro

.org 0x80028E7C
.area 12*5*4
.if ORIGINAL
    .dh     166, 80,  142, 80,  0, 0,  0, 0,  0, 0           ; layout 0: type 1
    .dh     166, 64,  142, 64,  0, 0,  0, 0,  0, 0           ; layout 1: type 2 variant 1
    .dh     166, 64,  166, 124, 142, 64, 142, 124, 0, 0      ; layout 2: type 2 variant 2
    .dh     178, 68,  154, 68,  130, 68, 0, 0,  0, 0         ; layout 3: type 3 variant 1
    .dh     178, 68,  178, 128, 154, 68, 154, 128, 130, 68   ; layout 4: type 3 variant 2
    .dh     180, 60,  152, 84,  128, 84, 0, 0,  0, 0         ; layout 5: type 3 variant 3
    .dh     178, 56,  154, 56,  130, 56, 0, 0,  0, 0         ; layout 6: type 4 variant 1
    .dh     178, 40,  154, 40,  130, 40, 0, 0,  0, 0         ; layout 7: type 4 variant 2
    .dh     180, 52,  152, 76,  128, 76, 0, 0,  0, 0         ; layout 8: type 4 variant 3
    .dh     180, 48,  152, 72,  128, 72, 0, 0,  0, 0         ; layout 9: type 4 variant 4
    .dh     262, 144, 238, 144, 0, 0,  0, 0,  0, 0           ; layout 10: type 5
    .dh     276, 74,  248, 86,  224, 86, 0, 0,  0, 0         ; layout 11: type 6
.else
    select_rows
    select_rows
    select_rows
    select_rows
    select_rows
    select_rows
    select_rows
    select_rows
    select_rows
    select_rows
    select_rows
    select_rows
.endif
.endarea

; ---- g_select_rect: {x, y, w, h} by type - 1 -----------------------------------------------
; Types 1-6 get the same corner: SEL_PAD left of the cursor (SEL_CURSOR_DX is at most 0,
; which the build checks) and SEL_PAD above the first row. Every select draws its box
; after select_draw measured it, so w and h come from vwf_select_box (xmax + pad, and the
; last row's y + cell + pad); the w and h here are only what it returns when nothing was
; measured. They are still derived from the row geometry rather than typed: the tallest
; layout has five rows, so the fallback box is that tall, and the width is the widest
; option this build allows. Entry 6 (type 7, the controls-help screen, which draws the
; box without select_draw) lies past this area and is untouched.
SEL_BOX_W equ (320 - PEN_X - SEL_X + 2 * SEL_PAD - SEL_CURSOR_DX)   ; select_width + both pads + the cursor
SEL_BOX_H equ (4 * SEL_PITCH + CELL + 2 * SEL_PAD)
.org 0x80028E44
.area 6*8
.if ORIGINAL
    .dh     120, 56,  80,  96
    .dh     120, 40,  80,  144
    .dh     104, 40,  112, 152
    .dh     104, 24,  112, 192
    .dh     216, 120, 80,  96
    .dh     208, 56,  96,  168
.else
    .dh     SEL_X + SEL_CURSOR_DX - SEL_PAD, SEL_Y - SEL_PAD, SEL_BOX_W, SEL_BOX_H
    .dh     SEL_X + SEL_CURSOR_DX - SEL_PAD, SEL_Y - SEL_PAD, SEL_BOX_W, SEL_BOX_H
    .dh     SEL_X + SEL_CURSOR_DX - SEL_PAD, SEL_Y - SEL_PAD, SEL_BOX_W, SEL_BOX_H
    .dh     SEL_X + SEL_CURSOR_DX - SEL_PAD, SEL_Y - SEL_PAD, SEL_BOX_W, SEL_BOX_H
    .dh     SEL_X + SEL_CURSOR_DX - SEL_PAD, SEL_Y - SEL_PAD, SEL_BOX_W, SEL_BOX_H
    .dh     SEL_X + SEL_CURSOR_DX - SEL_PAD, SEL_Y - SEL_PAD, SEL_BOX_W, SEL_BOX_H
.endif
.endarea
