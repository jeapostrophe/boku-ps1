; Subtitles for voice-only clips in events (PLAN VO-02). Included by vwf.asm, which owns the
; file, the equates and the ORIGINAL gate.
;
; A voice-only entry is a voice key with a null text offset, named by the XA opcode
; (research/event-scripts.md § Voice-only entries). The stock XA handler plays the clip and
; opens no text; a build that gives the entry English (boku.build, a `(voice only)` row that
; carries some) only has that English drawn because of the two hooks here:
;
;   xa_handler    jal talk_set -> voice_sub_open: the call it replaces; then the subtitle a
;                 previous clip left up comes down (this XA has just cut that clip off), and
;                 msg_open opens this entry, as XAMSG does -- unless its text offset is null
;                 (every stock entry) or g_ev_notext is set (XAMSG skips msg_open then too)
;   event_update  jal text_set_light -> voice_sub_tick, once per tick before dialog_draw:
;                 when the clip stops, or the subtitle is no longer the page on screen, it
;                 comes down; while it plays with auto-advance off (a press stopped an
;                 earlier clip), its page timers are counted here, since dialog_draw
;                 counts them only while g_voice_active
;
; The closing is ours because no script closes text after an XA (research/event-scripts.md
; § Voice-only entries). Coming down (voice_sub_drop) depends on what g_text_page shows:
;   inside the subtitle's words     text_reset, and the band and its linger countdown go
;                                   back to how they were when it opened
;   NULL (text_reset, WIN 0, END)   the band and countdown go back; the text is gone already
;   anything else                   another message opened over it and owns text and band

TALK_SET         equ 0x8003125C
MSG_OPEN         equ 0x8002CF9C
TEXT_RESET       equ 0x8002BC5C
TEXT_SET_LIGHT   equ 0x8002BCAC
DIALOG_PANEL_SHOW equ 0x8002EB54

; Two islands of dead retail code (research/text-renderer.md § 6 candidate 2), unreferenced
; by any jal, data word or lui pair in any image: date_label_draw_b and the routine after
; text_nth.
VOICE_OPEN_ISLAND     equ 0x80037698
VOICE_OPEN_ISLAND_END equ 0x800377F8
VOICE_TICK_ISLAND     equ 0x80043928
VOICE_TICK_ISLAND_END equ 0x80043A50

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
    addu    t2, t1, v1
    lbu     v0, 0x636C(t0)          ; the band's linger countdown, which msg_open resets
    lbu     v1, -0x6EE2(t0)         ; g_dlgbox_visible (0x8002911E)
    lui     t4, hi(voice_sub_live)
    sb      v0, lo(voice_sub_linger)(t4)
    sb      v1, lo(voice_sub_panel)(t4)
    sw      t2, lo(voice_sub_text)(t4)
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
    jal     MSG_OPEN                ; a0 is still the message index
    sb      v0, lo(voice_sub_live)(t4)
    ; msg_open raises the band only when its linger countdown is 0; after a voiced line and
    ; WIN 0 the band is down and the countdown still 30, which runs down only with
    ; auto-advance off.
    jal     DIALOG_PANEL_SHOW
    nop
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
@@out:
    jr      ra
    nop

voice_sub_open_end:
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
    .align  4
.if hi(voice_sub_text) != hi(voice_sub_linger)
    .error  "the subtitle's variables must share a lui"
.endif

voice_sub_tick:
    lui     t4, hi(voice_sub_live)
    lbu     v0, lo(voice_sub_live)(t4)
    lui     t0, 0x8003
    beqz    v0, @@light
    lw      t1, 0x59EC(t0)          ; g_text_page
    lw      t2, lo(voice_sub_text)(t4)
    lw      t3, lo(voice_sub_end)(t4)
    sltu    at, t1, t2
    bnez    at, @@drop              ; the page on screen is not the subtitle's
    sltu    at, t1, t3
    beqz    at, @@drop
    nop
    lw      v0, 0x59D8(t0)          ; the XA status word; XAMSG waits on these two bits
    nop
    andi    v0, v0, 5
    beqz    v0, @@drop              ; the clip has stopped
    nop
    lbu     v0, 0x59F6(t0)          ; g_voice_active: dialog_draw counts the timer
    lh      v1, 0x59F4(t0)          ; g_text_wait
    bnez    v0, @@light
    nop
    beqz    v1, @@light             ; no timer on this page
    addiu   v1, v1, -1
    bnez    v1, @@light
    sh      v1, 0x59F4(t0)
    lw      v0, 0x59E4(t0)          ; the timer ran out: dialog_next_page, inline
    sb      zero, 0x59E3(t0)        ; g_text_wait_armed
    ori     v0, v0, 8
    b       @@light
    sw      v0, 0x59E4(t0)          ; g_text_flags |= 8
@@drop:
    addiu   sp, sp, -24
    sw      ra, 16(sp)
    jal     voice_sub_drop
    nop
    lw      ra, 16(sp)
    addiu   sp, sp, 24
@@light:
    j       TEXT_SET_LIGHT
    move    a0, zero

voice_sub_tick_end:
.endarea
.endif
