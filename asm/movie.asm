; Subtitles over the 24-bit movies (PLAN FMV-04, milestone 1): design E2 of
; research/movies.md § 3, as built in § 7. Included by vwf.asm, which owns the file, the
; equates and the ORIGINAL gate.
;
; boku/movie_block.py owns the block's layout, and every number of it this file needs comes
; in as an equate rather than being retyped here:
;
;   -equ MOVIE_SUB_BLOCK    RAM address the cue block is read to
;   -equ MOVIE_SUB_LBA      the block's first sector
;   -equ MOVIE_SUB_SECTORS  how many sectors movie_sub_load reads
;   -equ MOVIE_SUB_MAGIC    the word at +0 (boku.movie_block.MAGIC)
;   -equ MOVIE_SUB_MASK_ROWS  rows and columns in a glyph mask (MASK)
;   -equ MOVIE_SUB_RECORD_SHIFT  log2 of a glyph record's size (RECORD_SIZE)
;
; Three sites, one routine each, bodies in the island below:
;   movie_play_entry  two words before the frame loop become a jal: movie_sub_load reads
;                     the block, once per movie, with the game's own CD reader
;   movie_get_frame   jal movie_frame_volume -> movie_sub_frame keeps the STR frame number
;   movie_dctout_cb   jal LoadImage -> movie_sub_blit paints the cue into the slice first
;
; The frame number movie_sub_frame keeps is the header of the frame whose sectors arrived
; last, and it advances while the current frame's slices are still uploading (measured:
; research/movies.md § 7, "which frame the number names"), so a cue's first and last frames
; change on a slice boundary, up to 1/15 s early. Accepted for a subtitle.

MOVIE_SUB_ISLAND     equ 0x80012E04  ; research/text-renderer.md § 6 candidate 2: 620 bytes of
MOVIE_SUB_ISLAND_END equ 0x80013070  ; directory helpers nothing references; § 7 measured it
MOVIE_FRAME_VOLUME   equ 0x800350F8
LOADIMAGE            equ 0x80053684
DSINTTOPOS           equ 0x8004CAEC
DSREAD               equ 0x800506CC
DSREADSYNC           equ 0x80050A7C

; ---- movie_play_entry: read the block before the first frame -----------------------------
; v0 holds 0x80030000 from the lui at 0x80034628 and a1 the frame count; the stock pair
; stores frames - 3 to g_movie_fade_frame. The jal takes the addiu as its delay slot and
; movie_sub_load opens with the store, so both keep their effect.
.org 0x8003462C
.area 2*4
.if ORIGINAL
    addiu   a1, a1, -3              ; stock: g_movie_fade_frame = frames - 3
    sw      a1, 0x66F4(v0)          ; stock
.else
    jal     movie_sub_load
    addiu   a1, a1, -3
.endif
.endarea

; ---- movie_get_frame: the STR frame number, in a0 ------------------------------------------
.org 0x80034D00
.area 4
.if ORIGINAL
    jal     0x800350F8              ; stock: movie_frame_volume(header.frame_no)
.else
    jal     movie_sub_frame
.endif
.endarea

; ---- movie_dctout_cb: the slice, before its upload --------------------------------------------
.org 0x80034C14
.area 4
.if ORIGINAL
    jal     0x80053684              ; stock: LoadImage(&rect, img[previous])
.else
    jal     movie_sub_blit
.endif
.endarea

; ---- the island ---------------------------------------------------------------------------
; Not assembled under ORIGINAL: the island is dead retail code, not a site with a stock
; claim to check, and restating 620 bytes of the executable here would put them in the repo.
.if ORIGINAL == 0
.org MOVIE_SUB_ISLAND
.area MOVIE_SUB_ISLAND_END - MOVIE_SUB_ISLAND

movie_sub_frame_no:                 ; the last STR header frame number seen
    .dw     0
movie_sub_loc:                      ; DslLOC of the block's first sector
    .dw     0

movie_sub_frame:
    lui     at, hi(movie_sub_frame_no)
    sw      a0, lo(movie_sub_frame_no)(at)
    j       MOVIE_FRAME_VOLUME
    nop

