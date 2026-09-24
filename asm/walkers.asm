; The fixed-pitch text walkers, routed through the advance table (PLAN TXT-05). Included by
; vwf.asm inside the executable's `.open`; it holds the executable's own walker sites and the
; island every walker's step body lives in, the overlays' included.
;
; Each walker steps its pen by a literal after `jal glyph_draw`. The step becomes a jal to a
; body that adds vwf_advance[id] instead -- or the surface's stock pitch for a cell that is
; not English, so untranslated text is spaced as the retail game spaces it. Bodies write
; only at, t8 and t9 besides what they are named for, so whatever a delay slot loaded
; survives.
; Sites, registers and why each hook sits where it does: research/vwf-prototype.md
; § "The fixed-pitch surfaces"; the walkers are run instruction by instruction in
; tests/test_real_walkers.py.

; ---- surface 5: the controls-help screen (START in free roam), g_help_text 0x80029B20 ------
; text_draw_right 0x80035360 is not right-aligned: a count pass moves s2 to the line's end,
; then the draw pass walks back glyph by glyph, so glyph 0 lands at x. Both passes must take
; the same widths.
.org 0x8003539C
.area 4
.if ORIGINAL
    addiu   s1, s1, 1               ; stock: count; delay slot `lh v0,0(s0)` loads the next word
.else
    jal     vwf_count_s2_s0
.endif
.endarea

.org 0x800353B0
.area 4
.if ORIGINAL
    addiu   s2, s2, 0xC             ; stock: x += 12, in the delay slot of `beqz v0`
.else
    nop                             ; vwf_count_s2_s0 adds the width
.endif
.endarea

.org 0x800353C0
.area 4
.if ORIGINAL
    addiu   s2, s2, -0xC            ; stock: x -= 12; delay slot `lh a0,0(s0)` is the id drawn
.else
    jal     vwf_back_s2_s0
.endif
.endarea

; help_line_draw 0x80035448: the one help line at a 10-px pitch (pad type 2). The pointer
; step is the delay slot, so the id just drawn is at -2(s0) in the body.
.org 0x80035490
.area 4
.if ORIGINAL
    addiu   s1, s1, 0xA             ; stock: x += 10
.else
    jal     vwf_step_s1_s0_p10
.endif
.endarea

; The help screen's pens, moved so the English fits its row (the reasons are the rows of
; research/data/text-boxes.tsv). g_help_pos 0x80029904 is an (x, y) byte pair per line
; 0-12; the button labels' x are help_draw's `addiu a1,zero,x`.
.macro help_pen, line, stock, moved
    .org 0x80029904 + 2 * line
    .area 1
    .if ORIGINAL
        .byte stock
    .else
        .byte moved
    .endif
    .endarea
.endmacro
help_pen 0, 64, 52
help_pen 2, 52, 48
help_pen 5, 184, 180
help_pen 6, 184, 180
help_pen 8, 172, 132

.org 0x8003572C
.area 4
.if ORIGINAL
    addiu   a1, zero, 0x88          ; stock: labels 15/18 at x 136, row 128
.else
    addiu   a1, zero, 96
.endif
.endarea

.org 0x80035750
.area 4
.if ORIGINAL
    addiu   a1, zero, 0x94          ; stock: label 21 (pad type 2) at x 148, row 128
.else
    addiu   a1, zero, 108
.endif
.endarea

; help_screen_draw's loop has drawn lines 0-12; the jal draws the bottom sentence's extra row
; (asm/help_resident.asm) and does the two instructions it takes the place of.
.org 0x800356D0
.area 2*4
.if ORIGINAL
    lui     v0, 0x8002              ; stock: the pad type's page,
    lbu     s1, 0x5917(v0)          ; read after the loop
.else
    jal     vwf_help_extra_row
    nop
.endif
.endarea

; ---- surfaces 12-14: item names and descriptions, kite names, fishing ---------------------
; text_draw_line_h 0x800437F4 and text_draw_h 0x80043864. The x step sits in the loop
; branch's delay slot, so the jal takes the pointer step's place and the body steps the
; pointer and reloads the next word into v0 and v1 (each walker tests one of them; the
; stock delay slot loaded the word *before* the step, which the body re-reads).
.org 0x80043834
.area 4
.if ORIGINAL
    addiu   s0, s0, 2               ; stock: next word; delay slot `lhu v0,0(s0)`
.else
    jal     vwf_step_s1_s0_cur
.endif
.endarea

.org 0x80043848
.area 4
.if ORIGINAL
    addiu   s1, s1, 0xC             ; stock: x += 12, in the delay slot of `beqz v0`
.else
    nop
.endif
.endarea

.org 0x800438A4
.area 4
.if ORIGINAL
    addiu   s0, s0, 2               ; stock: next word; delay slot `lhu v1,0(s0)`
.else
    jal     vwf_step_s1_s0_cur
.endif
.endarea

.org 0x800438B8
.area 4
.if ORIGINAL
    addiu   s1, s1, 0xC             ; stock: x += 12, in the delay slot of `beqz v0`
