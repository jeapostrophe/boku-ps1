--[[ Open one of the game's books by force and log what draws its text (PLAN GFX-05).

     A BOKU_POKES file for tools/redux/drive.lua. It performs mode_set (0x80011A98) from
     Lua -- the mode byte pair at 0x800237E0/E4, the previous mode at 0x800237E5, the
     change flag 0x80024728 and the arena base 0x800258E0 from the g_modes record -- so
     the dispatcher (0x80011C94) runs the mode's own init on the next frame. Nothing about
     the screen is faked: the overlay loads, the files load, the state machine runs.

     Env:
       BOKU_MODE      mode to enter at frame 3: 10 = HHON (the insect box),
                      11/12/13 = ZUKAN (the desk books)
       BOKU_SEEN      "id=state,..." -> the insect book-state byte 0x8003DF92 + 3*id
                      (exe.c 0x80037D38: 0 unseen, 1 seen, 2 caught, 3 via 0x80037CC8)
       BOKU_CAUGHT    "slot=id,..." -> caught record 0x80046F28 + 12*slot: id at +0, +3 = 1
       BOKU_SUBSTATE  "frame:value,..." -> HHON's sub-state word 0x80080600
       BOKU_ZSTATE    "frame:value,..." -> ZUKAN's sub-state word 0x800459DC
       BOKU_W32       "frame:addr=value,..." -> any other word, hex or decimal
       BOKU_GLYPHS    glyph lines to print per frame (default 4)

     Navigate HHON by sub-state pokes, not the pad: under drive.lua's presses the pad word
     0x80072766 stayed 0 for the whole of mode 10 (measured 2026-09-21, work/gfx05/hhon-run2.log)
     while the same presses registered in mode 13. Not chased. BOKU_SUBSTATE=120:17 opens the
     grid (state 0x11 loads MZ00, fades, and lands in 0x13).

     Prints: WALK for every hhon_entry_draw (0x8007C278) / hhon_text_scroll_v (0x8007C1C4)
     call with the text's offset in HHON.OVL, GLYPH for the first glyphs each frame with
     the OT layer, GSUM per frame (count and x/y range per return address), LOAD for
     every file_load / file_load_b (index, destination), and STATE on every change of
     the mode byte and the two sub-state words.
--]]
local L = ...

local MODE = L.numenv('BOKU_MODE', '10')
local NGLYPH = L.numenv('BOKU_GLYPHS', '4')
local G_MODE, G_MODE_NEXT, G_MODE_PREV, G_CHANGE, G_ARENA = 0x800237E0, 0x800237E4, 0x800237E5, 0x80024728, 0x800258E0
local G_MODES = 0x800236BC            -- 18 x {update, init, vsync, void **arena_base}
local G_BOOK_STATE = 0x8003DF92        -- + 3*id
local G_CAUGHT = 0x80046F28            -- 12-byte records
local G_HHON_STATE, G_ZUKAN_STATE = 0x80080600, 0x800459DC
local G_TEXT_LAYER = 0x80028E3C
local OVL_BASE, ENTRY_ARRAY = 0x80079A08, 0x5328

