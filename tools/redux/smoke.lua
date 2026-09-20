--[[ Headless boot gate for PCSX-Redux, and the worked example of driving it from Lua.

     Boots whatever image the launcher handed the emulator, lets a fixed number of frames
     run, reads CPU state and main RAM, and exits with a status a shell can branch on.
     No window, no keyboard, no human. Run it through tools/redux/run-headless.sh, which
     supplies the flags this file assumes. `PCSX.quit(n)` only ends the process under
     -testmode; without it the emulator keeps running and the gate hangs forever.

     Exit codes, deliberately distinct — a gate that cannot say WHICH way it failed is
     half a gate:
       0  reached the target frame and the game's own code was executing
       3  the target frame arrived but the PC was not in the executable's range
       4  the PC was in range but the instruction stream under it was all zero
       5  main RAM does not hold the executable — the BIOS shell is still running, or
          the disc booted something else
       6  no expected bytes were supplied, so 5 could not be decided
     (2)  a hang. Not produced here: run-headless.sh owns the wall clock, because an
          in-emulator watchdog cannot be relied on when the emulator is what wedged.

     Copy this file for new checks rather than re-deriving the API; the three things an
     agent with no display needs are all here — advance emulation (GPU::Vsync), read RAM
     (getMemPtr), stop on an address (addBreakpoint, which needs -debugger).
--]]

-- Boku no Natsuyasumi spends its first seconds in logos and a CD load, and the BIOS SHELL
-- runs from RAM at 0x8003xxxx-0x8005xxxx meanwhile — inside the range the game will later
-- occupy, and across the executable's own entry address, which the PC crosses from frame
-- ~90 in shell code. The BIOS copies the executable in at frame ~720 and the real entry is
-- reached at ~835 (measured: research/renderer-runtime.md § Q0). So no frame count and no
-- PC test tells the game from the shell; only the EXE's bytes being in RAM does, which is
-- what BOKU_EXE_SAMPLES below is for. The default target is past the load as well, so that
-- a run whose samples are somehow absent is not also sitting in the logos.

-- A typo'd env var must fail loudly here, not as a nil address or a nil comparison
-- somewhere inside a callback where the only symptom is a hang.
local function numenv(name, default)
    local raw = os.getenv(name) or default
    local n = tonumber(raw)
    assert(n, name .. " must be a number, got '" .. tostring(raw) .. "'")
    return n
end

local TARGET_FRAME = numenv('BOKU_FRAMES', '1000')

