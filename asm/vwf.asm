; The proportional, horizontal text patch for SCPS_100.88 (PLAN TXT-05, prototype).
;
; This is the file armips assembles; the surfaces are one include each, and the free space
; every surface shares is at the end. Design, table layout and what was seen on screen:
; research/vwf-prototype.md. Site lists per surface: research/text-renderer.md § 3, § 4c.
;
; Assembled by tools/vwf/build_prototype.py from the asm/ directory (includes are resolved
; against the working directory), which supplies every name below; nothing here is a
; product decision (PLAN TXT-03 / TXT-06 are open) and nothing here knows the typeface.
;
;   -strequ EXE_PATH    a COPY of the extracted executable; armips patches it in place
;   -strequ TABLE_PATH  TABLE_IDS bytes: the pen advance of glyph ids 0 .. TABLE_IDS-1
;   -equ TABLE_IDS      how many ids the table covers; every other id advances FIXED_ADVANCE
;   -equ FIXED_ADVANCE  14, the stock pitch, so untranslated Japanese keeps its spacing
;   -equ PEN_X, PEN_Y   dialogue: top-left of the first glyph cell
;   -equ LINE_PITCH     dialogue: rows between lines (stock 13)
;   -equ BAND_Y, BAND_H dialogue: the backing band's top row and height
;   -equ SEL_X, SEL_Y   select: top-left of the first option row's first cell
;   -equ SEL_PITCH      select: rows between option rows
;   -equ SEL_PAD        select: the box's margin around the measured text
;   -equ SEL_CURSOR_DX, SEL_CURSOR_DY
;                       select: where the cursor sprite sits relative to its row's origin
;   -equ ORIGINAL       0 builds the patch. 1 assembles, at every site, the instructions the
;                       retail executable holds there; the build runs that pass first and
;                       refuses unless the file comes back byte-identical. That is what
;                       checks each "stock:" claim in the includes against the
;                       contributor's own disc.
;
; RAM address = file offset + 0x8000F800; the executable is identity-loaded
; (research/renderer-runtime.md § Q0).

.psx
.open EXE_PATH, 0x8000F800

HEAP_START_STOCK equ 0x8008F3A4     ; first byte past the largest overlay (MUSI ends 0x8008F39A)
HEAP_START_NEW   equ 0x8008F800     ; = the end of the file's extent in RAM
CELL             equ 12             ; glyph_draw's sprite is 12 x 12 (0x8002BB4C)

; t9 = the advance of the glyph id in at (FIXED_ADVANCE past the table); clobbers at. The
; first instruction does not read at, so a `lhu at` may come right before the macro.
.macro vwf_lookup_at
    lui     t9, hi(vwf_advance)
    addu    t9, t9, at
    lbu     t9, lo(vwf_advance)(t9)
    sltiu   at, at, TABLE_IDS       ; (load delay of t9)
    bnez    at, @@have
    nop
    addiu   t9, zero, FIXED_ADVANCE
@@have:
.endmacro

.include "dialogue.asm"
.include "select.asm"

; ---- the heap's first byte ---------------------------------------------------------------
; 0x80068AF0 is the bump pointer itself; the file carries its initial value, `main` zeroes
; from that value up and every allocation advances it. Starting it 1,116 bytes higher leaves
; [HEAP_START_STOCK, HEAP_START_NEW) inside the file, loaded by the BIOS, above every
; overlay, and never cleared or allocated (measured: research/renderer-runtime.md § Q5).
.org 0x80068AF0
.area 4
.if ORIGINAL
    .dw     HEAP_START_STOCK
.else
    .dw     HEAP_START_NEW
.endif
.endarea

; ---- the space that frees ------------------------------------------------------------------
; The advance table first, then the variables and hook routines of the surfaces that need a
; jump out (the dialogue advance fits in place and needs none). Everything the includes
; reference by name is defined here, inside the one area, so an overflow is a build error.
.org HEAP_START_STOCK
.area HEAP_START_NEW - HEAP_START_STOCK
.if ORIGINAL
    .fill   HEAP_START_NEW - HEAP_START_STOCK, 0
