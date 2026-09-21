--[[ What sits in the low ordering-table slots while a message is up.

     A BOKU_POKES file for tools/redux/drive.lua: at BOKU_OT_FRAME (default 30) it walks
     slots 0..BOKU_OT_SLOTS-1 of BOTH ordering tables -- the pair at 0x80025948 and
     0x8002594C, of which *0x8002593C is the one being built this frame (the frame-flip code
     at 0x80012750-88 alternates them) -- and prints every primitive: its length byte, code
     byte, the first x, y after the colour word, and its words. Reversed tables: a slot's
     entry links to its last-added primitive, that to the one before, and the last one on
     to the next lower slot's entry; an entry that links straight to another entry is an
     empty slot. Output lines start with OT.
--]]
local L = ...
local G_OT_CURRENT, G_OT_PAIR = 0x8002593C, 0x80025948
local OT_ENTRIES = 0x2000
local frame_at = L.numenv('BOKU_OT_FRAME', '30')
local slots = L.numenv('BOKU_OT_SLOTS', '4')
local done = false

local function in_table(link, base)
    return link >= base and link < base + 4 * OT_ENTRIES
end

local function walk(base, slot)
    local entry = base + 4 * slot
    local link = L.r32(entry) % 0x1000000
    if in_table(link + 0x80000000, base) or link == 0xFFFFFF then
        L.say('OT slot %d empty (links to %s)', slot,
            link == 0xFFFFFF and 'the terminator' or string.format('entry %08x', link + 0x80000000))
        return
    end
    local n = 0
    while true do
        local addr = link + 0x80000000
        local tag = L.r32(addr)
        local len = math.floor(tag / 0x1000000)
        local code = L.r8(addr + 7)
        local words = {}
        for i = 1, math.min(len, 8) do words[#words + 1] = string.format('%08x', L.r32(addr + 4 * i)) end
        L.say('OT slot %d prim %d @%08x len %d code %02x xy (%d,%d) words %s', slot, n, addr, len, code,
            L.rs16(addr + 8), L.rs16(addr + 10), table.concat(words, ' '))
        n = n + 1
        link = tag % 0x1000000
        if link == 0xFFFFFF then L.say('OT slot %d ends at the terminator', slot); return end
        if in_table(link + 0x80000000, base) then
            L.say('OT slot %d ends -> entry %08x (%d primitives)', slot, link + 0x80000000, n); return
        end
    end
end

L.on_frame(function(f)
    if f >= frame_at and not done then
        done = true
        local current = L.r32(G_OT_CURRENT)
        L.shot('ot-frame')
        for t = 0, 1 do
            local base = L.r32(G_OT_PAIR + 4 * t)
            L.say('OT table %d at %08x%s', t, base, base == current and ' (current: being built this frame)' or '')
            for s = 0, slots - 1 do walk(base, s) end
        end
    end
end)
