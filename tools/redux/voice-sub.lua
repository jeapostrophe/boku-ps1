--[[ VO-02: boot, let day 1's arrival sequence play itself, and watch a voice-only clip.

     The boot is lib.lua's (the intro movie skipped); without further input the arrival
     sequence autoplays to E0184, Boku's room, whose message 2 is a voice-only XA clip
     (research/event-scripts.md § Voice-only entries). From the tick the XA opcode handler
     (0x8002F588) runs for BOKU_EVENT's message BOKU_MSG, every change of the dialogue state
     is printed, one line each:

       XA   f=<vsync> ev=<event id> msg=<index> voice_active=<g_voice_active>
       TEXT f=<vsync> page=<g_text_page> flags=<g_text_flags>
            busy=<XA status word 0x800359D8> panel=<g_dlgbox_visible>

     On the stock image the page stays 0: the handler opens no text. With asm/voice.asm and
     English on the entry, the page opens with the band up, turns on its timer, and goes
     back to 0 with the band down when busy clears. tests/test_real_voice_subtitle.py reads
     these lines.

       BOKU_EVENT, BOKU_MSG  the clip to watch (default 184, 2)
       BOKU_AFTER            vsyncs to watch after it starts (default 400)
       BOKU_SHOTS            also shoot every N vsyncs from the start (default 0: none)
       BOKU_FRAMES           give up at this vsync, moved later by however late the
                             title came (lib.lua after_title; default 16000): exit 3
       BOKU_SAVE             1: save the state "voice-start" (under BOKU_WORK/states) the
                             tick the clip starts
       BOKU_LOAD             a state name: load it instead of booting, and watch from there
       BOKU_CLEAR_AT         N: N vsyncs after the start, clear the page and its flags as
                             text_reset does (an event ending under the subtitle)

     Exit 0 once BOKU_AFTER vsyncs have been watched.
--]]
local L = dofile(os.getenv('BOKU_REDUX_DIR') .. '/lib.lua')
local LIMIT = L.numenv('BOKU_FRAMES', '16000')
local EVENT = L.numenv('BOKU_EVENT', '184')
local MSG = L.numenv('BOKU_MSG', '2')
local AFTER = L.numenv('BOKU_AFTER', '400')
local SHOTS = L.numenv('BOKU_SHOTS', '0')
local SAVE = os.getenv('BOKU_SAVE') == '1'
local LOAD = os.getenv('BOKU_LOAD')
local CLEAR_AT = L.numenv('BOKU_CLEAR_AT', '-1')
-- Anchored to the title (lib.lua after_title): fixed vsyncs miss it under load.
local boot = LOAD and function() return 0 end or L.after_title(L.BOOT_PRESSES, L.SKIP_MOVIE)

local XA_HANDLER, G_EV = 0x8002F588, 0x80036368
local TEXT_PAGE, TEXT_FLAGS = 0x800359EC, 0x800359E4
local XA_STATUS, VOICE_ACTIVE, PANEL_VISIBLE = 0x800359D8, 0x800359F6, 0x8002911E

-- The running event's id: *g_ev + 0x12, negative for an EV.BIN member.
local function event_id()
    local ev = L.r32(G_EV)
    if ev < 0x80000000 then return -1 end
    return math.abs(L.rs16(ev + 0x12))
end

local started
L.bp(XA_HANDLER, 'Exec', 4, 'xa', function()
    if L.r32(XA_HANDLER) == 0 then return true end -- before the EXE is loaded
    local pc = PCSX.getRegisters().GPR.n.a0
    local id, msg = event_id(), L.r8(pc + 4)
    L.say('XA f=%d ev=%d msg=%d voice_active=%d', L.frame, id, msg, L.r8(VOICE_ACTIVE))
    if id == EVENT and msg == MSG and not started then
        started = L.frame
        if SAVE then L.say('SAVED %s', L.save_state('voice-start')) end
    end
    return true
end)

local last
L.on_frame(function(f)
    local shift = boot(f)
    if LOAD and f == 2 then
        L.load_state(LOAD)
        started = f
        L.say('LOADED f=%d %s', f, LOAD)
    end
    if started and f == started + CLEAR_AT then
        L.w32(TEXT_PAGE, 0)
        L.w32(TEXT_FLAGS, 0)
        L.say('CLEARED f=%d', f)
    end
    if started then
        local state = string.format('page=%08x flags=%x busy=%x panel=%d', L.r32(TEXT_PAGE),
            L.r32(TEXT_FLAGS), L.r32(XA_STATUS), L.r8(PANEL_VISIBLE))
        if state ~= last then
            L.say('TEXT f=%d %s', f, state)
            last = state
        end
        if SHOTS > 0 and (f - started) % SHOTS == 0 then L.shot(string.format('voice-%05d', f)) end
        if f >= started + AFTER then L.finish(0, 'watched') end
    elseif f >= LIMIT + shift then
        L.finish(3, 'no XA for the clip by vsync ' .. f)
    end
end)