local function pairs_of(env)
    local t = {}
    for a, b in (os.getenv(env) or ''):gmatch('(%d+)[=:](%d+)') do t[#t + 1] = { tonumber(a), tonumber(b) } end
    return t
end

local function mode_set(m)
    L.w8(G_MODE_PREV, L.r8(G_MODE_NEXT))
    L.w8(G_MODE, m); L.w8(G_MODE_NEXT, m)
    L.w32(G_CHANGE, 1)
    L.w32(G_ARENA, L.r32(L.r32(G_MODES + 16 * m + 12)))
    L.say('POKE f=%d mode_set(%d): prev %d, arena %08x', L.frame, m, L.r8(G_MODE_PREV), L.r32(G_ARENA))
end

for _, p in ipairs(pairs_of('BOKU_SEEN')) do
    L.w8(G_BOOK_STATE + 3 * p[1], p[2])
    L.say('POKE book state insect %d = %d', p[1], p[2])
end
for _, p in ipairs(pairs_of('BOKU_CAUGHT')) do
    local rec = G_CAUGHT + 12 * p[1]
    L.w8(rec, p[2]); L.w8(rec + 3, 1)
    L.say('POKE caught slot %d = insect %d', p[1], p[2])
end
local substate, zstate, words = {}, {}, {}
for _, p in ipairs(pairs_of('BOKU_SUBSTATE')) do substate[p[1]] = p[2] end
for _, p in ipairs(pairs_of('BOKU_ZSTATE')) do zstate[p[1]] = p[2] end
for f, a, v in (os.getenv('BOKU_W32') or ''):gmatch('(%d+):([%w]+)=([%w]+)') do
    f = tonumber(f); words[f] = words[f] or {}
    table.insert(words[f], { tonumber(a), tonumber(v) })
end

-- Glyph bookkeeping per frame, keyed by the caller's return address.
local glyphs, printed = {}, 0
local function note_glyph(id, x, y, layer, ra)
    local g = glyphs[ra]
    if not g then g = { n = 0, x0 = x, x1 = x, y0 = y, y1 = y }; glyphs[ra] = g end
    g.n = g.n + 1
    if x < g.x0 then g.x0 = x end; if x > g.x1 then g.x1 = x end
    if y < g.y0 then g.y0 = y end; if y > g.y1 then g.y1 = y end
    if printed < NGLYPH then
        printed = printed + 1
        L.say('GLYPH f=%d id=%d x=%d y=%d layer=%d ra=%08x', L.frame, id, x, y, layer, ra)
    end
end
local function s16(v) v = v % 0x10000; if v >= 0x8000 then v = v - 0x10000 end; return v end

L.bp(0x8002BA2C, 'Exec', 4, 'glyph_draw', function()
    local r = PCSX.getRegisters().GPR.n
    note_glyph(r.a0, s16(r.a1), s16(r.a2), L.r32(G_TEXT_LAYER), r.ra)
    return true
end)
L.bp(0x8002B9FC, 'Exec', 4, 'glyph_draw_layer', function()
    local r = PCSX.getRegisters().GPR.n
    note_glyph(r.a0, s16(r.a1), s16(r.a2), r.a3, r.ra)
    return true
end)
local function walker(name, addr, fmt)
    L.bp(addr, 'Exec', 4, name, function()
        local r = PCSX.getRegisters().GPR.n
        local off = r.a0 - OVL_BASE
        L.say('WALK f=%d %s text=hhon+0x%x (entry array +0x%x) ' .. fmt .. ' ra=%08x', L.frame, name, off,
            off - ENTRY_ARRAY, r.a1, r.a2, r.a3, r.ra)
        return true
    end)
end
walker('hhon_entry_draw', 0x8007C278, 'insect=%d (a2=%d a3=%d)')
walker('hhon_text_scroll_v', 0x8007C1C4, 'x=%d scroll=%d insect=%d')
for name, addr in pairs({ file_load = 0x800129E0, file_load_b = 0x80012AB0 }) do
    L.bp(addr, 'Exec', 4, name, function()
        local r = PCSX.getRegisters().GPR.n
        L.say('LOAD f=%d %s index=%d dest=%08x ra=%08x', L.frame, name, r.a0, r.a1, r.ra)
        return true
    end)
end

local last = {}
L.on_frame(function(f)
    if f == 3 then mode_set(MODE) end
    if substate[f] then L.w32(G_HHON_STATE, substate[f]); L.say('POKE f=%d hhon state = %d', f, substate[f]) end
    if zstate[f] then L.w32(G_ZUKAN_STATE, zstate[f]); L.say('POKE f=%d zukan state = %d', f, zstate[f]) end
    for _, w in ipairs(words[f] or {}) do L.w32(w[1], w[2]); L.say('POKE f=%d [%08x] = %d', f, w[1], w[2]) end
    local now = { mode = L.r8(G_MODE), hhon = L.r32(G_HHON_STATE), zukan = L.r32(G_ZUKAN_STATE), pad = L.r16(0x80072766),
        scroll = L.rs16(0x800805DC) }
    for _, k in ipairs({ 'mode', 'hhon', 'zukan', 'pad', 'scroll' }) do
        if now[k] ~= last[k] then
            L.say('STATE f=%d %s %s -> %d', f, k, tostring(last[k]), now[k])
            last[k] = now[k]
        end
    end
    local parts = {}
    for ra, g in pairs(glyphs) do
        parts[#parts + 1] = string.format('ra=%08x n=%d x %d..%d y %d..%d', ra, g.n, g.x0, g.x1, g.y0, g.y1)
    end
    if #parts > 0 then L.say('GSUM f=%d %s', f, table.concat(parts, ' | ')) end
    glyphs, printed = {}, 0
end)