.else
    nop
.endif
.endarea

; Descriptions, captions and the fishing messages take five lines at a 12-px pitch in the
; white under the picture, starting 8 px higher (Jay, 2026-09-24, option c;
; research/data/text-boxes.tsv). A Japanese entry's three lines move with them.
DESC_PEN_Y      equ 118
DESC_LINE_STEP  equ 12

.org 0x800438C4
.area 4
.if ORIGINAL
    addiu   s2, s2, 0x10            ; stock: text_draw_h's newline, y += 16
.else
    addiu   s2, s2, DESC_LINE_STEP
.endif
.endarea

.org 0x80041858                     ; bag_draw -> text_draw_h(text, 0xB8, y)
.area 4
.if ORIGINAL
    addiu   a2, zero, 0x7E          ; stock: y 126, in the jal's delay slot
.else
    addiu   a2, zero, DESC_PEN_Y
.endif
.endarea

.org 0x80043F48                     ; fish_msg_draw -> text_draw_h(msg, 0xB8, y)
.area 4
.if ORIGINAL
    addiu   a2, zero, 0x7E
.else
    addiu   a2, zero, DESC_PEN_Y
.endif
.endarea

; kite_list_draw 0x80041FE4: the names start where the item list's do (text-boxes.tsv).
.org 0x8004207C
.area 4
.if ORIGINAL
    addiu   a1, zero, 0x30          ; stock: x 48
.else
    addiu   a1, zero, 40
.endif
.endarea

; ---- surface 9: sysmsg_draw 0x800379EC (insect names; wrapper sysmsg_line_draw 0x80037BA8) ---
; The across pass counts glyphs in s2 and returns the count, which five callers turn into
; pixels (x 12) to place what follows the name or to right-align it (MUSI measures a name by
; drawing it off screen at x 0x258 first). Patched, it adds the glyph's width to s2 instead,
; so the return value is the line's width in pixels, and every consumer below takes it as
; that (asm/hhon.asm, asm/musi.asm). The down pass (a3 != 0) is left stock: all eleven calls
; in every image pass a3 = 0.
.org 0x80037B20
.area 4
.if ORIGINAL
    addiu   s3, s3, 0xC             ; stock: x += 12; delay slot `lhu a0,0(s0)` (next word)
.else
    jal     vwf_step_sysmsg_across
.endif
.endarea

.org 0x80037B3C
.area 4
.if ORIGINAL
    addiu   s2, s2, 1               ; stock: count, in the delay slot of `beqz v0`
.else
    nop                             ; the body adds the width
.endif
.endarea

; cage_hud_draw's date ("Date caught", asm/labels.asm) leaves the name's row for the row below
; the size, as far below it as the name is above (text-boxes.tsv, exe@8003D2E0); asm/hhon.asm
; moves HHON.OVL's copy of the HUD the same way.
CAGE_NAME_Y equ 0x1A                ; retail: the name and the date
CAGE_SIZE_Y equ 0x2D                ; retail: the size (0x80040058)
CAGE_DATE_Y equ (CAGE_SIZE_Y + CAGE_SIZE_Y - CAGE_NAME_Y)
.org 0x8003FFF8
.area 4
.if ORIGINAL
    addiu   a1, zero, 0x1A          ; stock: y 26, the name's row
.else
    addiu   a1, zero, CAGE_DATE_Y
.endif
.endarea

; cage_hud_draw: the next item goes 12 x count after the name; now the width itself.
.org 0x8003FF98
.area 3*4
.if ORIGINAL
    sll     v1, v0, 1
    addu    v1, v1, v0
    sll     v1, v1, 2               ; stock: v1 = 12 * count
.else
    move    v1, v0                  ; the width sysmsg_draw returns
    nop
    nop
.endif
.endarea

; ---- surface 11: sys_title_draw 0x8003C5EC (fish names) --------------------------------
; The name is centred in its panel (asm/hud_resident.asm).
.org 0x8003C68C
.area 4
.if ORIGINAL
    sll     s2, v0, 0x10            ; stock: y << 16; the next word is the loop's first
.else
    jal     vwf_fish_title_x
.endif
.endarea

.org 0x8003C6A0
.area 4
.if ORIGINAL
    addiu   s1, s1, 0xC             ; stock: x += 12; delay slot `lhu a0,0(s0)`
.else
    jal     vwf_step_s1_s0
.endif
.endarea

; ---- the island ---------------------------------------------------------------------------
; The second part of dbg_font_init (vwf.asm, DEBUG_FONT_SPLIT; measured dead on the paths
; research/vwf-prototype.md § "The free space" lists). Not assembled under ORIGINAL: it is
; dead retail code, not a site with a stock claim to check, and restating it would put the
; executable's bytes in the repo.
WALKER_ISLAND     equ DEBUG_FONT_SPLIT
WALKER_ISLAND_END equ DEBUG_FONT_ISLAND_END
SYSNAME_DRAW      equ 0x80037BA8    ; sysmsg_line_draw(id, x, y, a3, [16]) -> v0 = its width
OFFSCREEN_X       equ 0x258         ; where MUSI draws a name to measure it
OFFSCREEN_Y       equ 0x12C
NOTEBOOK_SYM_X    equ 0x10F         ; the exchange notebook's item after a name

