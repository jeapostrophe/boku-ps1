; Subtitles for speech with no text on the disc (PLAN VO-02, VO-03). Included by vwf.asm,
; which owns the file, the equates and the ORIGINAL gate.
;
; Two kinds of clip, one subtitle (research/event-scripts.md § Voice-only entries):
;
; * An event's XA entry: a voice key with a null text offset. A build that gives the entry
;   English (a `(voice only)` row in a day file) has it drawn by the event's own renderer:
;     xa_handler      jal talk_set -> voice_sub_open: the call it replaces, then the entry's
;                     text -- unless its offset is null (every stock entry) or g_ev_notext
;                     is set (XAMSG skips msg_open then too)
;     event_update    jal text_set_light -> voice_sub_tick, once per event tick
; * A native play of g_xa_clips (XCH.nn): the day-1 bedtime clip in movie mode and the
;   epilogues in ENDOTI (the bug-sumo voices take the same hook; PLAN VO-06). Its English is
;   a row of the movie-subtitle block (boku.movie_block, "clips"), which movie_sub_load
;   reads before every movie -- and a movie plays before both (research/event-scripts.md
;   § Native clips). No event runs, so nothing else draws it:
;     xa_play_indexed jal xa_play -> clip_sub_play: the call it replaces, then the block's
;                     row for this clip, if there is one (clip_sub_block: movie mode and
;                     ENDOTI only, whatever the event runner's stale flag says -- VO-07)
;     main loop       jal 0x80014C18 -> clip_sub_frame, the last call before frame_flip:
;                     serve the subtitle and draw it, text and band, in front of the picture
;     day-1 bedtime   the VSync of 0x8002E568's wait loop -> clip_sub_wait: that loop draws
;                     nothing, so while a subtitle is up it builds and flips its own frame;
;                     and its closing xa_stop -> clip_sub_done, which flips an empty one
;
; Both kinds share one state and one server (voice_sub_service): the subtitle comes down when
; the XA status word clears (no script closes text after a clip), when the game mode changes
; (the next mode may reuse the words' memory) or when the page on screen is no longer the
; subtitle's; its page timers are counted here unless dialog_draw is counting
; them (only an event's, with auto-advance on). Coming down (voice_sub_drop) depends on what
; g_text_page shows:
;   inside the subtitle's words     text_reset, and the band and its linger countdown go
;                                   back to how they were when it opened
;   NULL (text_reset, WIN 0, END)   the band and countdown go back; the text is gone already
;   anything else                   another message opened over it and owns text and band

TALK_SET          equ 0x8003125C
TEXT_RESET        equ 0x8002BC5C
TEXT_SET_LIGHT    equ 0x8002BCAC
DIALOG_OPEN       equ 0x8002BD30
DIALOG_DRAW       equ 0x8002BDA8
DIALOG_PANEL_SHOW equ 0x8002EB54
DIALOG_PANEL_DRAW equ 0x8002E964
XA_PLAY           equ 0x8002B3E4
XA_STOP           equ 0x8002B518
FRAME_FLIP        equ 0x800126C4    ; (vsync count, OT length): DrawOTag, then swap buffers
CLEAR_OTAG_R      equ 0x800538C4
VSYNC             equ 0x8004BCEC
OT_LENGTH         equ 0x2000        ; what the main loop clears and draws (0x80011DF4)
CD_INT_TO_POS     equ 0x8004CAEC    ; DsIntToPos, DsRead, DsReadSync: the calls
CD_READ           equ 0x800506CC    ; movie_sub_load reads the block with (asm/movie.asm)
CD_READ_SYNC      equ 0x80050A7C

; Dead retail code (research/text-renderer.md § 6 candidate 2), unreferenced by any jal, j,
; data word or lui pair in the EXE or any overlay; each ends at the next function's addiu sp.
VOICE_OPEN_ISLAND     equ 0x80037698  ; date_label_draw_b
VOICE_OPEN_ISLAND_END equ 0x800377F8
VOICE_TICK_ISLAND     equ 0x80043928  ; the routine after text_nth
VOICE_TICK_ISLAND_END equ 0x80043A50
VOICE_SHOW_ISLAND     equ 0x80037414
VOICE_SHOW_ISLAND_END equ 0x80037524
CLIP_PLAY_ISLAND      equ 0x8001CA64
CLIP_PLAY_ISLAND_END  equ 0x8001CB58
CLIP_DRAW_ISLAND      equ 0x8001CC4C
CLIP_DRAW_ISLAND_END  equ 0x8001CCF4
CLIP_FRAME_ISLAND     equ 0x8001CDF4
CLIP_FRAME_ISLAND_END equ 0x8001CEB4

; ---- the XA opcode handler (0x8002F588): s0 -> the instruction, a0 = the speaker operand --
.org 0x8002F5B8
.area 4
.if ORIGINAL
    jal     0x8003125C              ; stock: talk_set(speaker)
.else
    jal     voice_sub_open
.endif
.endarea

; ---- event_update: text_set_light(0) just before dialog_draw -------------------------------
; The delay slot (move a0, zero) is left as it is; voice_sub_tick ends by jumping to
; text_set_light with a0 = 0 again.
.org 0x8002D3AC
.area 4
.if ORIGINAL
    jal     0x8002BCAC              ; stock: text_set_light(0)
.else
    jal     voice_sub_tick
.endif
.endarea

; ---- xa_play_indexed (0x8002B4E4): v1 = 12 x the clip's index, a0 -> its key (delay slot) --
.org 0x8002B500
.area 4
.if ORIGINAL
    jal     0x8002B3E4              ; stock: xa_play(key)
.else
    jal     clip_sub_play
.endif
.endarea

; ---- the main loop (0x80011DF4): the last call before frame_flip -------------------------
.org 0x80011E44
.area 4
.if ORIGINAL
    jal     0x80014C18              ; stock
.else
    jal     clip_sub_frame
.endif
.endarea

; ---- 0x8002E568, the day-1 bedtime clip's wait: VSync(0) in its loop ---------------------
.org 0x8002E580
.area 4
.if ORIGINAL
    jal     0x8004BCEC              ; stock: VSync(0)
.else
    jal     clip_sub_wait
.endif
.endarea

; ---- 0x8002E568 again: the xa_stop after its loop ------------------------------------------
.org 0x8002E5A4
.area 4
.if ORIGINAL
    jal     0x8002B518              ; stock: xa_stop()
.else
    jal     clip_sub_done
.endif
.endarea

; ---- the islands ---------------------------------------------------------------------------
; Not assembled under ORIGINAL: dead retail code has no stock claim to check, and restating
; it here would put the executable's bytes in the repo.
.if ORIGINAL == 0
.org VOICE_OPEN_ISLAND
.area VOICE_OPEN_ISLAND_END - VOICE_OPEN_ISLAND

voice_sub_open:
    addiu   sp, sp, -24
    sw      ra, 16(sp)
    jal     TALK_SET                ; the call this replaces
    nop
    jal     voice_sub_drop          ; the clip it belonged to has just been cut off
    nop
    lui     t0, 0x8003
    lbu     v0, 0x6374(t0)          ; g_ev_notext
    lbu     a0, 4(s0)               ; the message index (the calls kept s0)
    bnez    v0, @@done
    lw      t1, 0x6338(t0)          ; g_ev_block
    sll     v1, a0, 3               ; (load delay of t1; a0 is two loads back)
    addu    v1, v1, t1
    lw      v1, 0x14(v1)            ; the entry's text offset, as msg_open reads it
    nop
    beqz    v1, @@done              ; null: a stock XA, nothing to draw
    nop
    jal     voice_sub_show
    addu    a0, t1, v1
@@done:
    lw      ra, 16(sp)
    nop
    jr      ra
    addiu   sp, sp, 24

; Take a live subtitle down (the table in the header). Leaf but for text_reset; clobbers
; t0-t4, v0, v1, at and the argument registers, keeps the s registers.
voice_sub_drop:
    lui     t4, hi(voice_sub_live)
    lbu     v0, lo(voice_sub_live)(t4)
    lui     t0, 0x8003
    beqz    v0, @@out
    lw      t1, 0x59EC(t0)          ; g_text_page
    sb      zero, lo(voice_sub_live)(t4)
    beqz    t1, @@restore           ; nothing on screen: the band is still the subtitle's
    lw      t2, lo(voice_sub_text)(t4)
    lw      t3, lo(voice_sub_end)(t4)
    sltu    at, t1, t2
    bnez    at, @@out               ; another message's page
    sltu    at, t1, t3
    beqz    at, @@out
    nop
    addiu   sp, sp, -24
    sw      ra, 16(sp)
    jal     TEXT_RESET
    nop
    lw      ra, 16(sp)
    addiu   sp, sp, 24
    lui     t4, hi(voice_sub_live)
    lui     t0, 0x8003
@@restore:
    lbu     v0, lo(voice_sub_panel)(t4)
    lbu     v1, lo(voice_sub_linger)(t4)
    bnez    v0, @@out               ; the band was up before: it stays up
    sb      v1, 0x636C(t0)          ; the countdown as it was, either way
    sb      zero, -0x6EE2(t0)       ; dialog_panel_hide, inline
    sb      zero, 0x6541(t0)        ; and g_dlgbox_level, or the next panel draw fades a band out
@@out:
    jr      ra
    nop

; v0 -> the movie-subtitle block, or 0: when there is no block, and in any mode but movie
; mode (whose movie has just read it) and ENDOTI (mode 0x10), which writes over it while it
; starts (research/event-scripts.md § Native clips) and plays its clip once the drive is
; idle, so there it is read again first -- before xa_play, since a read after it would break
; the stream. No event runs in either mode, whatever the event runner's bit says
; (research/event-scripts.md § Native clips). Bug sumo's is PLAN VO-06.
clip_sub_block:
    addiu   sp, sp, -24
    sw      ra, 16(sp)
    lui     v1, 0x8002
    lbu     v1, 0x37E0(v1)          ; the game mode
    addiu   at, zero, 0x0E
    beq     v1, at, @@check         ; movie mode
    addiu   at, zero, 0x10
    bne     v1, at, @@none
    nop
    jal     clip_sub_read           ; ENDOTI
    nop
@@check:
    lui     t0, hi(MOVIE_SUB_BLOCK)
    addiu   t0, t0, lo(MOVIE_SUB_BLOCK)
    lw      v1, 0(t0)
    lui     at, MOVIE_SUB_MAGIC >> 16
    ori     at, at, MOVIE_SUB_MAGIC & 0xFFFF
    beq     v1, at, @@out
    move    v0, t0
@@none:
    move    v0, zero
@@out:
    lw      ra, 16(sp)
    nop
    jr      ra
    addiu   sp, sp, 24

clip_sub_loc:                       ; DslLOC of the block's first sector (clip_sub_read)
    .dw     0

; clip_sub_read's tail when every try failed: no block rather than part of one, as
; movie_sub_load leaves it. Here only because its own island is full.
clip_sub_give_up:
    lui     at, hi(MOVIE_SUB_BLOCK)
    sw      zero, lo(MOVIE_SUB_BLOCK)(at)
    lw      ra, 28(sp)
    lw      s0, 24(sp)
    jr      ra
    addiu   sp, sp, 32

voice_sub_open_end:
.endarea

.org VOICE_SHOW_ISLAND
.area VOICE_SHOW_ISLAND_END - VOICE_SHOW_ISLAND

; Put the words at a0 up as the subtitle: remember how the band was, find their end, open
; them in the band where msg_open would, and raise it (msg_open raises it only when its
; linger countdown is 0, and after a voiced line and WIN 0 the band is down with it at 30).
voice_sub_show:
    lui     t0, 0x8003
    lbu     v0, 0x636C(t0)          ; the band's linger countdown
    lbu     v1, -0x6EE2(t0)         ; g_dlgbox_visible (0x8002911E)
    lui     t4, hi(voice_sub_live)
    sb      v0, lo(voice_sub_linger)(t4)
    sb      v1, lo(voice_sub_panel)(t4)
    sw      a0, lo(voice_sub_text)(t4)
    lui     v0, 0x8002
    lbu     v0, 0x37E0(v0)          ; the game mode
    move    t2, a0
    sb      v0, lo(voice_sub_mode)(t4)
    sb      zero, lo(voice_sub_native)(t4)  ; clip_sub_play sets it for its own
@@scan:                             ; to one past the END word; a page break's operand is
    lhu     v0, 0(t2)               ; skipped, as dialog_draw skips it
    addiu   t2, t2, 2
    ori     at, zero, 0x8000
    beq     v0, at, @@found
    ori     at, zero, 0x8002
    bne     v0, at, @@scan
    nop
    b       @@scan
    addiu   t2, t2, 2
@@found:
    sw      t2, lo(voice_sub_end)(t4)
    addiu   v0, zero, 1
    sb      v0, lo(voice_sub_live)(t4)
    addiu   sp, sp, -24
    sw      ra, 16(sp)
    move    a3, a0
    addiu   a0, zero, PEN_X
    addiu   a1, zero, PEN_Y
    jal     DIALOG_OPEN
    move    a2, zero                ; horizontal, as dialogue.asm has msg_open pass
    jal     DIALOG_PANEL_SHOW
    nop
    lw      ra, 16(sp)
    nop
    jr      ra
    addiu   sp, sp, 24

; The block from its sectors, as movie_sub_load reads it (asm/movie.asm): up to 8 tries.
clip_sub_read:
    addiu   sp, sp, -32
    sw      ra, 28(sp)
    sw      s0, 24(sp)
    addiu   s0, zero, 8
@@read:
    beqz    s0, clip_sub_give_up
    addiu   s0, s0, -1
    addiu   a0, zero, MOVIE_SUB_LBA
    lui     a1, hi(clip_sub_loc)
    jal     CD_INT_TO_POS
    addiu   a1, a1, lo(clip_sub_loc)
    lui     a0, hi(clip_sub_loc)
    addiu   a0, a0, lo(clip_sub_loc)
    addiu   a1, zero, MOVIE_SUB_SECTORS
    lui     a2, hi(MOVIE_SUB_BLOCK)
    addiu   a2, a2, lo(MOVIE_SUB_BLOCK)
    jal     CD_READ
    addiu   a3, zero, 0x80
    beqz    v0, @@read
    nop
@@sync:
    jal     CD_READ_SYNC
    addiu   a0, sp, 16              ; its 8-byte result buffer
    beqz    v0, @@out
    addiu   at, zero, -1
    beq     v0, at, @@read
    nop
    b       @@sync
    nop
@@out:
    lw      ra, 28(sp)
    lw      s0, 24(sp)
    jr      ra
    addiu   sp, sp, 32

voice_sub_show_end:
.endarea

.org VOICE_TICK_ISLAND
.area VOICE_TICK_ISLAND_END - VOICE_TICK_ISLAND

voice_sub_text:                     ; the subtitle's first word
    .dw     0
voice_sub_end:                      ; one past its END word
    .dw     0
voice_sub_live:                     ; 1 while a subtitle this file opened may be up
    .db     0
voice_sub_panel:                    ; g_dlgbox_visible when it opened
    .db     0
voice_sub_linger:                   ; the linger countdown (0x8003636C) when it opened
    .db     0
voice_sub_half:                     ; toggles each 60 Hz frame: a timer counts at 30 Hz
    .db     0
voice_sub_mode:                     ; the game mode (0x800237E0) it opened in
    .db     0
voice_sub_native:                   ; 1: a g_xa_clips play's, drawn by clip_sub_draw
    .db     0
    .align  4
.if hi(voice_sub_text) != hi(voice_sub_native)
    .error  "the subtitle's variables must share a lui"
.endif

; Once a tick: v0 = 1 while the subtitle stays up. a0 says who counts its page timer and how
; often: 0 an event tick (30 Hz) -- dialog_draw counts while g_voice_active, this otherwise;
; 1 a 60 Hz frame, this counts every other one; 2 a 30 Hz frame, this counts each.
voice_sub_service:
    lui     t4, hi(voice_sub_live)
    lbu     v0, lo(voice_sub_live)(t4)
    lui     t0, 0x8003
    beqz    v0, @@out               ; v0 = 0: nothing up
    lw      t1, 0x59EC(t0)          ; g_text_page
    lw      t2, lo(voice_sub_text)(t4)
    lw      t3, lo(voice_sub_end)(t4)
    sltu    at, t1, t2
    bnez    at, @@drop              ; the page on screen is not the subtitle's
    sltu    at, t1, t3
    beqz    at, @@drop
    nop
    lui     v1, 0x8002
    lbu     v1, 0x37E0(v1)          ; the game mode: a new one reuses the words' memory
    lbu     at, lo(voice_sub_mode)(t4)
    lw      v0, 0x59D8(t0)          ; the XA status word; XAMSG waits on these two bits
    bne     v1, at, @@drop
    andi    v0, v0, 5
    beqz    v0, @@drop              ; the clip has stopped
    addiu   v0, zero, 1
    bnez    a0, @@native
    lbu     v1, 0x59F6(t0)          ; g_voice_active
    nop
    bnez    v1, @@out               ; an event's, auto-advancing: dialog_draw counts it
    nop
    b       @@count
    nop
@@native:
    addiu   at, zero, 2
    beq     a0, at, @@count
    lbu     v1, lo(voice_sub_half)(t4)
    nop
    xori    v1, v1, 1
    beqz    v1, @@out               ; the other 60 Hz frame
    sb      v1, lo(voice_sub_half)(t4)
@@count:
    lh      v1, 0x59F4(t0)          ; g_text_wait
    nop
    beqz    v1, @@out               ; no timer on this page
    addiu   v1, v1, -1
    bnez    v1, @@out
    sh      v1, 0x59F4(t0)
    lw      v1, 0x59E4(t0)          ; the timer ran out: dialog_next_page, inline
    sb      zero, 0x59E3(t0)        ; g_text_wait_armed
    ori     v1, v1, 8
    sw      v1, 0x59E4(t0)          ; g_text_flags |= 8
@@out:
    jr      ra
    nop
@@drop:
    addiu   sp, sp, -24
    sw      ra, 16(sp)
    jal     voice_sub_drop
    nop
    lw      ra, 16(sp)
    move    v0, zero
    jr      ra
    addiu   sp, sp, 24

voice_sub_tick:
    addiu   sp, sp, -24
    sw      ra, 16(sp)
    jal     voice_sub_service
    move    a0, zero
    lw      ra, 16(sp)
    addiu   sp, sp, 24
    j       TEXT_SET_LIGHT
    move    a0, zero

; v0 = 1 when event_update is the one to serve the subtitle: the event runner's bit is set
; and the subtitle is not a native clip's -- the bit is stale in a native clip's modes
; (research/event-scripts.md § Native clips). Clobbers v0, v1 and t5 only.
clip_sub_owned:
    lui     t5, 0x8003
    lw      v0, 0x637C(t5)          ; the event runner's flags
    lui     t5, hi(voice_sub_native)
    lbu     v1, lo(voice_sub_native)(t5)
    andi    v0, v0, 1
    jr      ra
    sltu    v0, v1, v0              ; the bit, and not native

voice_sub_tick_end:
.endarea

.org CLIP_PLAY_ISLAND
.area CLIP_PLAY_ISLAND_END - CLIP_PLAY_ISLAND

; The block, then xa_play, then the block's subtitle for this clip: its clips are found through
; the trailer before the glyph table (boku.movie_block, whose sizes are the MOVIE_SUB_ equates).
clip_sub_play:
    addiu   sp, sp, -32
    sw      ra, 28(sp)
    sw      s0, 24(sp)
    sw      s1, 20(sp)
    move    s0, v1                  ; 12 x the clip's index
.if MOVIE_SUB_CLIPS
    jal     clip_sub_block          ; before the clip: it may read the disc
.else
    move    v0, zero                ; a build with no clip subtitles: stock timing, no read
.endif
    move    s1, a0                  ; the key
    move    a0, s1
    jal     XA_PLAY                 ; the call this replaces
    move    s1, v0                  ; the block, or 0
    jal     voice_sub_drop          ; whatever clip was up has just been cut off
    nop
    beqz    s1, @@done
    lhu     v1, MOVIE_SUB_GLYPHS_FIELD(s1)
    nop
    addu    v1, s1, v1
    lhu     t1, -MOVIE_SUB_CLIP_TRAILER(v1) ; the clips' offset
    nop
    addu    t1, s1, t1
    lhu     t2, 0(t1)               ; their count
    addiu   t1, t1, MOVIE_SUB_CLIP_HEADER
@@next:
    beqz    t2, @@done
    addiu   t2, t2, -1
    lhu     v0, 0(t1)               ; its clip index
    lhu     a0, 2(t1)               ; its words' offset
    sll     v1, v0, 3
    sll     v0, v0, 2
    addu    v0, v0, v1              ; 12 x its index
    bne     v0, s0, @@next
    addiu   t1, t1, MOVIE_SUB_CLIP_ROW
    jal     voice_sub_show
    addu    a0, s1, a0
    lui     at, hi(voice_sub_native)
    addiu   v0, zero, 1
    sb      v0, lo(voice_sub_native)(at)
@@done:
    lw      ra, 28(sp)
    lw      s0, 24(sp)
    lw      s1, 20(sp)
    jr      ra
    addiu   sp, sp, 32

; The wait loop has ended with its clip: xa_stop, then one more of clip_sub_wait's frames,
; which drops the subtitle and flips an empty frame over it.
clip_sub_done:
    addiu   sp, sp, -24
    sw      ra, 16(sp)
    jal     XA_STOP                 ; the call this replaces
    nop
    lui     t0, hi(voice_sub_live)
    lbu     v0, lo(voice_sub_live)(t0)
    nop
    beqz    v0, @@out
    nop
    jal     clip_sub_flip
    nop
@@out:
    lw      ra, 16(sp)
    nop
    jr      ra
    addiu   sp, sp, 24

clip_sub_play_end:
.endarea

.org CLIP_DRAW_ISLAND
.area CLIP_DRAW_ISLAND_END - CLIP_DRAW_ISLAND

; The subtitle's text into OT slot 1, as event_update draws it, and then its band into slot 1
; as well (drawn first, so behind the text and in front of every picture in slot 2 and up --
; ENDOTI's stills are slot 2). dialog_draw counts no timer: voice_sub_service has.
clip_sub_draw:
    lui     t0, hi(voice_sub_native)
    lbu     v1, lo(voice_sub_native)(t0)
    nop
    beqz    v1, @@skip              ; an event's subtitle that outlived its event: served, not drawn
    nop
    addiu   sp, sp, -32
    sw      ra, 28(sp)
    sw      s0, 24(sp)
    lui     s0, 0x8003
    lbu     v0, 0x59F6(s0)          ; g_voice_active, held at 0 while dialog_draw runs
    nop
    sw      v0, 20(sp)
    sb      zero, 0x59F6(s0)
    jal     TEXT_SET_LIGHT
    move    a0, zero
    jal     DIALOG_DRAW
    nop
    lw      v0, 20(sp)
    lui     t0, 0x8002
    sb      v0, 0x59F6(s0)
    lw      v1, 0x593C(t0)          ; g_ot: dialog_panel_draw adds to its slot 2
    nop
    addiu   v1, v1, -4
    jal     DIALOG_PANEL_DRAW
    sw      v1, 0x593C(t0)
    lui     t0, 0x8002
    lw      v1, 0x593C(t0)
    nop
    addiu   v1, v1, 4
    sw      v1, 0x593C(t0)
    lw      ra, 28(sp)
    lw      s0, 24(sp)
    jr      ra
    addiu   sp, sp, 32
@@skip:
    jr      ra
    nop

clip_sub_draw_end:
.endarea

.org CLIP_FRAME_ISLAND
.area CLIP_FRAME_ISLAND_END - CLIP_FRAME_ISLAND

clip_sub_frame:
    addiu   sp, sp, -24
    sw      ra, 16(sp)
    jal     0x80014C18              ; the call this replaces
    nop
    jal     clip_sub_owned
    lui     t0, 0x8002
    bnez    v0, @@done              ; event_update serves it (clip_sub_owned)
    lw      a0, 0x37EC(t0)          ; the mode's vsync count: 0 or 1 runs this at 60 Hz
    addiu   t1, zero, 2             ; (load delay of a0)
    sltiu   v0, a0, 2
    jal     voice_sub_service
    subu    a0, t1, v0              ; 1 at 60 Hz, 2 at 30
    beqz    v0, @@done
    nop
    jal     clip_sub_draw
    nop
@@done:
    lw      ra, 16(sp)
    nop
    jr      ra
    addiu   sp, sp, 24

clip_sub_wait:
    lui     t0, hi(voice_sub_live)
    lbu     v0, lo(voice_sub_live)(t0)
    nop
    bnez    v0, clip_sub_flip
    nop
    j       VSYNC                   ; the call this replaces
    move    a0, zero
clip_sub_flip:                      ; clear, serve, draw if still up, flip (clip_sub_done too)
    addiu   sp, sp, -24
    sw      ra, 16(sp)
    lui     t0, 0x8002
    lw      a0, 0x593C(t0)          ; g_ot
    jal     CLEAR_OTAG_R
    addiu   a1, zero, OT_LENGTH
    jal     voice_sub_service
    addiu   a0, zero, 1             ; this loop runs at 60 Hz
    beqz    v0, @@empty             ; it has come down: flip an empty frame over it
    nop
    jal     clip_sub_draw
    nop
@@empty:
    move    a0, zero
    jal     FRAME_FLIP              ; VSync(0) is its first wait, as the stock loop's
    addiu   a1, zero, OT_LENGTH
    lw      ra, 16(sp)
    nop
    jr      ra
    addiu   sp, sp, 24

clip_sub_frame_end:
.endarea
.endif
