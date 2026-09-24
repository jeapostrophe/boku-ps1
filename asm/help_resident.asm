; The controls-help screen's bottom sentence on three rows: draws line 11's second row when the
; build split it (boku.help_screen has the mechanism; the HELP_ equates come from it).
; Included by vwf.asm in the PC-host island.

HELP_LINE equ 0x800353F8            ; help_line(n, x, y): item n of g_help_text at (x, y)

vwf_help_extra_row:
    addiu   sp, sp, -24
    sw      ra, 16(sp)
    lui     t0, hi(HELP_NEXT_Y)
    lbu     a2, lo(HELP_NEXT_Y)(t0)             ; line 12's y
    lui     t0, hi(HELP_SPLIT_X)
    lbu     a1, lo(HELP_SPLIT_X)(t0)            ; line 11's x
    addiu   t1, zero, HELP_NEXT_Y_RETAIL + HELP_ROW_PITCH  ; where the build moves line 12
    bne     a2, t1, @@done
    nop
    addiu   a2, a2, -HELP_ROW_PITCH             ; the row line 12 left
    jal     HELP_LINE
    addiu   a0, zero, HELP_EXTRA_ITEM
@@done:
    lw      ra, 16(sp)
    lui     v0, 0x8002                          ; the two instructions the jal replaced
    lbu     s1, 0x5917(v0)
    jr      ra
    addiu   sp, sp, 24
