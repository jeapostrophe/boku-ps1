--[[ Reach the first SELECT (E0112.1, day 1, the living room) on PCSX-Redux and drive its
     cursor with the pad -- research/vwf-prototype.md § "SELECT on screen". Run through
     tools/redux/run-on-image.sh, which supplies lib.lua and BOKU_WORK; shoot.sh shows the
     whole sequence.

     Why a RAM poke: on day 1 the room the arrival sequence leaves Boku in is sealed --
     G14100 and G13100 each carry exactly one exit record, to each other (measured from
     the exit list below) -- so the living room is not walkable from a headless boot
     without whatever opens the door. The poke performs the map change the engine's own
     MAP opcode performs (map_request 0x80017A04 writes the base name to 0x80026C48,
     points 0x80026BD0 at the request block 0x80026C20, sets 0x80024728 = 1 and bit 1 of
     0x80024714; map_go 0x80017954 sets bit 0), so the map, its actors, its events and
     the clock are the game's. Nothing else is touched: the talk, the line, the select and
     the pad are stock.

     Env (frames count from 1 at script start; L.load_state first):
       BOKU_LOAD       save-state name under $BOKU_WORK/states (free roam, G14)
       BOKU_MAP        base map name to request at frame 5 ("G01" for E0112), or unset
       BOKU_INPUT      "frame:BUTTON:duration;..." as drive.lua (tank controls: UP walks,
                       LEFT/RIGHT turn 44 angle units (of 4096) per frame, DOWN turns
                       about, CIRCLE talks / confirms)
       BOKU_FRAMES     stop after N frames (default 600)
       BOKU_SHOT_AT    "f,f,f"   BOKU_SHOT_EVERY N   BOKU_PREFIX name
       BOKU_SAVE       save-state name written at the last frame
       BOKU_POS_EVERY  N = print Boku (slot 0) and the uncle (slot 1) every N frames

     Prints: MAP on every map / mode change (with the clock), EXITS (the live map's exit
     records: quad, centre, target) once per map, DLG on dialog_open, SELOPEN on
     select_open, SEL on the first three select_draw frames, and at the end how many
     frames drew a select.
--]]
local L = dofile(os.getenv('BOKU_REDUX_DIR') .. '/lib.lua')

local FRAMES = L.numenv('BOKU_FRAMES', '600')
local EVERY = L.numenv('BOKU_SHOT_EVERY', '0')
local POS_EVERY = L.numenv('BOKU_POS_EVERY', '0')
local PREFIX = os.getenv('BOKU_PREFIX') or 'select'
local at = {}
for f in (os.getenv('BOKU_SHOT_AT') or ''):gmatch('%d+') do at[tonumber(f)] = true end
local downs, ups = {}, {}
for f, names, dur in (os.getenv('BOKU_INPUT') or ''):gmatch('(%d+):([%w+]+):(%d+)') do
    f, dur = tonumber(f), tonumber(dur)
    for name in names:gmatch('[^+]+') do
        local b = assert(L.BTN[name], 'unknown button ' .. name)
        downs[f] = downs[f] or {}; table.insert(downs[f], b)
        ups[f + dur] = ups[f + dur] or {}; table.insert(ups[f + dur], b)
    end
end

local G_MAP_NAME, G_CLOCK, G_MODE, G_DIALOG = 0x80026C00, 0x80028FA0, 0x800237E0, 0x800359EC
local G_ACTORS = 0x80027778           -- u32 pointer per slot; actor {x@0, y@4, z@8 (<<4), angle@0x10}
local G_EXIT_LIST = 0x80026BE8        -- -> {u32 count, then 0x2C-byte records}, the live map's
local REQ_NAME, REQ_PTR, REQ_BLOCK = 0x80026C48, 0x80026BD0, 0x80026C20
local REQ_FLAGS, REQ_ONE = 0x80024714, 0x80024728

local function map() return (L.rbytes(G_MAP_NAME, 8):gsub('%z.*', '')) end
local function clock()
    return string.format('d%d %02d:%02d', L.r8(G_CLOCK), L.r8(G_CLOCK + 1), L.r8(G_CLOCK + 2))
