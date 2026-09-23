--[[ VO-03: a native g_xa_clips play with its subtitle, reached from a cold boot.

     BOKU_ROUTE picks the clip; both start where the intro movie hands over to the field
     (game_mode_set(5) called from movie_queue_play, 0x80013C24):

       bedtime   movie mode is entered again with the day-end queue (one sleep movie,
                 BOKU_MOVIE, default 7) and, when movie_queue_play starts (0x800139E4), the
                 byte it reads as "came from the diary" (0x800237E5) set to 0x0B -- what the
                 day-end code sets. On day 1 it then plays XCH.34 in 0x8002E568's wait loop.
       ending    ENDOTI (mode 0x10) is entered instead, with ending BOKU_ENDING (default 0)
                 in 0x80035F42: it plays XCH.41 + that.

     The presses are lib.lua's, anchored to the title (L.after_title). From the clip on,
     every change of the
     subtitle's state is printed, one line each:

       CLIP  f=<vsync> clip=<index> magic=<the movie block's first word at 0x801C0000>
       STATE f=<vsync> mode=<game mode> page=<g_text_page> flags=<g_text_flags>
             busy=<XA status 0x800359D8> panel=<g_dlgbox_visible> level=<g_dlgbox_level>

       BLOCK f=<vsync>  the block's BOKU_BLOCK_BYTES bytes at BOKU_BLOCK_RAM changed, while
             the game mode is still the clip's: the subtitle reads its words from there

     BOKU_SHOTS shoots every N vsyncs from the clip (default 0: none); BOKU_AFTER is how long
     to watch (default 400 bedtime, 1900 ending); BOKU_FRAMES gives up (default 8000): exit 3.
     tests/test_real_clip_subtitle.py reads these lines.
--]]
local L = dofile(os.getenv('BOKU_REDUX_DIR') .. '/lib.lua')
local ROUTE = os.getenv('BOKU_ROUTE') or 'bedtime'
assert(ROUTE == 'bedtime' or ROUTE == 'ending', 'BOKU_ROUTE is bedtime or ending')
local MOVIE = L.numenv('BOKU_MOVIE', '7')
local ENDING = L.numenv('BOKU_ENDING', '0')
local SHOTS = L.numenv('BOKU_SHOTS', '0')
local AFTER = L.numenv('BOKU_AFTER', ROUTE == 'bedtime' and '400' or '1900')
local LIMIT = L.numenv('BOKU_FRAMES', '8000')
local BLOCK_BYTES = L.numenv('BOKU_BLOCK_BYTES', '0')
local BLOCK_RAM = L.numenv('BOKU_BLOCK_RAM', '0')     -- boku.movie_block.BLOCK_RAM

local MODE_SET, FROM_MOVIE_MODE, MOVIE_QUEUE_PLAY = 0x80011A98, 0x80013C24, 0x800139E4
local XA_PLAY_INDEXED = 0x8002B4E4
local boot = L.after_title(L.BOOT_PRESSES, L.SKIP_MOVIE)
local TEXT_PAGE, TEXT_FLAGS, XA_STATUS = 0x800359EC, 0x800359E4, 0x800359D8
local PANEL_VISIBLE, PANEL_LEVEL = 0x8002911E, 0x80036541
local redirected, clip_at, clip_mode, last, last_block

L.bp(MODE_SET, 'Exec', 4, 'mode_set', function()
    if L.r32(MODE_SET) == 0 then return true end -- before the EXE is loaded
    local r = PCSX.getRegisters().GPR.n
    if r.a0 == 5 and r.ra == FROM_MOVIE_MODE and not redirected then
        redirected = L.frame
        if ROUTE == 'bedtime' then
            L.w32(0x80036560, 1)            -- g_movie_queue: one movie
            L.w32(0x80036564, MOVIE)
            r.a0 = 0xE
        else
            L.w8(0x80035F42, ENDING)
            r.a0 = 0x10
        end
        L.say('ROUTE f=%d %s', L.frame, ROUTE)
    end
    return true
end)
L.bp(MOVIE_QUEUE_PLAY, 'Exec', 4, 'movie_queue_play', function()
    if redirected and ROUTE == 'bedtime' then L.w8(L.MODE + 5, 0x0B) end
    return true
end)
L.bp(XA_PLAY_INDEXED, 'Exec', 4, 'xa_play_indexed', function()
    if redirected and not clip_at then
        clip_at = L.frame
        L.say('CLIP f=%d clip=%d magic=%08x', L.frame, PCSX.getRegisters().GPR.n.a0, L.r32(BLOCK_RAM))
    end
    return true
end)

L.on_frame(function(f)
    local shift = boot(f)
    if clip_at then
        local state = string.format('mode=%x page=%08x flags=%x busy=%x panel=%d level=%d',
            L.r8(L.MODE), L.r32(TEXT_PAGE), L.r32(TEXT_FLAGS), L.r32(XA_STATUS),
            L.r8(PANEL_VISIBLE), L.r8(PANEL_LEVEL))
        if state ~= last then
            L.say('STATE f=%d %s', f, state)
            last = state
        end
        clip_mode = clip_mode or L.r8(L.MODE)
        if BLOCK_BYTES > 0 and L.r8(L.MODE) == clip_mode then
            local block = L.rbytes(BLOCK_RAM, BLOCK_BYTES)
            if block ~= last_block then L.say('BLOCK f=%d', f); last_block = block end
        end
        if SHOTS > 0 and (f - clip_at) % SHOTS == 0 then L.shot(string.format('%s-%05d', ROUTE, f)) end
        if f >= clip_at + AFTER then L.finish(0, 'watched') end
    elseif f >= LIMIT + shift then
        L.finish(3, 'no clip by vsync ' .. f)
    end
end)
