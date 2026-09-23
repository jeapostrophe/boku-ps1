--[[ FMV-04: boot to the opening movie -- or another in its place, BOKU_PLAY_NAME below --
     do not skip it, and dump decoded frames from RAM.

     The boot's presses are lib.lua's (L.BOOT_PRESSES, without the movie skip), replayed
     from the frame the title comes up (L.after_title), which puts the memory-card screen up
     and then the movie ~1270 vsyncs after the title. Every change of the game mode is
     printed ("MODE f=<vsync> mode=<hex>"), so a boot that went elsewhere says where. A frame is read where
     design E2 writes it: the twenty 16 x 240 x 3-byte slice buffers, each copied at the
     LoadImage call in movie_dctout_cb (0x80034C14, ra 0x80034C1C -- the same site once
     asm/movie.asm's movie_sub_blit tail-jumps there). Decoded frames are counted from the
     first slice, so index k is the same picture on the stock image and on a patched one.
     The GPU is not asked: takeScreenShot goes black in the movie's 24-bit display mode
     (research/tooling-setup.md § PCSX-Redux, headless), which is why this script dumps
     buffers and shoots nothing.

       BOKU_SUB_FRAME_NO  REQUIRED: the RAM address of movie_sub_frame_no, decimal or 0x
                          hex. It is decided in asm/movie.asm and recorded by the build as
                          edits.json -> movie_subtitles.islands[0].symbols.movie_sub_frame_no;
                          this script keeps no copy of it, so a rebuilt island cannot leave
                          it reading a stale address and reporting the words it finds there
                          as frame numbers
       BOKU_DUMP_INDEX    comma list of decoded-frame indices to dump (default 59,199,399):
                          dumps/k<K>.bin under BOKU_WORK, the 20 slices in order, and
                          dumps/k<K>.txt, one line per slice -- its x (VRAM halfwords), its
                          VRAM y, the word at movie_sub_frame_no (the STR frame number the
                          hook drew for, meaningless on the stock image) and the last STR
                          header number movie_frame_volume saw. Only a frame on this list is
                          copied out of RAM at all
       BOKU_POLL_FROM/TO  print "POLL n=<frame> polls=<StGetNext calls since the previous
                          frame> dvs=<vsyncs>" for STR frames in that range: the per-frame
                          idle budget of research/movies.md § 2.2. Off unless one of the two
                          is set (the StGetNext breakpoint it needs fires millions of times
                          a boot); setting either takes 100 and 340 for the other
       BOKU_ISLAND_WATCH  1 arms an execution breakpoint over the island asm/movie.asm
                          reuses and reports every hit -- on the STOCK image, where a hit
                          means the island is not dead. The count is printed at exit
                          ("ISLAND hits=N"). Needs BOKU_ISLAND_BYTES, the island's size
                          (edits.json -> movie_subtitles.islands[0].bytes), watched from
                          BOKU_SUB_FRAME_NO on; or BOKU_ISLAND_RANGE "start,length" (hex)
                          for another range entirely -- the red run, over a function the
                          boot is known to call
       BOKU_PLAY_NAME, BOKU_PLAY_FRAMES
                          play another movie where the boot plays the opening: at each
                          movie_play_entry (0x80034594) the entry it was handed gets this
                          name pointer (g_movie_table's word 0, decimal or 0x hex) and this
                          stop frame (word 3) before the function reads them, so the
                          player, the subtitle loader's select and everything after see
                          that movie. Both come from the caller (boku.movie_block.
                          movie_names, research/data/movies.tsv); none is restated here.
                          "PLAY entry=<addr> name=<old>-><new>" is printed
       BOKU_FRAMES        give up at this vsync, moved later by however late the title
                          came (default 6000): exit 3

     Exit 0 once the last dump is written.
--]]
local L = dofile(os.getenv('BOKU_REDUX_DIR') .. '/lib.lua')
local LIMIT = L.numenv('BOKU_FRAMES', '6000')
local POLLS = os.getenv('BOKU_POLL_FROM') or os.getenv('BOKU_POLL_TO')
local POLL_FROM = POLLS and L.numenv('BOKU_POLL_FROM', '100')
local POLL_TO = POLLS and L.numenv('BOKU_POLL_TO', '340')
local SLICE_BYTES, SLICES = 16 * 240 * 3, 20
local LOADIMAGE, CALLBACK_RA = 0x80053684, 0x80034C1C
local SUB_FRAME_NO = assert(tonumber(os.getenv('BOKU_SUB_FRAME_NO') or ''),
    'BOKU_SUB_FRAME_NO must be the RAM address of movie_sub_frame_no (edits.json -> ' ..
    'movie_subtitles.islands[0].symbols); this script keeps no copy of it')
local island_hits = nil

local boot = L.after_title(L.BOOT_PRESSES)
local dump_wanted, remaining = L.numlist('BOKU_DUMP_INDEX', '59,199,399')

local PLAY_NAME = os.getenv('BOKU_PLAY_NAME') and L.numenv('BOKU_PLAY_NAME')
local PLAY_FRAMES = PLAY_NAME and L.numenv('BOKU_PLAY_FRAMES')
if PLAY_NAME then
    L.bp(0x80034594, 'Exec', 4, 'movie_play_entry', function()
        local entry = PCSX.getRegisters().GPR.n.a0
        L.say('PLAY entry=%08x name=%08x->%08x frames=%d->%d', entry, L.r32(entry), PLAY_NAME,
            L.r32(entry + 12), PLAY_FRAMES)
        L.w32(entry, PLAY_NAME)
        L.w32(entry + 12, PLAY_FRAMES)
        return true
    end)
end

local polls, last_vsync = 0, nil
local frames_seen, header_no = 0, -1
local last_mode = nil

L.bp(0x800350F8, 'Exec', 4, 'movie_frame_volume', function()
    local n = PCSX.getRegisters().GPR.n.a0
    frames_seen = frames_seen + 1
    header_no = n
    if POLLS and n >= POLL_FROM and n <= POLL_TO then
        L.say('POLL n=%d polls=%d dvs=%d', n, polls, last_vsync and (L.frame - last_vsync) or -1)
    end
    polls, last_vsync = 0, L.frame
    return true
end)
if POLLS then
    -- One hit per ring poll -- millions a boot, and only the POLL lines read the count.
    L.bp(0x80066A60, 'Exec', 4, 'StGetNext', function() polls = polls + 1; return true end)
end

-- The slices of the frame being uploaded, and how many decoded frames came before it.
local slices, notes, index = {}, {}, 0
os.execute("mkdir -p '" .. L.work .. "/dumps'")
L.bp(LOADIMAGE, 'Exec', 4, 'LoadImage', function()
    local r = PCSX.getRegisters().GPR.n
    if r.ra ~= CALLBACK_RA then return true end
    local x, y = L.r16(r.a0), L.r16(r.a0 + 2)
    local k = x / 24
    if dump_wanted[index] then
        -- Copied only for a frame that will be written: every slice of every frame is ~92 MB
        -- of strings a boot, and nothing but the dump reads them.
        slices[k] = L.rbytes(r.a1, SLICE_BYTES)
        notes[k] = string.format('slice=%d x=%d y=%d sub_frame=%d header=%d',
            k, x, y, L.r32(SUB_FRAME_NO), header_no)
    end
    if k == SLICES - 1 then
        if dump_wanted[index] then
            local parts, lines = {}, {}
            for i = 0, SLICES - 1 do
                assert(slices[i], 'decoded frame ' .. index .. ' is missing slice ' .. i)
                parts[#parts + 1] = slices[i]
                lines[#lines + 1] = notes[i]
            end
            local stem = L.work .. '/dumps/k' .. index
            L.write_file(stem .. '.bin', table.concat(parts))
            L.write_file(stem .. '.txt', table.concat(lines, '\n') .. '\n')
            L.say('DUMP f=%d index=%d header=%d -> %s.bin', L.frame, index, header_no, stem)
            dump_wanted[index] = nil
            remaining = remaining - 1
        end
        index = index + 1
        slices, notes = {}, {}
    end
    return true
end)

if os.getenv('BOKU_ISLAND_WATCH') == '1' then
    local start, length = SUB_FRAME_NO, nil
    local range = os.getenv('BOKU_ISLAND_RANGE')
    if range then
        local s, n = string.match(range, '^(%x+),(%x+)$')
        assert(s, 'BOKU_ISLAND_RANGE is "start,length" in hex')
        start, length = tonumber(s, 16), tonumber(n, 16)
    else
        length = assert(tonumber(os.getenv('BOKU_ISLAND_BYTES') or ''),
            'BOKU_ISLAND_WATCH needs BOKU_ISLAND_BYTES (edits.json -> ' ..
            'movie_subtitles.islands[0].bytes), watched from BOKU_SUB_FRAME_NO on, or ' ..
            'BOKU_ISLAND_RANGE "start,length" in hex; the island is not restated here')
    end
    island_hits = 0
    L.bp(start, 'Exec', length, 'island', function()
        island_hits = island_hits + 1
        local r = PCSX.getRegisters()
        if island_hits <= 5 then
            L.say('ISLAND hit %d f=%d pc=%08x ra=%08x', island_hits, L.frame, tonumber(r.pc) or -1, r.GPR.n.ra)
        end
        return true
    end)
    L.say('ISLAND watching %08x +%x', start, length)
end

local function finish(code, why)
    if island_hits then L.say('ISLAND hits=%d', island_hits) end
    L.finish(code, why)
end

L.on_frame(function(f)
    local shift = boot(f)
    local mode = L.r8(L.MODE)
    if mode ~= last_mode then L.say('MODE f=%d mode=%02x', f, mode); last_mode = mode end
    if remaining == 0 then finish(0, 'done strframes=' .. frames_seen .. ' decoded=' .. index) end
    if f >= LIMIT + shift then
        finish(3, 'dumps still due at vsync ' .. f .. ', strframes=' .. frames_seen ..
            ', title ' .. shift .. ' vsyncs late, game mode ' .. mode)
    end
end)
