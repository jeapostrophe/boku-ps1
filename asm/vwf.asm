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
;   -strequ TITLE_PATH, HHON_PATH, MUSI_PATH (and TAKO_PATH)
;                       copies of the drawing overlays, patched in place the same way
;   -strequ TABLE_PATH  TABLE_IDS bytes: the pen advance of glyph ids 0 .. TABLE_IDS-1
;   -equ TABLE_IDS      how many ids the table covers; every other id advances FIXED_ADVANCE
;   -equ FIXED_ADVANCE  14, the stock pitch, so untranslated Japanese keeps its spacing
;   -equ PEN_X, PEN_Y   dialogue: top-left of the first glyph cell
;   -equ LINE_PITCH     dialogue: rows between lines (stock 13)
;   -equ BAND_Y, BAND_H dialogue: the backing band's top row and height
;   -equ BAND_BRIGHTNESS, BAND_BLEND
;                       dialogue: g_dlgbox_fade[6], the band's brightness and blend
;                       (semitrans + 1) while a message is up; stock 224, 1
;   -equ MAP_AREA_EXTRA bytes added to the engine's 0x6400 map work area (arena.asm)
;   -equ SEL_X, SEL_Y   select: top-left of the first option row's first cell
;   -equ SEL_PITCH      select: rows between option rows
;   -equ SEL_PAD        select: the box's margin around the measured text
;   -equ SEL_CURSOR_DX, SEL_CURSOR_DY
;                       select: where the cursor sprite sits relative to its row's origin
;   -equ MOVIE_SUB_BLOCK, MOVIE_SUB_LBA, MOVIE_SUB_SECTORS, MOVIE_SUB_MAGIC,
;        MOVIE_SUB_MASK_ROWS, MOVIE_SUB_RECORD_SHIFT
;                       movies: where the subtitle block is read from and to, and the
;                       numbers of its format (movie.asm; boku/movie_block.py owns them)
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

HEAP_START_STOCK equ 0x8008F3A4     ; the retail heap start, just past MUSI.OVL's file end
HEAP_START_NEW   equ 0x8008F800     ; = the end of the file's extent in RAM
CELL             equ 12             ; glyph_draw's sprite is 12 x 12 (0x8002BB4C)

; t9 = the advance of the glyph id in at; clobbers at (the first instruction does not read
; it, so a `lhu at` may come right before). A cell that is not English -- the table's
; FIXED_ADVANCE, or an id past the table -- advances `stock`, the surface's own pitch; with
; stock == FIXED_ADVANCE that test is skipped. place_font refuses an English advance of 14.
.macro vwf_lookup_at, stock
    lui     t9, hi(vwf_advance)
    addu    t9, t9, at
    lbu     t9, lo(vwf_advance)(t9)
.if stock == FIXED_ADVANCE
    sltiu   at, at, TABLE_IDS       ; (load delay of t9)
    bnez    at, @@have
    nop
    addiu   t9, zero, FIXED_ADVANCE
.else
    sltiu   at, at, TABLE_IDS       ; (load delay of t9)
    beqz    at, @@stock             ; past the table
    addiu   at, t9, -FIXED_ADVANCE
    bnez    at, @@have              ; an English cell
    nop
@@stock:
    addiu   t9, zero, stock
.endif
@@have:
.endmacro

; dbg_font_init 0x800221CC..0x80022494: 712 bytes of dead code (research/text-renderer.md
; § 6 candidate 2), shared. movie.asm's loader takes [ISLAND, SPLIT), walkers.asm's step
; bodies [SPLIT, END); each block is an .area, so either outgrowing its half is a build
; error, and moving SPLIT is the one edit that rebalances them.
DEBUG_FONT_ISLAND     equ 0x800221CC
DEBUG_FONT_SPLIT      equ 0x800222EC    ; 288 bytes for the movie loader
DEBUG_FONT_ISLAND_END equ 0x80022494

.include "dialogue.asm"
.include "select.asm"
.include "arena.asm"
.include "voice.asm"
.include "walkers.asm"
.include "movie.asm"

; ---- the heap's first byte ---------------------------------------------------------------
; 0x80068AF0 is the bump pointer itself (`main` zeroes from its initial value up). Starting it
; 1,116 bytes higher keeps the heap out of the room MUSI.OVL may grow into. Not resident space:
; an overlay load overwrites it (research/text-renderer.md § 6).
.org 0x80068AF0
.area 4
.if ORIGINAL
    .dw     HEAP_START_STOCK
.else
    .dw     HEAP_START_NEW
.endif
.endarea

; ---- g_pc_host, cleared in the file ---------------------------------------------------------
; 1 in the file and cleared by sys_init (0x80011FE4) before any reader runs; nothing sets it
; again. Starting it at 0 makes the PC-host branches of file_load and the cd_dir_* helpers
; unreachable from the first instruction, so nothing can ever jump into the island below.
.org 0x80023830
.area 1
.if ORIGINAL
    .byte   1                       ; stock: g_pc_host = 1 (the dev kit's PC file server)
.else
    .byte   0
.endif
.endarea

; ---- the PC-host island: the renderer's resident space --------------------------------------
; PCload/PCsave and the libsn PCopen/PCread/... module, 0x8005CD44..0x8005DCF8: reached only
; from the g_pc_host branches, which the byte above closes (research/text-renderer.md § 6 has
; the measurement and the ownership of every island). The advance table first, then the select's
; variables and hook routines (the dialogue advance fits in place and needs none; the
; fixed-pitch walkers' bodies are in walkers.asm's island). One area, so an overflow is a
; build error. Not assembled under ORIGINAL: dead retail code, not a site with a stock claim.
PC_HOST_ISLAND     equ 0x8005CD44
PC_HOST_ISLAND_END equ 0x8005DCF8
.if ORIGINAL == 0
.org PC_HOST_ISLAND
.area PC_HOST_ISLAND_END - PC_HOST_ISLAND
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
    vwf_lookup_at FIXED_ADVANCE
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
vwf_free:                           ; first unclaimed byte of the island, reported by the build
.endarea
.org PC_HOST_ISLAND_END
vwf_island_end:                     ; the edit set records it: grown text arrays take the tail
.endif

.close

; ---- TITLE.OVL --------------------------------------------------------------------------
; Overlays load at 0x80079A08 (research/text-renderer.md § 3); the build hands a copy of the
; member and compares it the same way. Sites in title.asm jump to the bodies above.
.open TITLE_PATH, 0x80079A08
.include "title.asm"
.close

; ---- HHON.OVL and MUSI.OVL -----------------------------------------------------------------
.open HHON_PATH, 0x80079A08
.include "hhon.asm"
.close

.open MUSI_PATH, 0x80079A08
.include "musi.asm"
.close
