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
vwf_island_free:                    ; first unclaimed byte, reported by the build
.endarea
.endif