-- "ADDR:HEXBYTES ADDR:HEXBYTES ..." — run-headless.sh reads them out of the executable on
-- disc at launch. They are never written into this file: the repo ships no byte of the
-- original (CLAUDE.md § "This repo is public and contains none of the original game").
local function parse_samples(spec)
    local out = {}
    for addr, bytes in spec:gmatch('(%x+):(%x+)') do
        assert(#bytes % 2 == 0, 'BOKU_EXE_SAMPLES: odd hex run at ' .. addr)
        out[#out + 1] = { addr = tonumber(addr, 16), bytes = bytes:lower() }
    end
    return out
end

local SAMPLES = parse_samples(os.getenv('BOKU_EXE_SAMPLES') or '')

-- From the PS-X EXE header of SCPS_100.88: t_addr 0x80010000, t_size 0x7f800.
local TEXT_START = 0x80010000
local TEXT_END = 0x8008f800

-- psyouloveme/boku1-reversing's RAM map for the PS1 original calls this byte GameMode.
-- Reported, never asserted on: this gate has not confirmed the address, and asserting on
-- an unverified byte that happens to read 0 is how a gate goes quietly vacuous.
local GAMEMODE_ADDR = 0x800237e0

-- Set BOKU_BREAK=0x800588a8 to demonstrate an execution breakpoint. Requires -debugger:
-- measured 2026-09-20, without that flag addBreakpoint returns an object and the
-- breakpoint simply never fires, including at an address the PC was observed to hold.
local BREAK_AT = numenv('BOKU_BREAK', '0')

local frames = 0
local finished = false

-- Redux drops a breakpoint or listener whose Lua object is garbage-collected, so these
-- references are load-bearing, not tidiness.
local keep = {}

-- Main RAM is a flat 2 MB buffer and every KUSEG/KSEG0/KSEG1 alias folds onto it, which
-- is why the mask works — and also why this function must refuse anything else. Masking
-- is silently WRONG outside main RAM: 0x1f801814 (GPUSTAT) would return the byte at RAM
-- offset 0x1814, and both 0x1f800000 (scratchpad) and 0xbfc00000 (BIOS ROM) fold to
-- offset 0. Each returns plausible bytes and no error, so the caller cannot tell.
local RAM_SIZE = 0x200000

local function inMainRAM(addr)
    for _, base in ipairs({ 0x00000000, 0x80000000, 0xa0000000 }) do
        if addr >= base and addr < base + RAM_SIZE then return true end
    end
    return false
end

local function readRAM(addr, count)
    assert(inMainRAM(addr),
        string.format('readRAM: 0x%08x is not main RAM; masking it would read the ' ..
            'wrong byte and say nothing', addr))
    local base = bit.band(addr, RAM_SIZE - 1)
    assert(base + count <= RAM_SIZE,
        string.format('readRAM: %d bytes from 0x%08x runs off the end of main RAM',
            count, addr))
    local mem = PCSX.getMemPtr()
    local out = {}
    for i = 0, count - 1 do
        out[i + 1] = mem[base + i]
    end
    return out
end

local function say(fmt, ...)
    print(string.format('SMOKE ' .. fmt, ...))
end

local function hex(bytes)
    local t = {}
    for i = 1, #bytes do t[i] = string.format('%02x', bytes[i]) end
    return table.concat(t, ' ')
end

local function finish(code, why)
    if finished then return end
    finished = true
    say('exit=%d %s', code, why)
    PCSX.quit(code)
end

local function report()
    if finished then return end
    local regs = PCSX.getRegisters()
    local pc = regs.pc
    say('frames=%d cycles=%d', frames, PCSX.getCPUCycles())
    say('pc=0x%08x ra=0x%08x sp=0x%08x', pc, regs.GPR.n.ra, regs.GPR.n.sp)
    say('gamemode[0x%08x]=0x%02x (address unconfirmed, reported only)',
        GAMEMODE_ADDR, readRAM(GAMEMODE_ADDR, 1)[1])

    -- The assertion that decides game-or-shell, and the reason this gate cannot pass on
    -- BIOS code: the shell occupies the same addresses but not the same bytes.
    for _, s in ipairs(SAMPLES) do
        local got = (hex(readRAM(s.addr, #s.bytes / 2)):gsub(' ', ''))
        if got ~= s.bytes then
            say('ram @0x%08x = %s', s.addr, got)
            say('file        = %s', s.bytes)
            finish(5, 'main RAM does not hold the executable — this is not the game')
            return
        end
    end
    say('exe bytes match the file at %d sampled offsets', #SAMPLES)

    -- The second assertion. If the disc fails to boot, the PC stays in BIOS ROM at 0xbfc0xxxx
    -- or in kernel RAM below 0x80010000, and this is what notices. Verified red on
    -- purpose at BOKU_FRAMES=1, where the BIOS has not yet handed over.
    if pc < TEXT_START or pc >= TEXT_END then
        say('pc is outside the executable range 0x%08x..0x%08x', TEXT_START, TEXT_END)
        finish(3, 'the game\'s own code was not executing')
        return
    end

    -- A PC inside the range with nothing but zeroes under it would mean we are running
    -- off the end of a cleared region, which the range check alone cannot see.
    local at_pc = readRAM(pc, 8)
    say('ram@pc = %s', hex(at_pc))
    local nonzero = 0
    for i = 1, #at_pc do
        if at_pc[i] ~= 0 then nonzero = nonzero + 1 end
    end
    if nonzero == 0 then
        finish(4, 'the instruction stream at the PC is all zero')
        return
    end

    finish(0, 'ok')
end

if BREAK_AT ~= 0 then
    keep[#keep + 1] = PCSX.addBreakpoint(BREAK_AT, 'Exec', 4, 'boku smoke probe', function()
        say('breakpoint-hit 0x%08x frame=%d', BREAK_AT, frames)
        -- Returning false removes the breakpoint. Returning true keeps it armed and, in
        -- a paused-then-resumed loop, re-fires on the same instruction forever.
        return false
    end)
    say('breakpoint armed at 0x%08x (needs -debugger)', BREAK_AT)
end

keep[#keep + 1] = PCSX.Events.createEventListener('GPU::Vsync', function()
    frames = frames + 1
    -- Reported on the first frame rather than after the target, so a gate that has been
    -- disarmed by a missing environment cannot spend a minute looking like it is working.
    if #SAMPLES == 0 then
        finish(6, 'BOKU_EXE_SAMPLES is empty; without the file\'s bytes this gate cannot ' ..
            'tell the game from the BIOS shell. Launch through run-headless.sh.')
    elseif frames >= TARGET_FRAME then
        report()
    end
end)

say('armed target-frame=%d exe-samples=%d', TARGET_FRAME, #SAMPLES)
