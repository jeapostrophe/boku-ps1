--[[ Read-only probes of the game's state, shared by the TXT-01 scripts. Addresses are
     research/symbols/text-renderer.symbols.tsv and research/event-scripts.md; nothing
     here writes to RAM. Returns a constructor taking lib.lua's table.

     BOKU_PROBE selects breakpoints: a comma list of
       dialog   dialog_open / msg_open / event_begin arguments
       dbg      exec-watch dbg_vprintf and dbg_printf (Q6)
       heap     write-watch 0x8008F3A4..0x8008F7FF (Q5), armed at once. From a cold boot
                this MUST hit (the BIOS loads the file's zeros there and main() clears from
                g_heap_base) — that is the red run showing the watch can fire
       heapraise  cold boot only: when the PC first reaches the EXE's entry with the EXE
                under it, set g_heap_base = 0x8008F800, fill the gap with a sentinel, and
                only then arm the write-watch. report() re-reads the sentinel, which does
                not depend on the breakpoint machinery
       prim     per-frame primitive-buffer use, peak (Q4)
       voice    g_text_wait / g_voice_active transitions (Q7)
       pad      every change of the game's pad word at 0x80072766 (Q9)
--]]
return function(L)
    local P = {}
    local want = {}
    for w in (os.getenv('BOKU_PROBE') or ''):gmatch('[^,]+') do want[w] = true end

    local function in_ram(p) return p >= 0x80000000 and p < 0x80200000 end

    function P.status()
        local page = L.r32(0x800359EC)
        local block = L.r32(0x80036338)
        return string.format(
            'pc=%08x mode=%02x map=%q day=%d %02d:%02d ev_block=%08x ev_pc=%08x text_page=%08x flags=%x wait=%d voice=%d dlg_level=%d pad=%04x',
            PCSX.getRegisters().pc, L.r8(0x800237E0), L.rbytes(0x80026C00, 8):gsub('%z.*', ''),
            L.r8(0x80028FA0), L.r8(0x80028FA1), L.r8(0x80028FA2), block, L.r32(0x80036340), page,
            L.r32(0x800359E4), L.rs16(0x800359F4), L.r8(0x800359F6), L.r8(0x80036541), L.r16(0x80072766))
    end

    local function words(p, n)
        local t = {}
        for i = 0, n - 1 do t[#t + 1] = string.format('%04x', L.r16(p + 2 * i)) end
        return table.concat(t, ' ')
    end

    local hits = { dialog_open = 0, msg_open = 0, event_begin = 0, dbg_vprintf = 0, dbg_printf = 0, heap = 0 }
    local prim_peak, prim_peak_frame, prim_peak_dlg = 0, 0, 0
    local last_voice, last_wait_zero

    function P.arm()
        if want.dialog then
            L.bp(0x8002BD30, 'Exec', 4, 'dialog_open', function()
                local r = PCSX.getRegisters().GPR.n
                hits.dialog_open = hits.dialog_open + 1
                L.say('PROBE f=%d dialog_open x=%d y=%d vertical=%d text=%08x ra=%08x ev_block=%08x off=+0x%x words: %s',
                    L.frame, r.a0, r.a1, r.a2, r.a3, r.ra, L.r32(0x80036338), r.a3 - L.r32(0x80036338),
                    in_ram(r.a3) and words(r.a3, 12) or '?')
                return true
            end)
            L.bp(0x8002CF9C, 'Exec', 4, 'msg_open', function()
                local r = PCSX.getRegisters().GPR.n
                hits.msg_open = hits.msg_open + 1
                L.say('PROBE f=%d msg_open msg=%d ra=%08x ev_block=%08x ev_pc=+0x%x', L.frame, r.a0, r.ra,
                    L.r32(0x80036338), L.r32(0x80036340) - L.r32(0x80036338))
                return true
            end)
            L.bp(0x8002CD8C, 'Exec', 4, 'event_begin', function()
                local r = PCSX.getRegisters().GPR.n
                hits.event_begin = hits.event_begin + 1
                local b = r.a0
                local n = in_ram(b) and L.r32(b) or 0
                local sig = ''
                if n >= 3 and n < 600 then
                    -- fingerprint: entry count, the offsets of bytecode and first text, and
                    -- the first 16 bytecode bytes; enough to find the event offline.
                    local code = b + L.r32(b + 12)
                    sig = string.format('n=%d off2=0x%x code: %s', n, L.r32(b + 12), words(code, 16))
                end
                L.say('PROBE f=%d event_begin block=%08x ctx=%08x ra=%08x map=%q %s ctx: %s', L.frame, b, r.a1, r.ra,
                    L.rbytes(0x80026C00, 8):gsub('%z.*', ''), sig, in_ram(r.a1) and words(r.a1, 10) or '?')
                return true
            end)
        end
        if want.dbg then
            for name, a in pairs({ dbg_vprintf = 0x800229A4, dbg_printf = 0x80022C38 }) do
                L.bp(a, 'Exec', 4, name, function()
                    hits[name] = hits[name] + 1
                    if hits[name] <= 5 then L.say('PROBE f=%d %s ra=%08x', L.frame, name, PCSX.getRegisters().GPR.n.ra) end
                    return true
                end)
            end
        end
        if want.heapraise then
            local done = false
            L.bp(0x80049154, 'Exec', 4, 'entry', function()
                if done or L.r32(0x80049154) ~= 0x3C028007 then return true end -- BIOS shell code lives here first
                done = true
                assert(L.r32(0x80068AF0) == 0x8008F3A4, 'g_heap_base is not 0x8008F3A4')
                L.w32(0x80068AF0, 0x8008F800)
                for a = 0x8008F3A4, 0x8008F7FC, 4 do L.w32(a, 0x5AFEC0DE) end
                L.say('PROBE f=%d entry reached: g_heap_base raised to 0x8008F800, sentinel written', L.frame)
                want.heap = true
                P.arm_heap()
                return false
            end)
        end
        function P.arm_heap()
            -- One breakpoint per word: width semantics beyond 4 were not verified.
            for a = 0x8008F3A4, 0x8008F7FC, 4 do
                L.bp(a, 'Write', 4, 'heapgap', function(addr)
                    hits.heap = hits.heap + 1
                    if hits.heap <= 20 then
                        L.say('PROBE f=%d write into 0x8008F3A4..7FF at %08x pc=%08x', L.frame, addr, PCSX.getRegisters().pc)
                    end
                    return true
                end)
            end
        end
        if want.heap and not want.heapraise then P.arm_heap() end
        if want.voice then
            L.bp(0x800359F6, 'Write', 1, 'g_voice_active', function()
                local r = PCSX.getRegisters()
                L.say('PROBE f=%d write g_voice_active from pc=%08x ra=%08x (old=%d)', L.frame, r.pc, r.GPR.n.ra, L.r8(0x800359F6))
                return true
            end)
        end
        if want.pad then
            local last_pad = 0
            L.on_frame(function(f)
                local v = L.r16(0x80072766)
                if v ~= last_pad then
                    L.say('PROBE f=%d pad word %04x -> %04x (flags=%x voice=%d page=%08x)', f, last_pad, v,
                        L.r32(0x800359E4), L.r8(0x800359F6), L.r32(0x800359EC))
                    last_pad = v
                end
            end)
        end
        if want.prim or want.voice then
            L.on_frame(function(f)
                if want.prim then
                    -- Sampled at vsync: g_prim_next minus whichever of the two buffers it is inside.
                    local nxt, b0, b1 = L.r32(0x800258F0), L.r32(0x800258E8), L.r32(0x800258EC)
                    local used = -1
                    if nxt >= b0 and nxt < b0 + 0x130B0 then used = nxt - b0
                    elseif nxt >= b1 and nxt < b1 + 0x130B0 then used = nxt - b1 end
                    if used > prim_peak then
                        prim_peak, prim_peak_frame = used, f
                        prim_peak_dlg = L.r32(0x800359EC)
                    end
                end
                if want.voice then
                    local fl, pg = L.r32(0x800359E4), L.r32(0x800359EC)
                    if fl ~= P._fl or pg ~= P._pg then
                        L.say('PROBE f=%d g_text_flags %x -> %x, g_text_page %08x -> %08x (wait=%d voice=%d)', f,
                            P._fl or 0, fl, P._pg or 0, pg, L.rs16(0x800359F4), L.r8(0x800359F6))
                        P._fl, P._pg = fl, pg
                    end
                    local v, w = L.r8(0x800359F6), L.rs16(0x800359F4)
                    if v ~= last_voice then
                        L.say('PROBE f=%d g_voice_active %s -> %d (wait=%d flags=%x page=%08x)', f, tostring(last_voice), v, w,
                            L.r32(0x800359E4), L.r32(0x800359EC))
                        last_voice = v
                    end
                    local z = (w == 0)
                    if z ~= last_wait_zero then
                        L.say('PROBE f=%d g_text_wait %s (=%d voice=%d flags=%x page=%08x)', f, z and 'reached 0' or 'loaded', w, v,
                            L.r32(0x800359E4), L.r32(0x800359EC))
                        last_wait_zero = z
                    end
                end
            end)
        end
    end

    function P.report()
        for k, v in pairs(hits) do L.say('PROBE total %s = %d', k, v) end
        if want.heapraise then
            local bad = 0
            for a = 0x8008F3A4, 0x8008F7FC, 4 do if L.r32(a) ~= 0x5AFEC0DE then bad = bad + 1 end end
            L.say('PROBE sentinel words changed in 0x8008F3A4..0x8008F7FF: %d of 279; g_heap_base now %08x', bad, L.r32(0x80068AF0))
        end
        if want.prim then
            L.say('PROBE prim peak = %d bytes of 78000 at f=%d (dialogue %s)', prim_peak, prim_peak_frame,
                prim_peak_dlg ~= 0 and 'up' or 'not up')
        end
    end

    return P
end
