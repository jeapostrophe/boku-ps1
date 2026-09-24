; The map work area, raised (PLAN PIPE-03: research/loading-and-memory.md § "Making room" 2).
; Included by vwf.asm, which owns the file, the equates and the ORIGINAL gate.
;
; A map pack's children 0-5 must fit in the 0x6400 bytes the engine keeps for the live map
; ("A") and for the incoming pack ("B"); map_commit executes `break` if child 6 starts past
; it. English text is child 1, and M_H06001 already overruns the retail figure by 628 bytes
; with days 1-7 alone. The constant lives in four instructions at three sites, all patched
; together to MAP_AREA = 0x6400 + MAP_AREA_EXTRA:
;
;   boot_load_resident  the bump that sizes A (after `sw s0, g_map_live`) and the one that
;                       sizes B (after `sw s0, g_map_load`): everything laid out after each
;                       moves up by MAP_AREA_EXTRA, the pointers with it -- the model pool,
;                       g_bg_clut_save and g_bg_save are all bump-derived, and nothing in
;                       the executable or an overlay holds 0x6400 as a literal for them
;                       (scanned: the only other 0x6400 in the EXE, 0x80012308, is the sound
;                       work buffer, which is not touched).
;   map_commit          the test `slti v0, v0, 0x6401` and the length of the A<->B swap.
;
; What it costs: the fixed arena ends 2 * MAP_AREA_EXTRA higher, under the level-C mode
; arena, bg_swap_in's 0x6000 scratch and the stack (top 0x801FFFF0). Measured on the retail
; layout over the arrival sequence and free roam (tools/vwf/stack-probe.lua): the stack's
; low-water mark is 0x801FF040, 4,016 bytes deep, and the level-C bump pointer never moved;
; the gap from the scratch's end to that mark is 20,044 bytes, less the 1,116 the heap
; raise (vwf.asm) spends. research/vwf-prototype.md § "The map work area".
;
; The reinserter measures against the same figure: build_prototype.py writes it to
; edits.json as map_work_area_end and boku build hands it to the plan.

; armips equates are textual, hence the parentheses.
MAP_AREA equ (0x6400 + MAP_AREA_EXTRA)
STACK_GAP equ 20044                 ; measured: scratch end 0x801FA1F4 to low-water 0x801FF040
STACK_DEPTH equ 4016                ; measured: 0x801FFFF0 - 0x801FF040
HEAP_RAISE equ (HEAP_START_NEW - HEAP_START_STOCK)

.if MAP_AREA_EXTRA % 4
    .error "MAP_AREA_EXTRA is a multiple of 4: the swap copies words"
.endif
.if MAP_AREA + 1 > 0x7FFF
    .error "MAP_AREA + 1 must fit slti's signed 16-bit immediate"
.endif
; The raise must leave the measured gap with one and a half times the measured stack
; depth to spare: the depth is the field's (level-C modes); a sumo bout and fishing are not
; measured. The item menu's deeper frame runs only in level-B modes, where level C is empty
; (research/vwf-prototype.md § "The map work area"). Past this, re-measure before raising.
.if 2 * MAP_AREA_EXTRA > STACK_GAP - HEAP_RAISE - STACK_DEPTH - STACK_DEPTH / 2
    .error "2 * MAP_AREA_EXTRA leaves the stack less than 1.5x its measured depth; re-measure"
.endif

; ---- boot_load_resident: the two bumps ---------------------------------------------------
.org 0x80012350
.area 4
.if ORIGINAL
    addiu   s0, s0, 0x6400          ; stock: A is 0x6400 bytes
.else
    addiu   s0, s0, MAP_AREA
.endif
.endarea

.org 0x80012370
.area 4
.if ORIGINAL
    addiu   s0, s0, 0x6400          ; stock: B is 0x6400 bytes
.else
    addiu   s0, s0, MAP_AREA
.endif
.endarea

; ---- map_commit: the test, and the swap length -------------------------------------------
.org 0x80017748
.area 4
.if ORIGINAL
    slti    v0, v0, 0x6401          ; stock: pack[+0x34] <= 0x6400, else break
.else
    slti    v0, v0, MAP_AREA + 1
.endif
.endarea

.org 0x800177E0
.area 4
.if ORIGINAL
    addiu   a2, zero, 0x6400        ; stock: mem_swap(A, B, 0x6400), in the jal's delay slot
.else
    addiu   a2, zero, MAP_AREA
.endif
.endarea

; ---- SUB.TIM's reload (0x80014E60): the stack's side of the raise ---------------------------
; A mode's way out reloads SUB.TIM's 50 sectors at g_arena_cur, and the raises move that up;
; from bug sumo the load ran through the stack (research/loading-and-memory.md § Leaving a
; mode). sub_tim_floor lowers the destination, only when it must, to the highest one whose
; sectors end under the stack's measured reach. The three instructions after the frame's
; `sw s0` become: save ra, jal sub_tim_floor with `move s0, a0` in its delay slot, and
; sub_tim_floor does the displaced `addiu a0, zero, 0xE1`.
SUB_TIM     equ 0xE1                ; g_cd_dir index of SUB.TIM
STACK_TOP   equ 0x801FFFF0
STACK_REACH equ (STACK_TOP - STACK_DEPTH)

.org 0x80014E68
.area 12
.if ORIGINAL
    move    s0, a0                  ; stock: s0 = the destination
    addiu   a0, zero, SUB_TIM       ; stock: file_load's index
    sw      ra, 0x1C(sp)            ; stock
.else
    sw      ra, 0x1C(sp)            ; first: the jal below overwrites ra
    jal     sub_tim_floor
    move    s0, a0
.endif
.endarea

.if ORIGINAL == 0
.org VOICE_SHOW_SPLIT
.area VOICE_SHOW_ISLAND_END - VOICE_SHOW_SPLIT
; s0 = the destination; returns a0 = SUB_TIM and s0 no higher than STACK_REACH less the
; file's sectors (its size from g_cd_dir, which a build that moves it keeps true). Clobbers
; v0 and at, which are dead in 0x80014E60 here.
sub_tim_floor:
    lui     at, hi(CD_DIR_SIZE + 4 * SUB_TIM)
    lw      v0, lo(CD_DIR_SIZE + 4 * SUB_TIM)(at)
    lui     at, hi(STACK_REACH)
    addiu   v0, v0, 2047
    srl     v0, v0, 11
    sll     v0, v0, 11              ; whole sectors: what the load writes
    addiu   at, at, lo(STACK_REACH)
    subu    at, at, v0
    sltu    v0, at, s0
    beqz    v0, @@fits
    addiu   a0, zero, SUB_TIM
    move    s0, at
@@fits:
    jr      ra
    nop
.endarea
.endif
