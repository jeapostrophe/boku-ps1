--[[ The TXT-04 trial applied to RAM only (research/text-renderer.md § 7) — for
     drive.lua's BOKU_POKES. No disc image is touched; the pokes die with the process.

     Env:
       BOKU_TRIAL   comma list of
                      horiz   msg_open passes (24, 132, horizontal) to dialog_open
                      band    the dialogue strip becomes the lower half of the screen
                      band2   instead: a band with INDEPENDENT top and height and still no new
                              instruction slots — x is stored as the constant 0, which
                              frees the slot that computed it to load y (BOKU_BAND_Y,
                              BOKU_BAND_H; defaults 168, 72)
                      arrow   the next-page arrow moves into the band (BOKU_ARROW_X/Y)
                      hello   the CURRENT event's message BOKU_HELLO_MSG (default 0) is
                              overwritten with "Hello, Boku!" in the font's full-width Latin
       BOKU_BAND_LEVEL    copy g_dlgbox_fade[n] over entry 6, the level msg_open raises the
                          panel to (6 is the only opaque one; 0..5 are semi-transparent)
       BOKU_X0, BOKU_Y0   pen origin for `horiz` (defaults 24, 132)
       BOKU_PITCH         glyph advance for horizontal text (default: leave 14)

     Every code poke asserts the word it replaces, so a wrong address or a different
     build fails loudly instead of corrupting the run.
--]]
local L = ...
local want = {}
for w in (os.getenv('BOKU_TRIAL') or 'horiz,band'):gmatch('[^,]+') do want[w] = true end

local function addiu(rt, imm) return 0x24000000 + rt * 65536 + bit.band(imm, 0xffff) end
local function patch(addr, old, new, what)
    local cur = L.r32(addr)
    assert(cur == old, string.format('%s: 0x%08x holds %08x, expected %08x', what, addr, cur, old))
    L.w32(addr, new)
    L.say('POKE %s: %08x: %08x -> %08x', what, addr, old, new)
end

if want.horiz then
    patch(0x8002CFC4, 0x24040129, addiu(4, L.numenv('BOKU_X0', '24')), 'msg_open x')
    patch(0x8002CFC8, 0x24050016, addiu(5, L.numenv('BOKU_Y0', '132')), 'msg_open y')
    patch(0x8002CFCC, 0x24060001, addiu(6, 0), 'msg_open vertical')
end
local pitch = os.getenv('BOKU_PITCH')
if pitch then
    patch(0x8002BF7C, 0x2652000E, 0x26520000 + tonumber(pitch), 'dialog_draw horizontal advance')
end
if want.band then
    assert(L.r16(0x8002911C) == 260, 'g_dlgbox_x is not 260')
    L.w16(0x8002911C, 0xFFFB)
    L.say('POKE g_dlgbox_x: 260 -> -5')
    patch(0x8002EA34, 0x241100F0, addiu(17, L.numenv('BOKU_BAND_Y', '120')), 'dialog_panel_draw s1 (y and h)')
    patch(0x8002EA38, 0xA600000A, 0xA611000A, 'dialog_panel_draw tile y')
end
if want.band2 then
    assert(L.r16(0x8002911C) == 260, 'g_dlgbox_x is not 260')
    L.w16(0x8002911C, 0xFFFB) -- w = 0x145 - x = 330 (clipped); the 5 px fade lands off-screen
    L.say('POKE g_dlgbox_x: 260 -> -5')
    patch(0x8002EA34, 0x241100F0, addiu(17, L.numenv('BOKU_BAND_H', '72')), 'dialog_panel_draw s1 (h)')
    patch(0x8002EA38, 0xA600000A, 0xA6000008, 'dialog_panel_draw: sh zero,8(s0) — tile x = 0')
    patch(0x8002EA44, 0x24620005, addiu(2, L.numenv('BOKU_BAND_Y', '168')), 'dialog_panel_draw: v0 = y')
    patch(0x8002EA48, 0xA6020008, 0xA602000A, 'dialog_panel_draw: sh v0,10(s0) — tile y')
end
local level = os.getenv('BOKU_BAND_LEVEL')
if level then
    local t = 0x80029120
    for i = 0, 6 do L.say('POKE g_dlgbox_fade[%d] = brightness %d, abr+1 %d', i, L.rs16(t + 4 * i), L.rs16(t + 4 * i + 2)) end
    local n = tonumber(level)
    L.w16(t + 24, L.r16(t + 4 * n)); L.w16(t + 26, L.r16(t + 4 * n + 2))
end
if want.arrow then
    -- dialog_cursor_draw: addiu s1,s1,0x10A / y literals 0xDC, 0xDF. The registers are
    -- read back from the words themselves so only the immediates change.
    local ax, ay = L.numenv('BOKU_ARROW_X', '296'), L.numenv('BOKU_ARROW_Y', '222')
    for _, p in ipairs({ { 0x8002C078, 0x010A, ax }, { 0x8002C088, 0x00DC, ay }, { 0x8002C0E8, 0x00DF, ay + 3 } }) do
        local cur = L.r32(p[1])
        assert(bit.band(cur, 0xffff) == p[2], string.format('arrow literal at %08x is %08x', p[1], cur))
        L.w32(p[1], bit.bor(bit.band(cur, 0xffff0000), p[3]))
        L.say('POKE arrow %08x: %04x -> %04x', p[1], p[2], p[3])
    end
end
if want.hello then
    local msg = L.numenv('BOKU_HELLO_MSG', '0')
    local block = L.r32(0x80036338)
    assert(block >= 0x80010000 and block < 0x80200000, 'no current event block (g_ev_block)')
    local off = L.r32(block + 0x14 + 8 * msg)
    assert(off ~= 0, 'that message has no text')
    local text = block + off
    -- Ｈ ｅ ｌ ｌ ｏ ， space Ｂ ｏ ｋ ｕ ！ END — ids from research/data/glyph-table.tsv
    local words = { 0x45, 0x5C, 0x63, 0x63, 0x66, 0x03, 0x00, 0x3F, 0x66, 0x62, 0x6C, 0x09, 0x8000 }
    for i, w in ipairs(words) do L.w16(text + 2 * (i - 1), w) end
    L.say('POKE hello: %d words at %08x (block %08x msg %d)', #words, text, block, msg)
end
PCSX.invalidateCache()
