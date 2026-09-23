; TITLE.OVL's fixed-pitch horizontal walkers, routed through the width table (PLAN TXT-05,
; prototype). Included by vwf.asm inside `.open TITLE_PATH, 0x80079A08`; the hook bodies it
; jumps to live in the executable's walker island (walkers.asm), which every overlay can see.
;
; Each walker steps its pen by a literal 12 after `jal glyph_draw`; the step becomes a jal
; to a body that adds vwf_advance[id] instead (12 for a cell that is not English). Bodies
; write only at, t8 and t9, so whatever a delay slot loaded (a0, v0) survives. Sites and
; registers: research/vwf-prototype.md § "The fixed-pitch surfaces" (surfaces 17, 19, 20
; of research/text-renderer.md § 3).

; ---- surface 17: the memory-card messages (EXE array 0x8003D5F0), walker 0x8007CB54 ----
; Pen s5; s0 was stepped past the word before the draw, so the id is at -2(s0).
.org 0x8007CDD8
.area 4
.if ORIGINAL
    addiu   s5, s5, 0xC             ; stock: x += 12; delay slot `lhu a0,0(s0)` reloads a0
.else
    jal     vwf_step_s5_s0
.endif
.endarea

; ---- surface 19: the config labels (EXE array 0x8003D9BC), walker 0x8007FA94 ----------
; Line 4's pen (the setting under "Vibration"): research/data/text-boxes.tsv.
.org 0x8007FB2C
.area 4
.if ORIGINAL
    addiu   s0, zero, 0x58          ; stock: line 4 at x 88
.else
    addiu   s0, zero, 84
.endif
.endarea

; Pen s0 through v1; the id pointer is s1, stepped before the draw. Line 1 (s3 == 1) was
; letter-spaced 16 instead of 12 by the third word, which the proportional pen drops.
.org 0x8007FBC4
.area 5*4
.if ORIGINAL
    addiu   v1, s0, 0xC             ; stock: x + 12
    addiu   v0, zero, 1
    bne     s3, v0, 0x8007FBD8
    move    s0, v1                  ; stock: every line
    addiu   s0, v1, 4               ; stock: line 1 only, 4 more
.else
    jal     vwf_step_v1_s0_s1
    addiu   v0, zero, 1             ; (unchanged, delay slot)
    bne     s3, v0, 0x8007FBD8      ; (unchanged)
    move    s0, v1                  ; (unchanged)
    move    s0, v1
.endif
.endarea

; ---- surface 20a: extras label 5 (EXE array 0x8003DA00), walker 0x800803D8 -------------
; Pen s1; the step sits in the loop branch's delay slot, so the jal takes the pointer
; step's slot instead: the id is still at -2(s0) there, and the body steps s0 itself.
.org 0x8008045C
.area 4
.if ORIGINAL
    addiu   s0, s0, 2               ; stock: next word; delay slot `andi v0,a0,0x8000` is kept
.else
    jal     vwf_step_s1_s0_next
.endif
.endarea

.org 0x80080468
.area 4
.if ORIGINAL
    addiu   s1, s1, 0xC             ; stock: x += 12, in the delay slot of `beqz v0`
.else
    nop
.endif
.endarea

; The quiz-rate popup's tile (x, y, w, h), read only by quiz_popup_draw 0x80080484; its
; width is label 5's box (research/data/text-boxes.tsv). The digits under it keep their pens.
.org 0x80081AC8
.area 2
.if ORIGINAL
    .halfword 112                   ; stock: w
.else
    .halfword 136
.endif
.endarea

; ---- surface 20b: extras labels 0-4, walker 0x80080680 -----------------------------------
; Pen s1 through v1; lines 0 and 3 were letter-spaced 16. The step becomes a copy (x + 0)
; because the instruction after it is a branch; the advance is added at the pointer step.
.org 0x80080790
.area 4
.if ORIGINAL
    addiu   v1, s1, 0xC             ; stock: x + 12
.else
    move    v1, s1
.endif
.endarea

.org 0x800807A8
.area 4
.if ORIGINAL
    addiu   s1, v1, 4               ; stock: lines 0 and 3, 4 more
.else
    move    s1, v1
.endif
.endarea

.org 0x800807B0
.area 4
.if ORIGINAL
    addiu   s0, s0, 2               ; stock: next word; delay slot `move a1,zero` is kept
.else
    jal     vwf_step_s1_s0_next
.endif
.endarea

; ---- surface 18: the card screens' two answers (5 raw glyphs at 0x80081480), 0x8007CF7C ----
; Pen s1 from 0x70; the glyph index is s0 and the id is lh 2*s0(s4). After glyph SPLIT
; (`addiu v0,zero,1` at 0x8007D03C, compared at D040) the stock steps 0x30 more, which puts
; the second answer at 0xAC when the first is two 12-px glyphs; the loop draws COUNT glyphs
; (`slti v0,v0,5` at 0x8007D064). Proportional, the second answer starts at 0xAC itself, and
; SPLIT and COUNT are the translation's: boku build rewrites both from the `Yes | No` row
; (boku.layout.ANSWER_PAIR), so neither word is restated here.
YESNO_SECOND equ 0xAC               ; where the stock second answer starts

.org 0x8007D04C
.area 2*4
.if ORIGINAL
    addiu   s1, s1, 0x30            ; stock: the gap, in the delay slot of `j 0x8007D054`
    addiu   s1, s1, 0xC             ; stock: x += 12; delay slot `addiu v0,s2,1` follows
.else
    addiu   s1, zero, YESNO_SECOND
    jal     vwf_step_s1_answer
.endif
.endarea