.if ORIGINAL == 0
.org WALKER_ISLAND
.area WALKER_ISLAND_END - WALKER_ISLAND
vwf_island:

; The lookup is shared: a body keeps its caller's ra in t8, calls vwf_width_<stock> with
; the id load in the jal's delay slot (the routine's first instruction does not read at),
; and returns through t8 with its add in the last delay slot. Bodies are named by what they
; touch: pen register, where the id is, and a suffix when the body also steps the pointer
; (`next`: the id was at -2 and the pointer steps; `cur`: the id is at 0).

vwf_width_12:                       ; t9 = advance[at], 12 for a cell that is not English
    vwf_lookup_at 12
    jr      ra
    nop

vwf_width_10:                       ; the same, stock 10 (help_line_draw)
    vwf_lookup_at 10
    jr      ra
    nop

vwf_step_s5_s0:                     ; TITLE 17: s5 += advance[-2(s0)]
    move    t8, ra
    jal     vwf_width_12
    lhu     at, -2(s0)
    jr      t8
    addu    s5, s5, t9

vwf_step_v1_s0_s1:                  ; TITLE 19: v1 = s0 + advance[-2(s1)]
    move    t8, ra
    jal     vwf_width_12
    lhu     at, -2(s1)
    jr      t8
    addu    v1, s0, t9

vwf_step_s1_s0_next:                ; TITLE 20: s1 += advance[-2(s0)]; s0 += 2
    move    t8, ra
    jal     vwf_width_12
    lhu     at, -2(s0)
    addu    s1, s1, t9
    jr      t8
    addiu   s0, s0, 2

vwf_step_s1_s0_p10:                 ; help_line_draw: s1 += advance[-2(s0)], stock 10
    move    t8, ra
    jal     vwf_width_10
    lhu     at, -2(s0)
    jr      t8
    addu    s1, s1, t9

vwf_count_s2_s0:                    ; text_draw_right, count: s2 += advance[-2(s0)]; s1 += 1
    move    t8, ra
    jal     vwf_width_12
    lhu     at, -2(s0)
    addu    s2, s2, t9
    jr      t8
    addiu   s1, s1, 1

vwf_back_s2_s0:                     ; text_draw_right, draw: s2 -= advance[0(s0)]
    move    t8, ra
    jal     vwf_width_12
    lhu     at, 0(s0)
    jr      t8
    subu    s2, s2, t9

vwf_step_s1_answer:                 ; TITLE 18: s1 += advance[lh 2*s0(s4)] (glyph index s0)
    move    t8, ra
    sll     at, s0, 1
    addu    at, at, s4
    jal     vwf_width_12
    lhu     at, 0(at)
    jr      t8
    addu    s1, s1, t9

vwf_step_s1_s0_cur:                 ; text_draw_line_h / _h: s1 += advance[0(s0)]; s0 += 2;
    move    t8, ra                  ; v0 = v1 = the next word
    jal     vwf_width_12
    lhu     at, 0(s0)
    addu    s1, s1, t9
    addiu   s0, s0, 2
    lhu     v0, 0(s0)
    jr      t8
    lhu     v1, 0(s0)               ; (the caller's next instruction is a nop: load delay)

vwf_step_s1_s0:                     ; fish names, sumo move names: s1 += advance[-2(s0)]
    move    t8, ra
    jal     vwf_width_12
    lhu     at, -2(s0)
    jr      t8
    addu    s1, s1, t9

vwf_step_sysmsg_across:             ; sysmsg_draw across: s3 += width; s2 += width
    move    t8, ra
    jal     vwf_width_12
    lhu     at, -2(s0)
    addu    s3, s3, t9
    jr      t8
    addu    s2, s2, t9

    .align  4
; MUSI's exchange notebook (0x8007E670) draws an insect's name at x 175 and the item after it
; at a fixed x 271; at its three name sites (musi.asm) this draws the name to end there
; instead, measured first as MUSI measures its right-aligned names (0x8007D850: at
; OFFSCREEN_X, OFFSCREEN_Y, and a fifth argument of 1, which skips the glyph flush). All
; three pass a3 = 0 and a fifth argument of 0, which the second call passes on. A 96-px
; Japanese name lands where retail drew it.
vwf_name_before_sym:
    addiu   sp, sp, -32
    sw      ra, 24(sp)
    sw      s0, 20(sp)
    sw      s1, 28(sp)
    move    s0, a0
    move    s1, a2
    addiu   t0, zero, 1
    sw      t0, 16(sp)
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
    lw      ra, 24(sp)
    lw      s0, 20(sp)
    lw      s1, 28(sp)
    jr      ra
    addiu   sp, sp, 32

vwf_island_free:                    ; first unclaimed byte, reported by the build
.endarea
.endif