; The read half of cd_load_sync (0x800127C8), for a fixed sector: DsIntToPos, DsRead(loc,
; sectors, dst, 0x80) until it is accepted, DsReadSync until it reports done. Not copied:
; the libcd reset cd_load_sync runs at the head of every retry (0x800521FC — clears the
; callback slots, DsEndReadySystem); the block reads fine without it on both emulators.
; Bounded: after eight failed reads the block's magic is zeroed and the movie plays with no
; subtitles, rather than a retry loop a drive that dislikes the sector could never leave.
movie_sub_load:
    sw      a1, 0x66F4(v0)          ; the displaced g_movie_fade_frame store
    addiu   sp, sp, -0x20
    sw      ra, 0x1C(sp)
    sw      s0, 0x18(sp)
    addiu   s0, zero, 8
@@read:
    beqz    s0, @@give_up
    addiu   s0, s0, -1
    addiu   a0, zero, MOVIE_SUB_LBA
    lui     a1, hi(movie_sub_loc)
    jal     DSINTTOPOS
    addiu   a1, a1, lo(movie_sub_loc)
    lui     a0, hi(movie_sub_loc)
    addiu   a0, a0, lo(movie_sub_loc)
    addiu   a1, zero, MOVIE_SUB_SECTORS
    lui     a2, hi(MOVIE_SUB_BLOCK)
    addiu   a2, a2, lo(MOVIE_SUB_BLOCK)
    jal     DSREAD
    addiu   a3, zero, 0x80
    beqz    v0, @@read
    nop
@@sync:
    jal     DSREADSYNC
    addiu   a0, sp, 0x10            ; its 8-byte result buffer
    beqz    v0, @@done
    addiu   at, zero, -1
    beq     v0, at, @@read
    nop
    b       @@sync
    nop
@@give_up:
    lui     at, hi(MOVIE_SUB_BLOCK)
    sw      zero, lo(MOVIE_SUB_BLOCK)(at)
@@done:
    lw      ra, 0x1C(sp)
    lw      s0, 0x18(sp)
    jr      ra
    addiu   sp, sp, 0x20

; a0 -> the slice rect {x in VRAM halfwords, y, w, h}, a1 -> the slice's 16 x 240 pixels of
; 3 bytes, rows 48 bytes apart. Both go on to LoadImage untouched, and so does ra: this is
; a tail call. t0-t9, v0, v1, a2, a3 and at are caller-saved and LoadImage clobbers them
; from the same site; s0-s4 are kept on the stack. Runs in the DMA callback.
;
;   t0 block  t1 frame  t2 slice x (px)  t3 slice buffer  t4 cue  t5 cues left
;   t6 line cursor  t7 pen x  t8 line y  t9 glyph record
;   s0 first mask column drawn (then + 16, the shift into the sign bit)  s1 columns drawn
;   s2 row's first pixel  s3 mask row  s4 rows left
movie_sub_blit:
    lui     t0, hi(MOVIE_SUB_BLOCK)
    addiu   t0, t0, lo(MOVIE_SUB_BLOCK)
    lw      t1, 0(t0)
    lui     t2, MOVIE_SUB_MAGIC >> 16
    ori     t2, t2, MOVIE_SUB_MAGIC & 0xFFFF
    bne     t1, t2, @@out
    lui     t1, hi(movie_sub_frame_no)
    lw      t1, lo(movie_sub_frame_no)(t1)
    lhu     t5, 4(t0)               ; cue count
    lhu     t2, 0(a0)               ; slice x, halfwords: 24 per 16 pixels
    addiu   t6, zero, 3
    sll     t2, t2, 1
    divu    t2, t6
    beqz    t5, @@out
    mflo    t2                      ; x0 = x * 2 / 3
    addiu   sp, sp, -0x20
    sw      s0, 0x00(sp)
    sw      s1, 0x04(sp)
    sw      s2, 0x08(sp)
    sw      s3, 0x0C(sp)
    sw      s4, 0x10(sp)
    move    t3, a1
    addiu   t4, t0, 8
@@cue:
    lhu     v0, 0(t4)               ; start
    lhu     v1, 2(t4)               ; end
    slt     at, t1, v0
    bnez    at, @@next_cue
    slt     at, v1, t1
    lhu     v0, 4(t4)               ; lines offset
    bnez    at, @@next_cue
    addu    t6, t0, v0
