--[[ BOKU_POKES file for drive.lua: once the bag is open, give it items 1, 2, 3 so their
     names and a description are on screen (research/vwf-prototype.md § "The bag with
     items"). The bag rebuilds its list when it opens, so the write waits for that frame.

     BOKU_BAG_AT  the drive frame to write at (after the bag has opened)
     The list: g_bag_items (0x80047E28, one item id per row), g_bag_count (0x80047E1E),
     read by bag_draw 0x800416E8.
--]]
local L = ...
local at = L.numenv('BOKU_BAG_AT', '420')
L.on_frame(function(f)
    if f == at then
        L.w8(0x80047E1E, 3)
        L.w8(0x80047E28, 1); L.w8(0x80047E29, 2); L.w8(0x80047E2A, 3)
        L.say('BAG items 1 2 3 at f=%d', f)
    end
end)
