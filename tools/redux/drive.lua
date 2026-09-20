--[[ Generic headless driver: load a save state (or boot), play a pad script, take
     framebuffer shots, optionally save a state at the end. Every other script here is
     this plus probes; use it to explore.

     Env (frames count from 1 at script start, i.e. from the state load when there is one):
       BOKU_LOAD        save-state name under $BOKU_WORK/states (omit to boot the disc)
       BOKU_INPUT       "frame:BUTTON:duration;..."  e.g. "300:START:4;420:CIRCLE:4"
                        BUTTON may be A+B for a chord. Names: PCSX.CONSTS.PAD.BUTTON.
       BOKU_FRAMES      stop after this many frames (default 600)
       BOKU_SHOT_EVERY  shot period in frames (0 = none); BOKU_SHOT_AT "f,f,f" for specifics
       BOKU_PREFIX      shot name prefix (default "drive")
       BOKU_SAVE        save-state name to write at the last frame
       BOKU_POKES       lua file to dofile after load (RAM patches), receives L as `...`
--]]
local L = dofile(os.getenv('BOKU_REDUX_DIR') .. '/lib.lua')
local probes = dofile(os.getenv('BOKU_REDUX_DIR') .. '/probes.lua')(L)

local FRAMES = L.numenv('BOKU_FRAMES', '600')
local EVERY = L.numenv('BOKU_SHOT_EVERY', '0')
local PREFIX = os.getenv('BOKU_PREFIX') or 'drive'
local at = {}
for f in (os.getenv('BOKU_SHOT_AT') or ''):gmatch('%d+') do at[tonumber(f)] = true end

local downs, ups = {}, {}
for f, names, dur in (os.getenv('BOKU_INPUT') or ''):gmatch('(%d+):([%w+]+):(%d+)') do
    f, dur = tonumber(f), tonumber(dur)
    for name in names:gmatch('[^+]+') do
        local b = assert(L.BTN[name], 'unknown button ' .. name)
        downs[f] = downs[f] or {}; table.insert(downs[f], b)
        ups[f + dur] = ups[f + dur] or {}; table.insert(ups[f + dur], b)
    end
end

local loaded = false
L.on_frame(function(f)
    if not loaded then
        loaded = true
        local name = os.getenv('BOKU_LOAD')
        if name and name ~= '' then L.load_state(name); L.say('DRIVE loaded state %s', name) end
        local pokes = os.getenv('BOKU_POKES')
        if pokes and pokes ~= '' then assert(loadfile(pokes))(L) end
        probes.arm()
    end
    for _, b in ipairs(ups[f] or {}) do L.release(b) end
    for _, b in ipairs(downs[f] or {}) do L.press(b) end
    if (EVERY > 0 and f % EVERY == 0) or at[f] then
        L.shot(string.format('%s-%05d', PREFIX, f))
        L.say('DRIVE f=%d %s', f, probes.status())
    end
    if f >= FRAMES then
        local save = os.getenv('BOKU_SAVE')
        if save and save ~= '' then L.say('DRIVE saved %s', L.save_state(save)) end
        probes.report()
        L.finish(0, 'ok')
    end
end)
