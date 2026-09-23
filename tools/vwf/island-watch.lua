--[[ BOKU_POKES file for drive.lua (tools/vwf/shoot-menus.sh sets it under ISLAND_WATCH=1):
     an execution breakpoint over the walker island, and a control breakpoint on glyph_draw so
     that a run in which neither fires is visible as broken rather than read as "dead".

     BOKU_ISLAND_RANGE "start,end" in hex -- shoot-menus.sh reads both from asm/vwf.asm's
     DEBUG_FONT_ISLAND equates, which are their one home. Breakpoints need Redux's -debugger,
     which run-headless.sh passes.
--]]
local L = ...
local s, e = string.match(os.getenv('BOKU_ISLAND_RANGE') or '', '^(%x+),(%x+)$')
assert(s, 'BOKU_ISLAND_RANGE is "start,end" in hex')
local start, length = tonumber(s, 16), tonumber(e, 16) - tonumber(s, 16)
local hits, control = 0, 0
L.bp(start, 'Exec', length, 'walker-island', function()
    hits = hits + 1
    local r = PCSX.getRegisters()
    if hits <= 5 then
        L.say('ISLAND hit %d f=%d pc=%08x ra=%08x', hits, L.frame, tonumber(r.pc) or -1, r.GPR.n.ra)
    end
    return true
end)
L.bp(0x8002BA2C, 'Exec', 4, 'glyph_draw', function()
    control = control + 1
    if control == 1 or control % 10000 == 0 then
        L.say('ISLAND control: glyph_draw hit %d f=%d', control, L.frame)
    end
    return true
end)
L.say('ISLAND watching %08x +%x', start, length)
