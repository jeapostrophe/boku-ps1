--[[ Cold boot → title → new game → skip the intro movie → the first dialogue line.

     The reproducible input script (frames are GPU vsyncs counted from process start,
     retail SCPH-5500 BIOS, interpreter; measured 2026-09-20):

        ~720   BIOS has copied SCPS_100.88 into RAM        (q0-exe-load.lua)
         835   PC reaches the EXE entry 0x80049154
       ~2250   title screen is up ("PRESS START BUTTON")
               START  (L.BOOT_PRESSES) → menu, cursor already on "start from the beginning"
               CIRCLE (L.BOOT_PRESSES) → memory-card check screen, then the intro FMV (~3400)
               START  (L.SKIP_MOVIE)   → skips the FMV; map H02001 loads
        3817   event_begin: E0171 (day 1, auto, H02001)
        3980   msg_open(0) → dialog_open(297, 22, 1, text): line E0171.0

     Without further input the whole arrival sequence autoplays (voiced pages turn on
     their timers and a message closes when its clip ends): E0171 → E0172 → E0174 → E0175 …

     Exit 0 when dialog_open fires with the expected literals; saves state
     "first-dialogue" 8 frames later (the text is on screen) and a shot of it.
     Exit 3 if it has not fired by BOKU_FRAMES (default 4600), 4 if the arguments differ.
--]]
local L = dofile(os.getenv('BOKU_REDUX_DIR') .. '/lib.lua')
local LIMIT = L.numenv('BOKU_FRAMES', '4600')
local script = L.script(L.BOOT_PRESSES, L.SKIP_MOVIE)

local opened_at, bad
L.bp(0x8002BD30, 'Exec', 4, 'dialog_open', function()
    if L.r32(0x8002BD30) == 0 then return true end -- before the EXE is loaded
    local r = PCSX.getRegisters().GPR.n
    L.say('BOOT f=%d dialog_open(x=%d, y=%d, vertical=%d, text=%08x) ra=%08x map=%s', L.frame, r.a0, r.a1, r.a2,
        r.a3, r.ra, L.rbytes(0x80026C00, 6))
    bad = not (r.a0 == 297 and r.a1 == 22 and r.a2 == 1 and r.ra == 0x8002CFD8)
    opened_at = L.frame
    return false
end)

L.on_frame(function(f)
    if script[f] then script[f]() end
    if opened_at and f == opened_at + 8 then
        L.shot('first-dialogue')
        L.say('BOOT saved %s', L.save_state('first-dialogue'))
        if bad then L.finish(4, 'dialog_open arguments are not (297, 22, 1) from msg_open') else L.finish(0, 'ok') end
    elseif f >= LIMIT then
        L.shot('boot-to-dialogue-timeout')
        L.finish(3, 'no dialogue by frame ' .. f)
    end
end)
