--[[ VO-06 on PCSX-Redux: a boy's bug-sumo clip, with its subtitle, from a cold boot.

     The route to bug sumo's desk is to-sumo.lua's (the intro's hand-over pointed at E4025 in
     A18). A new game has no bug to fight with, so the clip is played by making the CPU call
     xa_play_indexed(BOKU_CLIP) -- the call every sumo clip makes -- BOKU_AFTER_SUMO vsyncs
     into mode 7 (default 600, the desk up), at the entry of g_modes[7]'s update
     (0x80013804), which the main loop calls each frame: only a0-a3, sp and ra are live there,
     and they are put back when the call returns to it. tools/libretro/sumo_bout.py --gong
     reaches a real bout on Beetle.

     From the clip on, every change of the subtitle's state is printed, one line each:

       CLIP  f=<vsync> clip=<index> home=<level C's base> magic=<its first word>
       STATE f=<vsync> page=<g_text_page> panel=<g_dlgbox_visible> busy=<XA status>

     with a shot BOKU_SHOT vsyncs after the clip (default 20) and one when BOKU_AFTER have
     passed (default 300). Exit 0 then; 3 if bug sumo has not come by BOKU_FRAMES.
--]]
local L = dofile(os.getenv('BOKU_REDUX_DIR') .. '/lib.lua')
local CLIP = L.numenv('BOKU_CLIP', '4')
local AFTER_SUMO = L.numenv('BOKU_AFTER_SUMO', '600')
local SHOT = L.numenv('BOKU_SHOT', '20')
local AFTER = L.numenv('BOKU_AFTER', '300')
local LIMIT = L.numenv('BOKU_FRAMES', '8000')

local MODE_SET, FROM_MOVIE_MODE, SUMO = 0x80011A98, 0x80013C24, 7
local RETURN_MAP, NEXT_EVENT_ON, NEXT_EVENT, G_FLAGS = 0x80036588, 0x80036359, 0x8003635A, 0x80035E48
local XA_PLAY_INDEXED, SUMO_UPDATE, LEVEL_C = 0x8002B4E4, 0x80013804, 0x800258FC
local TEXT_PAGE, XA_STATUS, PANEL_VISIBLE = 0x800359EC, 0x800359D8, 0x8002911E
local boot = L.after_title(L.BOOT_PRESSES, L.SKIP_MOVIE)
local redirected, sumo_at, clip_at, saved, last

L.bp(MODE_SET, 'Exec', 4, 'mode_set', function()
    if L.r32(MODE_SET) == 0 then return true end -- before the EXE is loaded
    local r = PCSX.getRegisters().GPR.n
    if r.a0 == 5 and r.ra == FROM_MOVIE_MODE and not redirected then
        redirected = L.frame
        L.w32(RETURN_MAP, 0x00383141)       -- "A18\0"
        L.w8(NEXT_EVENT_ON, 1)
        L.w16(NEXT_EVENT, 4025)
        L.w8(G_FLAGS + 25, 2)
        L.w8(G_FLAGS + 30, 1)
    elseif r.a0 == SUMO and not sumo_at then
        sumo_at = L.frame
        L.say('SUMO f=%d', L.frame)
    end
    return true
end)

L.bp(SUMO_UPDATE, 'Exec', 4, 'sumo_update', function()
    local regs = PCSX.getRegisters()
    local n = regs.GPR.n
    if saved and not clip_at then
        -- back from the clip call: the update's own call goes on as it was made
        n.a0, n.a1, n.a2, n.a3, n.ra = saved[1], saved[2], saved[3], saved[4], saved[5]
        clip_at = L.frame
        local home = L.r32(LEVEL_C)
        L.say('CLIP f=%d clip=%d home=%08x magic=%08x', L.frame, CLIP, home, L.r32(home))
    elseif sumo_at and not saved and L.frame >= sumo_at + AFTER_SUMO then
        saved = { n.a0, n.a1, n.a2, n.a3, n.ra }
        n.a0, n.ra = CLIP, SUMO_UPDATE
        regs.pc = XA_PLAY_INDEXED
    end
    return true
end)

L.on_frame(function(f)
    local shift = boot(f)
    if clip_at then
        local state = string.format('page=%08x panel=%d busy=%x', L.r32(TEXT_PAGE),
            L.r8(PANEL_VISIBLE), L.r32(XA_STATUS))
        if state ~= last then
            L.say('STATE f=%d %s', f, state)
            last = state
        end
        if f == clip_at + SHOT then L.shot('clip') end
        if f >= clip_at + AFTER then
            L.shot('after')
            L.finish(0, 'watched')
        end
    elseif not sumo_at and f >= LIMIT + shift then
        L.finish(3, 'no bug sumo by vsync ' .. f)
    elseif sumo_at and f >= sumo_at + AFTER_SUMO + 600 then
        L.finish(3, 'no clip by vsync ' .. f)
    end
end)
