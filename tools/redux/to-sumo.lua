--[[ Cold boot -> bug sumo's desk screen (mode 7, MUSI.OVL), with no save.

     Bug sumo is entered by one event, E4025 (map A18, variants 002/102): PROG 72, PROG 73,
     then PROG 3 with argument 7 -- game_mode_set(7) (research/event-scripts.md § Native
     clips). This script lets lib.lua's boot (anchored to the title) reach the intro's
     hand-over to the field -- game_mode_set(5) called from movie_queue_play at 0x80013C24 --
     and there points the return at E4025, as a MOVIE opcode would (ev_op_movie 0x800300FC):

       g_movie_return_map 0x80036588  "A18"
       0x80036359 / 0x8003635A        1 / 4025: the event that starts in the new map
       g_flags[25] = 2, g_flags[30] = 1  E4025's condition (A18 is variant 002 on day 1
                                        after 10:00 once flag 25 >= 1: EVVER.BIN)

     The field loads, E4025 runs, and game_mode_set(7) comes ~300 vsyncs after the hand-over
     (measured in two runs: hand-over at 3617, mode 7 at 3909 and at 3921). What it reaches is the desk: the insect notebook and Boku's cage,
     which ○ opens -- empty, since a new game has caught nothing. A bout needs a beetle in the
     cage (0x80045A10, 10 x 12-byte records): a record poked by hand with guessed fields hung
     the game when the cage opened, so this script does not poke one (research/save-format.md
     § Reaching the scenes other lanes asked for).

     Prints "MODE f=<vsync> a0=<mode> ra=<caller>" for every game_mode_set, "SUMO f=<vsync>"
     when mode 7 starts, then saves the state "sumo-desk" (under BOKU_WORK/states) and a shot
     BOKU_AFTER vsyncs later (default 300). Exit 0 then; 3 if mode 7 has not come by
     BOKU_FRAMES (default 8000, moved with the boot's shift).
--]]
local L = dofile(os.getenv('BOKU_REDUX_DIR') .. '/lib.lua')
local AFTER = L.numenv('BOKU_AFTER', '300')
local LIMIT = L.numenv('BOKU_FRAMES', '8000')

local MODE_SET, FROM_MOVIE_MODE, SUMO = 0x80011A98, 0x80013C24, 7
local RETURN_MAP, NEXT_EVENT_ON, NEXT_EVENT, G_FLAGS = 0x80036588, 0x80036359, 0x8003635A, 0x80035E48
local E4025 = 4025
local boot = L.after_title(L.BOOT_PRESSES, L.SKIP_MOVIE)
local redirected, sumo_at

L.bp(MODE_SET, 'Exec', 4, 'mode_set', function()
    if L.r32(MODE_SET) == 0 then return true end -- before the EXE is loaded
    local r = PCSX.getRegisters().GPR.n
    L.say('MODE f=%d a0=%x ra=%08x', L.frame, r.a0, r.ra)
    if r.a0 == 5 and r.ra == FROM_MOVIE_MODE and not redirected then
        redirected = L.frame
        L.w32(RETURN_MAP, 0x00383141)       -- "A18\0"
        L.w8(NEXT_EVENT_ON, 1)
        L.w16(NEXT_EVENT, E4025)
        L.w8(G_FLAGS + 25, 2)
        L.w8(G_FLAGS + 30, 1)
    elseif r.a0 == SUMO and not sumo_at then
        sumo_at = L.frame
        L.say('SUMO f=%d', L.frame)
    end
    return true
end)

L.on_frame(function(f)
    local shift = boot(f)
    if sumo_at and f == sumo_at + AFTER then
        L.shot('sumo-desk')
        L.say('SAVED %s', L.save_state('sumo-desk'))
        L.finish(0, 'at the desk')
    elseif not sumo_at and f >= LIMIT + shift then
        L.finish(3, 'no bug sumo by vsync ' .. f)
    end
end)
