--[[ BOKU_POKES file for drive.lua: does loading one overlay overwrite a RAM range the patch
     keeps resident? (research/text-renderer.md § 6, "The overlay region's whole-sector reads")

     From BOKU_AFTER on, at the next entry of glyph_draw -- a plain call on the main thread,
     where only a0-a3 and ra are live -- the script snapshots the watched range and fills it
     with a sentinel (so a load writing a byte's own value back still shows), poisons the
     word at g_overlay_base, then makes the CPU call file_load(BOKU_OVERLAY, *g_overlay_base)
     and return to glyph_draw's entry. On that return it counts sentinel bytes that changed,
     checks the overlay's first word replaced the poison (the control: a load that never
     happened would read as "untouched"), and quits: 0 untouched, 1 overwritten, 2 the load
     did not happen. The overlay replaced whatever the caller was running, so the run ends.

       BOKU_OVERLAY       g_cd_dir index to load (MUSI.OVL is 129)
       BOKU_WATCH_RANGE   "start,end" in hex
       BOKU_OVERLAY_WORD  the overlay file's first u32, hex (the caller reads it off the import)
       BOKU_AFTER         first frame to act on (default 3000: the title screen)
--]]
local L = ...
local FILE_LOAD, GLYPH_DRAW, OVERLAY_BASE_PTR = 0x800129E0, 0x8002BA2C, 0x80068AF4
local SENTINEL, POISON = 0xA5, 0x5AFEC0DE
local index = L.numenv('BOKU_OVERLAY', '129')
local after = L.numenv('BOKU_AFTER', '3000')
local first_word = tonumber(os.getenv('BOKU_OVERLAY_WORD') or '', 16)
assert(first_word, 'BOKU_OVERLAY_WORD is the overlay file\'s first u32 in hex')
local s, e = string.match(os.getenv('BOKU_WATCH_RANGE') or '', '^(%x+),(%x+)$')
assert(s, 'BOKU_WATCH_RANGE is "start,end" in hex')
local start, stop = tonumber(s, 16), tonumber(e, 16)

local state = 'wait'
L.bp(GLYPH_DRAW, 'Exec', 4, 'glyph_draw', function()
    local r = PCSX.getRegisters()
    if state == 'wait' and L.frame >= after then
        local base = L.r32(OVERLAY_BASE_PTR)
        for a = start, stop - 1 do L.w8(a, SENTINEL) end
        L.w32(base, POISON)
        PCSX.invalidateCache()
        L.say('OVERRUN f=%d calling file_load(%d, %08x); watching %08x-%08x', L.frame, index,
            base, start, stop)
        local n = r.GPR.n
        n.a0, n.a1, n.ra = index, base, GLYPH_DRAW
        r.pc = FILE_LOAD
        state = 'loading'
    elseif state == 'loading' then
        state = 'done'
        local after_bytes = L.rbytes(start, stop - start)
        local changed = 0
        for i = 1, #after_bytes do
            if after_bytes:byte(i) ~= SENTINEL then changed = changed + 1 end
        end
        local landed = L.r32(L.r32(OVERLAY_BASE_PTR))
        L.say('OVERRUN overlay first word %08x (want %08x); %d of %d watched bytes changed',
            landed, first_word, changed, #after_bytes)
        if landed ~= first_word then L.finish(2, 'the overlay did not load') end
        L.finish(changed == 0 and 0 or 1, changed == 0 and 'untouched' or 'overwritten')
    end
    return true
end)
L.say('OVERRUN armed: overlay %d from frame %d', index, after)
