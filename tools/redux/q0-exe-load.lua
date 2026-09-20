--[[ Q0 (research/text-renderer.md § 8): is SCPS_100.88 identity-loaded at 0x80010000?

     Polls every frame until RAM[0x80010000 + k] equals the file's bytes at 0x800 + k
     for a probe window inside .text (glyph_draw, 0x8002BA2C), reports that frame, then
     compares the WHOLE loaded range 0x80010000..0x8008F7FF against the file a little
     later and classifies every mismatching byte by region. Also logs each time the PC
     reaches the header's entry point, with the 8 bytes under it, so a too-early hit in
     BIOS-shell code that happens to live at the same address is visible as such.

     Env: BOKU_EXE (default disc/files/SCPS_100.88), BOKU_FRAMES (give up after; 3000),
          BOKU_SETTLE (frames after load before the full compare; 120).
--]]
local L = dofile(os.getenv('BOKU_REDUX_DIR') .. '/lib.lua')
local exe = L.read_file(os.getenv('BOKU_EXE') or (L.repo .. '/disc/files/SCPS_100.88'))
local LIMIT = L.numenv('BOKU_FRAMES', '3000')
local SETTLE = L.numenv('BOKU_SETTLE', '120')
local T_ADDR, T_SIZE, HDR, ENTRY = 0x80010000, 0x7f800, 0x800, 0x80049154
assert(#exe == HDR + T_SIZE, 'unexpected EXE size ' .. #exe)

local function matches(addr, n)
    return L.rbytes(addr, n) == exe:sub(addr - T_ADDR + HDR + 1, addr - T_ADDR + HDR + n)
end

local t0 = os.clock()
local loaded_at
local entry_hits, entry_hits_bios = 0, 0
L.bp(ENTRY, 'Exec', 4, 'entry', function()
    -- The BIOS shell has a hot loop through this same address, so hits are counted and
    -- only the first few of each kind are printed.
    local real = matches(ENTRY, 64)
    if real then entry_hits = entry_hits + 1 else entry_hits_bios = entry_hits_bios + 1 end
    if (real and entry_hits > 3) or (not real and entry_hits_bios > 3) then return true end
    L.say('Q0 pc==entry at frame %d; ram there = %s; file-match(64 bytes)=%s', L.frame,
        (L.rbytes(ENTRY, 8):gsub('.', function(c) return string.format('%02x ', c:byte()) end)),
        tostring(matches(ENTRY, 64)))
    return true
end)

local function full_compare()
    local ram = L.rbytes(T_ADDR, T_SIZE)
    local file = exe:sub(HDR + 1)
    -- regions per research/text-renderer.md § 6
    local regions = {
        { 'image  0x80010000-0x80072670', 0x80010000, 0x80072670 },
        { 'bss    0x80072670-0x80079A08', 0x80072670, 0x80079A08 },
        { 'ovl    0x80079A08-0x8008F3A4', 0x80079A08, 0x8008F3A4 },
        { 'heap   0x8008F3A4-0x8008F800', 0x8008F3A4, 0x8008F800 },
    }
    local counts, runs = {}, {}
    local run_start
    for i = 1, T_SIZE do
        local a = T_ADDR + i - 1
        if ram:byte(i) ~= file:byte(i) then
            for _, r in ipairs(regions) do
                if a >= r[2] and a < r[3] then counts[r[1]] = (counts[r[1]] or 0) + 1 end
            end
            if not run_start then run_start = a end
        elseif run_start then
            runs[#runs + 1] = { run_start, a }; run_start = nil
        end
    end
    if run_start then runs[#runs + 1] = { run_start, T_ADDR + T_SIZE } end
    for _, r in ipairs(regions) do L.say('Q0 mismatching bytes in %s: %d', r[1], counts[r[1]] or 0) end
    -- coalesce runs closer than 16 bytes, list those inside the image
    local merged = {}
    for _, r in ipairs(runs) do
        local last = merged[#merged]
        if last and r[1] - last[2] < 16 then last[2] = r[2] else merged[#merged + 1] = { r[1], r[2] } end
    end
    local shown = 0
    for _, r in ipairs(merged) do
        if r[1] < 0x80072670 then
            shown = shown + 1
            if shown <= 60 then L.say('Q0   image mismatch 0x%08x..0x%08x (%d bytes)', r[1], r[2], r[2] - r[1]) end
        end
    end
    L.say('Q0 image mismatch runs: %d', shown)
    L.say('Q0 glyph_draw @0x8002BA2C = %s (spec expects 21 38 80 00)',
        (L.rbytes(0x8002BA2C, 4):gsub('.', function(c) return string.format('%02x ', c:byte()) end)))
end

L.on_frame(function(f)
    if f % 100 == 0 then
        L.say('Q0 frame %d pc=0x%08x %.1f fps(cpu-clock)', f, PCSX.getRegisters().pc, f / (os.clock() - t0))
    end
    if not loaded_at then
        if matches(0x8002BA2C, 256) and matches(0x80010000, 256) then
            loaded_at = f
            L.say('Q0 EXE bytes present in RAM at frame %d (pc=0x%08x)', f, PCSX.getRegisters().pc)
        elseif f >= LIMIT then
            L.say('Q0 EXE never appeared in %d frames', f)
            L.say('Q0 ram@0x80010000: %s', (L.rbytes(0x80010000, 16):gsub('.', function(c) return string.format('%02x ', c:byte()) end)))
            L.finish(3, 'not loaded')
        end
    elseif f == loaded_at + SETTLE then
        full_compare()
        L.say('Q0 entry-address hits: %d with the EXE under the PC, %d with something else (BIOS shell)',
            entry_hits, entry_hits_bios)
        L.finish(0, 'ok')
    end
end)
L.say('Q0 armed')