end
local function s16(a) local v = L.r16(a); if v >= 0x8000 then v = v - 0x10000 end; return v end
local function s32(a) local v = L.r32(a); if v >= 0x80000000 then v = v - 0x100000000 end; return v end
local function actor(slot)
    local p = L.r32(G_ACTORS + 4 * slot)
    if p < 0x80000000 then return string.format('a%d=nil', slot) end
    return string.format('a%d=(%d,%d,%d ang=%d)', slot, s32(p) / 16, s32(p + 4) / 16, s32(p + 8) / 16,
        L.r16(p + 0x10) % 4096)
end
local function exits()
    local a = L.r32(G_EXIT_LIST)
    if a < 0x80000000 then return end
    local n = L.r32(a)
    L.say('EXITS map=%s count=%d', map(), n)
    for i = 0, math.min(n, 12) - 1 do
        local b = a + 4 + 0x2C * i
        L.say('  exit %d -> %s quad (%d,%d) (%d,%d) (%d,%d) (%d,%d) centre (%d,%d)', i,
            (L.rbytes(b + 0x28, 4):gsub('%z.*', '')), s16(b), s16(b + 4), s16(b + 8), s16(b + 12),
            s16(b + 16), s16(b + 20), s16(b + 24), s16(b + 28), s16(b + 0x20), s16(b + 0x24))
    end
end
local function request_map(name)
    for i = 1, 4 do L.w8(REQ_NAME + i - 1, name:byte(i) or 0) end
    L.w32(REQ_PTR, REQ_BLOCK)
    L.w32(REQ_ONE, 1)
    L.w32(REQ_FLAGS, bit.bor(L.r32(REQ_FLAGS), 3))
    L.say('REQUEST f=%d map %s (from %s, clock %s)', L.frame, name, map(), clock())
end

local sel_frames = 0
local function arm()
    L.bp(0x8002C234, 'Exec', 4, 'select_draw', function()
        sel_frames = sel_frames + 1
        if sel_frames <= 3 then
            local r = PCSX.getRegisters().GPR.n
            L.say('SEL f=%d select_draw type=%d variant=%d ra=%08x', L.frame, r.a0, r.a1, r.ra)
        end
        return true
    end)
    local opens = 0
    L.bp(0x8002D00C, 'Exec', 4, 'select_open', function()
        opens = opens + 1               -- the SELECT op calls it every frame it yields
        if opens <= 3 then
            local r = PCSX.getRegisters().GPR.n
            L.say('SELOPEN f=%d msg=%d type=%d variant=%d', L.frame, r.a0, r.a1, r.a2)
        end
        return true
    end)
    L.bp(0x8002BD30, 'Exec', 4, 'dialog_open', function()
        local r = PCSX.getRegisters().GPR.n
        L.say('DLG f=%d dialog_open x=%d y=%d vertical=%d', L.frame, r.a0, r.a1, r.a2)
        return true
    end)
end

local armed = false
local lastmap, lastmode, lastdlg = '', -1, -1
L.on_frame(function(f)
    if not armed then
        armed = true
        local name = os.getenv('BOKU_LOAD')
        if name and name ~= '' then L.load_state(name); L.say('LOADED %s: map %s clock %s', name, map(), clock()) end
        arm()
    end
    local want = os.getenv('BOKU_MAP')
    if want and want ~= '' and f == 5 then request_map(want) end
    for _, b in ipairs(ups[f] or {}) do L.release(b) end
    for _, b in ipairs(downs[f] or {}) do L.press(b) end
    local m, md, dl = map(), L.r8(G_MODE), L.r32(G_DIALOG)
    if m ~= lastmap or md ~= lastmode or dl ~= lastdlg then
        L.say('MAP f=%d map=%s mode=%02x dialog=%s clock=%s', f, m, md, dl ~= 0 and 'open' or 'closed', clock())
        if m ~= lastmap and f > 1 then exits() end
        lastmap, lastmode, lastdlg = m, md, dl
    end
    if f == 2 then exits() end
    if POS_EVERY > 0 and f % POS_EVERY == 0 then L.say('POS f=%d %s %s', f, actor(0), actor(1)) end
    if (EVERY > 0 and f % EVERY == 0) or at[f] then L.shot(string.format('%s-%05d', PREFIX, f)) end
    if f >= FRAMES then
        local save = os.getenv('BOKU_SAVE')
        if save and save ~= '' then L.say('SAVED %s', L.save_state(save)) end
        L.say('END f=%d map=%s select_frames=%d clock=%s', f, map(), sel_frames, clock())
        L.finish(0, 'ok')
    end
end)
