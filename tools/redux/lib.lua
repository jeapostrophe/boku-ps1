--[[ Shared helpers for the headless PCSX-Redux scripts in this directory.

     Load with:  local L = dofile(os.getenv('BOKU_REDUX_DIR') .. '/lib.lua')
     (tools/redux/run-txt01.sh exports BOKU_REDUX_DIR, BOKU_REPO and BOKU_WORK.)

     API facts used here were read from the emulator's source at the commit of the
     installed build (e3e051ca: src/core/pcsxffi.lua, src/core/pad.cc), not from memory.
--]]

local M = {}
local ffi = require 'ffi'

M.RAM_SIZE = 0x200000
M.repo = os.getenv('BOKU_REPO') or '.'
M.work = os.getenv('BOKU_WORK') or (M.repo .. '/work/txt01-emu')

function M.numenv(name, default)
    local raw = os.getenv(name) or default
    local n = tonumber(raw)
    assert(n, name .. " must be a number, got '" .. tostring(raw) .. "'")
    return n
end

function M.say(fmt, ...) print(string.format(fmt, ...)) end

-- Main RAM only; see smoke.lua for why masking any other address is silently wrong.
local function off(addr, count)
    local seg = bit.rshift(addr, 28)
    local phys = bit.band(addr, 0x1fffffff)
    assert((seg == 0 or seg == 8 or seg == 0xa) and phys + (count or 1) <= M.RAM_SIZE,
        string.format('0x%08x is not main RAM', addr))
    return phys
end

function M.mem() return PCSX.getMemPtr() end
function M.r8(a) return M.mem()[off(a, 1)] end
function M.r16(a) local m, o = M.mem(), off(a, 2); return m[o] + m[o + 1] * 256 end
function M.rs16(a) local v = M.r16(a); if v >= 0x8000 then v = v - 0x10000 end; return v end
function M.r32(a)
    local m, o = M.mem(), off(a, 4)
    return m[o] + m[o + 1] * 256 + m[o + 2] * 65536 + m[o + 3] * 16777216
end
function M.w8(a, v) M.mem()[off(a, 1)] = v end
function M.w16(a, v)
    local m, o = M.mem(), off(a, 2)
    m[o] = bit.band(v, 0xff); m[o + 1] = bit.band(bit.rshift(v, 8), 0xff)
end
function M.w32(a, v)
    M.w16(a, bit.band(v, 0xffff)); M.w16(a + 2, bit.band(bit.rshift(v, 16), 0xffff))
end
function M.rbytes(a, n) return ffi.string(M.mem() + off(a, n), n) end

-- Code pokes must be followed by this or a cached decode may keep running the old word.
function M.poke_code(a, v) M.w32(a, v); PCSX.invalidateCache() end

function M.write_file(path, data)
    local f = assert(io.open(path, 'wb'), 'cannot write ' .. path)
    f:write(data); f:close()
end

function M.read_file(path)
    local f = assert(io.open(path, 'rb'), 'cannot read ' .. path)
    local d = f:read('*a'); f:close(); return d
end

-- Framebuffer → <work>/shots/<name>.raw with a 16-byte header "BOKUSHOT" w h bpp(16|24) 0,
-- all u16 LE. tools/redux/shot2png.py converts. The raw 15-bit words are the game's
-- pixels, so these never leave work/.
function M.shot(name)
    local s = PCSX.GPU.takeScreenShot()
    local bpp = (tonumber(s.bpp) == 0) and 16 or 24
    local hdr = 'BOKUSHOT' .. string.char(
        s.width % 256, math.floor(s.width / 256), s.height % 256, math.floor(s.height / 256),
        bpp, 0, 0, 0)
    local path = M.work .. '/shots/' .. name .. '.raw'
    local f = Support.File.open(path, 'TRUNCATE')
    f:write(hdr)
    f:writeMoveSlice(s.data)
    f:close()
    return path
end

-- Save state → file: the raw protobuf createSaveState returns; loadSaveState accepts
-- the same bytes back as a File.
function M.save_state(name)
    local slice = PCSX.createSaveState()
    local path = M.work .. '/states/' .. name .. '.sstate'
    local f = Support.File.open(path, 'TRUNCATE')
    f:writeMoveSlice(slice)
    f:close()
    return path
end

function M.load_state(name)
    local path = M.work .. '/states/' .. name .. '.sstate'
    local f = Support.File.open(path, 'READ')
    assert(not f:failed(), 'no save state at ' .. path)
    PCSX.loadSaveState(f)
    f:close()
end

-- Pad 1. Button numbers from pad.cc's setLua: a set override forces the button DOWN.
M.BTN = PCSX.CONSTS.PAD.BUTTON
local pad = PCSX.SIO0.slots[1].pads[1]
function M.press(b) pad.setOverride(b) end
function M.release(b) pad.clearOverride(b) end
function M.release_all() for _, b in pairs(M.BTN) do pad.clearOverride(b) end end

-- Frame scheduler: M.on_frame(fn) is called with the frame number every vsync;
-- M.script{ {frame, fn}, ... } runs fn once at that frame.
M.frame = 0
local listeners, keep = {}, {}
M.keep = keep
function M.on_frame(fn) listeners[#listeners + 1] = fn end
keep[#keep + 1] = PCSX.Events.createEventListener('GPU::Vsync', function()
    M.frame = M.frame + 1
    for i = 1, #listeners do listeners[i](M.frame) end
end)

function M.bp(addr, kind, width, label, fn)
    local b = PCSX.addBreakpoint(addr, kind, width, label, fn)
    keep[#keep + 1] = b
    return b
end

local finished = false
function M.finish(code, why)
    if finished then return end
    finished = true
    M.release_all()
    M.say('EXIT %d %s', code, why or '')
    PCSX.quit(code)
end

return M
