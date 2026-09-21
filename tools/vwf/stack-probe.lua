--[[ How deep does the stack go, and how high does the level-C arena reach?

     A BOKU_POKES file for tools/redux/drive.lua (or tools/vwf/reach-select.lua): it runs
     once, right after the state loads, and answers the two questions that bound how far
     the map work area may be raised (asm/arena.asm; research/loading-and-memory.md
     § "Making room" 1-2): the fixed arena ends at *g_arena_lvl_c, bg_swap_in scratches
     0x6000 bytes above that, and the stack grows down from 0x801FFFF0 -- every byte the
     work area grows costs two of the gap between the two.

     Method: fill [FILL_LO, sp - GUARD) with a sentinel at load, sample sp and g_arena_cur
     every vsync, and at the last frame report the lowest sentinel byte that was
     overwritten (the stack's low-water mark), the lowest sp seen at a vsync, and the
     highest g_arena_cur. FILL_LO sits above where the scratch can reach, so nothing but
     the stack can disturb the fill.

     Env: BOKU_PROBE_FRAMES = the frame to report at (default: BOKU_FRAMES - 1, i.e. just
     before the driver quits). Output lines start with STACK.
--]]
local L = ...
local SENTINEL = 0xEE
local GUARD = 0x400                   -- bytes under the live sp left untouched (interrupt frames)
local STACK_TOP = 0x801FFFF0
local G_ARENA_CUR = 0x800258E0
local G_ARENA_LVL_C = 0x800258FC
-- bg_swap_in's StoreImage scratch reaches level C + 0x6000, and level C moves with every
-- arena raise (asm/arena.asm), so the window starts where the live layout says, not at a
-- literal that a later raise would silently put inside the scratch.
local FILL_LO = L.r32(G_ARENA_LVL_C) + 0x6000

local sp0 = PCSX.getRegisters().GPR.n.sp
local fill_hi = sp0 - GUARD
assert(fill_hi > FILL_LO, string.format('sp %08x is already below the fill window', sp0))
local mem = L.mem()
for a = FILL_LO, fill_hi - 1 do mem[a - 0x80000000] = SENTINEL end
L.say('STACK filled %08x..%08x (sp at load %08x, arena level C %08x, arena cur %08x)',
    FILL_LO, fill_hi, sp0, L.r32(G_ARENA_LVL_C), L.r32(G_ARENA_CUR))

local frames = L.numenv('BOKU_PROBE_FRAMES', tostring(L.numenv('BOKU_FRAMES', '600') - 1))
local sp_min, cur_max = sp0, L.r32(G_ARENA_CUR)
local reported = false
L.on_frame(function(f)
    local sp = PCSX.getRegisters().GPR.n.sp
    if sp < sp_min then sp_min = sp end
    local cur = L.r32(G_ARENA_CUR)
    if cur > cur_max then cur_max = cur end
    if f >= frames and not reported then
        reported = true
        local low = fill_hi
        local m = L.mem()
        for a = FILL_LO, fill_hi - 1 do
            if m[a - 0x80000000] ~= SENTINEL then low = a; break end
        end
        L.say('STACK low-water %08x (depth %d bytes from %08x); sp min at vsync %08x; '
            .. 'arena cur max %08x (level C %08x, +%d); gap left %d bytes',
            low, STACK_TOP - low, STACK_TOP, sp_min, cur_max, L.r32(G_ARENA_LVL_C),
            cur_max - L.r32(G_ARENA_LVL_C), low - (L.r32(G_ARENA_LVL_C) + 0x6000))
    end
end)