@@line:
    addiu   t6, t6, 1               ; a line's header is halfword-aligned: round the
    srl     t6, t6, 1               ; cursor up past the previous line's odd byte
    sll     t6, t6, 1
    lhu     v0, 0(t6)               ; x, or 0xFFFF after the last line
    lhu     t8, 2(t6)               ; y
    ori     v1, zero, 0xFFFF
    beq     v0, v1, @@next_cue
    move    t7, v0
    addiu   t6, t6, 4
@@glyph:
    lbu     at, 0(t6)               ; glyph index, or 0xFF at the line's end
    addiu   t6, t6, 1
    addiu   v0, zero, 0xFF
    beq     at, v0, @@line
    sll     v0, at, MOVIE_SUB_RECORD_SHIFT  ; index * the record size
    lhu     v1, 6(t0)               ; glyphs offset
    addu    v0, v0, t0
    addu    t9, v0, v1
    ; The mask's column 0 is at pen - 1. Columns c0 = max(0, x0 - (pen - 1)) up to
    ; c1 = min(14, x0 + 16 - (pen - 1)) fall in this slice.
    addiu   v0, t7, -1
    subu    s0, t2, v0
    bgez    s0, @@c0
    addiu   s1, t2, 16
    move    s0, zero
@@c0:
    subu    s1, s1, v0
    slti    at, s1, MOVIE_SUB_MASK_ROWS + 1
    bnez    at, @@c1
    addiu   v1, t8, -1              ; the mask's row 0 is at y - 1
    addiu   s1, zero, MOVIE_SUB_MASK_ROWS
@@c1:
    subu    s1, s1, s0              ; columns to draw
    blez    s1, @@advance
    sll     at, v1, 4
    sll     v1, v1, 5
    addu    s2, at, v1              ; (y - 1) * 48 bytes
    addu    at, v0, s0
    subu    at, at, t2              ; the slice column of the first one, 0..15
    sll     v1, at, 1
    addu    at, at, v1              ; * 3 bytes
    addu    s2, s2, at
    addu    s2, s2, t3
    addiu   s3, t9, 4               ; glyph rows; the outline rows follow them
    addiu   s4, zero, MOVIE_SUB_MASK_ROWS
    addiu   s0, s0, 16              ; the shift that puts column c0 in the sign bit
@@row:
    lhu     v0, 0(s3)
    lhu     v1, 2*MOVIE_SUB_MASK_ROWS(s3)
    move    a2, s2
    or      at, v0, v1
    beqz    at, @@next_row
    sllv    v0, v0, s0
    sllv    v1, v1, s0
    move    a3, s1
@@column:
    bgez    v0, @@not_ink
    addiu   at, zero, 0xFF          ; white
    sb      at, 0(a2)
    sb      at, 1(a2)
    b       @@next_column
    sb      at, 2(a2)
@@not_ink:
    bgez    v1, @@next_column
    addiu   at, zero, 0x18          ; the outline: the renderer's dark shadow (0x18,0x18,0x14)
    sb      at, 0(a2)
    sb      at, 1(a2)
    addiu   at, zero, 0x14
    sb      at, 2(a2)
@@next_column:
    sll     v0, v0, 1
    sll     v1, v1, 1
    addiu   a3, a3, -1
    bnez    a3, @@column
    addiu   a2, a2, 3
@@next_row:
    addiu   s3, s3, 2
    addiu   s4, s4, -1
    bnez    s4, @@row
    addiu   s2, s2, 48
@@advance:
    lbu     at, 0(t9)               ; the pen advance (the VWF table's width)
    b       @@glyph
    addu    t7, t7, at              ; two instructions after the load
@@next_cue:
    addiu   t5, t5, -1
    bnez    t5, @@cue
    addiu   t4, t4, 8
    lw      s0, 0x00(sp)
    lw      s1, 0x04(sp)
    lw      s2, 0x08(sp)
    lw      s3, 0x0C(sp)
    lw      s4, 0x10(sp)
    addiu   sp, sp, 0x20
@@out:
    j       LOADIMAGE
    nop

movie_sub_end:
.endarea
.endif
