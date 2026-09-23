--[[ BOKU_POKES file for drive.lua: write memory on given frames, nothing else.

     BOKU_W32  "frame:0xADDR=value,..." -- value decimal or 0x-hex; a 32-bit write each.
     BOKU_W8   the same, one byte each (a flag whose neighbours must survive).
     (tools/redux/book-pokes.lua has the same option, but also forces a mode.)
--]]
local L = ...
local writes = {}
for _, spec in ipairs({ { 'BOKU_W32', L.w32 }, { 'BOKU_W8', L.w8 } }) do
    for f, a, v in (os.getenv(spec[1]) or ''):gmatch('(%d+):(0x%x+)=(%w+)') do
        f = tonumber(f); writes[f] = writes[f] or {}
        table.insert(writes[f], { spec[2], tonumber(a), tonumber(v) })
    end
end
L.on_frame(function(f)
    for _, w in ipairs(writes[f] or {}) do
        w[1](w[2], w[3]); L.say('POKE f=%d [%08x] = %d', f, w[2], w[3])
    end
end)