.else
vwf_advance:
    .incbin TABLE_PATH              ; u8 advance per glyph id, TABLE_IDS of them
    .align  4

; select_draw records the pen's furthest x and the last row's y here; select_box_draw
; consumes them (and zeroes xmax) the same frame. Both live in the file as 0, so the box
; of a caller that never measured (the controls-help screen) comes from the stock table.
vwf_select_xmax:
    .dw     0
vwf_select_ymax:
    .dw     0
.if hi(vwf_select_xmax) != hi(vwf_select_ymax)
    .error  "vwf_select_xmax and vwf_select_ymax must share a lui"
.endif


; Called from select_draw in place of `addiu s0,s0,0xc` (select.asm). s1 has already
; stepped past the word just drawn, s2 is the pen x, s0 the row y; a0 was reloaded in the
; jal's delay slot and must survive; v0 at t0 t9 are dead.
vwf_select_advance:
    lhu     at, -2(s1)              ; the glyph id just drawn
    vwf_lookup_at
    addu    s2, s2, t9              ; the row's pen moves right instead of the column's down
    lui     t0, hi(vwf_select_xmax)
    lw      v0, lo(vwf_select_xmax)(t0)
    sw      s0, lo(vwf_select_ymax)(t0)
    slt     at, v0, s2
    beqz    at, @@done
    nop
    sw      s2, lo(vwf_select_xmax)(t0)
@@done:
    jr      ra
    nop

; The fixed-pitch walkers' steps (title.asm; research/vwf-prototype.md § "The fixed-pitch
; surfaces"). Named by what they touch: pen register, id pointer, and `next` when the body
; also steps the pointer because the stock step's own slot was a branch delay slot.
vwf_step_s5_s0:                     ; s5 += advance[-2(s0)]
    lhu     at, -2(s0)
    vwf_lookup_at
    jr      ra
    addu    s5, s5, t9

vwf_step_v1_s0_s1:                  ; v1 = s0 + advance[-2(s1)]
    lhu     at, -2(s1)
    vwf_lookup_at
    jr      ra
    addu    v1, s0, t9

vwf_step_s1_s0_next:                ; s1 += advance[-2(s0)]; s0 += 2
    lhu     at, -2(s0)
    vwf_lookup_at
    addu    s1, s1, t9
    jr      ra
    addiu   s0, s0, 2

; Called from select_box_draw in place of the table's w and h (select.asm). s1 -> the
; rect {x, y, w, h} (select.asm puts the corner SEL_PAD left of the cursor and above the
; first row); returns v0 = w, v1 = h. With a measurement pending, the box hugs the rows.
vwf_select_box:
    lui     t0, hi(vwf_select_xmax)
    lw      v0, lo(vwf_select_xmax)(t0)
    lhu     t1, 0(s1)               ; rect x (load delay of v0)
    beqz    v0, @@table
    lhu     t3, 2(s1)               ; rect y
    lw      t2, lo(vwf_select_ymax)(t0)
    sw      zero, lo(vwf_select_xmax)(t0)   ; consumed
    subu    v0, v0, t1
    addiu   v0, v0, SEL_PAD         ; w = xmax + pad - x
    subu    v1, t2, t3
    jr      ra
    addiu   v1, v1, CELL + SEL_PAD  ; h = ymax + cell + pad - y
@@table:
    lhu     v0, 4(s1)               ; stock w
    lhu     v1, 6(s1)               ; stock h
    jr      ra
    nop

    .align  4
vwf_free:                           ; first unclaimed byte of the gap, reported by the build
.endif
.endarea

.close

; ---- TITLE.OVL --------------------------------------------------------------------------
; Overlays load at 0x80079A08 (research/text-renderer.md § 3); the build hands a copy of the
; member and compares it the same way. Sites in title.asm jump to the bodies above.
.open TITLE_PATH, 0x80079A08
.include "title.asm"
.close
