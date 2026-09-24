# Texture recipes — English typeset into textures at build time (PLAN `GFX-07`, `GFX-09`)

[textures-plan.md](textures-plan.md) chose a path for every image with Japanese in its
pixels. This file is the **P** path as built: how `boku build --textures` turns the tracked
English into rebuilt images, and, per image, the measurements its recipe stands on. Every
number here was measured on the dump of [disc-recon.md](disc-recon.md) and on Beetle PSX.

## How it is built

* **The English** lives in `translation/textures/*.txt`, one row per string: `id<TAB>English`
  ([../translation/textures/README.md](../translation/textures/README.md)). Ids are the
  `tex@<member>.<n>` namespace [textures-plan.md](textures-plan.md) § "The new English text
  this creates" proposed.
* **The recipe** for each image is a function in `boku/texture_text.py`, registered in
  `FAMILIES` under the id before the last dot (`tex@T_TITLE`), or under the namespace of a
  bulk family whose ids name a page (`nikki@` — the picture diary, whose recipe and
  measurements are [diary-redraw.md](diary-redraw.md) § "The build"); a bulk family builds
  the pages it is given. It reads the image out of the
  contributor's import, checks the image is the one it was measured on, blanks and typesets
  in the image's own palette indices, and returns `ByteEdit`s — the texture's changed bytes
  at every occurrence (`boku.textures.patches_for`) plus any code or data word the screen
  needs changed to show the English. A single texture's family takes all its strings or refuses; an id no
  recipe owns is refused, so a typo cannot leave a texture in Japanese silently.
* **The type** is the game's own 12×12 dialogue glyphs, decoded from the one glyph sheet in
  the import (`boku/typeset.py`; the sheet is [font.md](font.md)'s), re-aligned to their ink
  and advanced `ink + 1` — the variant [font-candidates.md](font-candidates.md) measured and
  [diary-redraw.md](diary-redraw.md) chose for the diary. A character the sheet cannot draw
  (`-`, `"`, `[` …) is refused, never substituted.
* **The build.** `boku build --textures DIR` applies the edits with everything else, so every
  `old` is verified against the source image before a sector is written;
  `./make.sh build-days` passes `--textures translation/textures`. The rebuilt image exists
  only in `build/` — it is the original's pixels plus our text (CLAUDE.md § "This repo is
  public").

## `T_TITLE` — the title menu

`\_DATA\T_TITLE.BIN` child 0 (`_DATA_T_TITLE.BIN__000014`), 248×198 8bpp, 4 CLUTs. Rows 0–63
hold the four menu lines in 16-row bands, the Japanese inked on band rows 1–13 within x 0–82:
a dark fill (index 14) ringed by a pale outline (index 1), with a few antialias entries
between. CLUT 0 is what the three idle lines are drawn in; **CLUT 3 is a ramp of greys** — the
drop shadow is the game drawing the same sprite again through it, so a rebuilt line gets its
shadow for free. The (TM) mark beside the logo is a sprite at x 128–151, rows 17–49; x 84–127
of the menu rows is transparent.

**The sprites.** Each line is drawn from a 0x18-byte record in `TITLE.OVL`:

| record (RAM) | screen x, y | u, v | w × h |
|---|---|---|---|
| `0x80081814` | 0x77, 0x7A | 0, 0 | 0x54 × 0x10 |
| `0x80079DD8` | 0x77, 0x8C | 0, 16 | 0x54 × 0x10 |
| `0x80079DF0` | 0x77, 0x9E | 0, 32 | 0x54 × 0x10 |
| `0x80079E08` | 0x77, 0xB0 | 0, 48 | 0x54 × 0x10 |

(layout: `u16 0, x, y; u8 u, v; u16 w, h`, then fields not needed here.) The cursor's line is
drawn a second time as a pulsing highlight whose width is an immediate,
`addiu $a1, $zero, 0x54` at `0x8007F85C`, stored into the highlight's state at `0x80082080`.

**84 px is too narrow for English.** The Japanese lines are seven 12 px glyphs; *Summer
Memories* in the game's glyphs is 107 px of ink, 109 with its outline. The recipe widens all
four records and the highlight immediate to **128** — the transparent space the atlas already
has — and the screen has room (0x77 + 128 = 247 < 320). Measured on Beetle with a ruler
pattern: at 0x54 exactly x 0–83 of each band is drawn; at 128 all four lines and the
highlight draw 128 wide; with the records widened and the immediate not, the cursor's line
shows the highlight only over its first 84 px. So both are needed.

**What the recipe draws.** Each band is cleared to transparent over x 0–127; the English is
set with its first glyph's ink at x 1 and the glyph cell's top at band row 1 (capitals ink
rows 2–10, descenders to 12); every inked pixel takes the fill, and its eight neighbours that
are not ink take the outline. Fill and outline are read out of the Japanese's own pixels (the
two most-used entries), not assumed.

**Proof.** `tests/test_real_texture_text.py` checks the rebuilt atlas against the tracked
English and the disc's glyph sheet texel by texel, and that nothing outside the four widened
bands changed. `tests/test_real_texture_text_beetle.py` (`./make.sh emu-test`) boots an image
carrying only these edits on Beetle to the menu (START at frame 3300, shot at 3650) and
requires every texel the build changed and left opaque in the three idle lines to show its
CLUT-0 colour on screen exactly; the stock image fails it, and so does an image with the
English but not the widened records.

## Painting Japanese out of a ground that is not flat

Most plates are not one colour: the settings screen's are a dithered radial gradient. The
recipes paint the Japanese out with `boku/texture_paint.py`: the type is found by colour
through the CLUT the screen draws it in (pale near-neutral pixels on a saturated ground, or
dark pixels on a pale plate), grown by a pixel or two to take its antialiasing and drop
shadow, and each such pixel is replaced by the nearest clean pixel **of its own row, an even
distance away**, so an ordered dither keeps its phase and a gradient keeps its slope. A rule
or frame line that must survive is passed as `avoid` and is never a donor. The English is then
stamped in the entry the Japanese used most — so the white, the shadow and the ground are
all the texture's own.

## `T_CONFIG` — the settings screen

Two textures, both drawn by `TITLE.OVL`'s settings mode (records from `0x8008190A`, 0x16
bytes apart here, same layout as the title's). The five labels down the left are renderer
text (`exe@8003D9BC`, `TXT-05`), not these. Child 0 is `_DATA_T_CONFIG.BIN__000014` (384×240,
5 CLUTs), child 1 `_DATA_T_CONFIG.BIN__017234` (384×228, 8 CLUTs). Where each piece lands and
through which CLUT, measured on the stock image on Beetle by matching every CLUT at every
screen offset against a screenshot:

| piece | texture box (x, y, w, h) | CLUT | screen | record |
|---|---|---|---|---|
| heading plaque interior (flat) | child 0 (64, 164, 50, 30) | 2 | top left | `0x80081ACC` |
| message plate: both modes, small | child 1 (0, 0, 128, 146) | 7 | (168, 28) | `0x800819D0` |
| sound plate: stereo / mono, small | child 0 (256, 0, 128, 146) | 1 | (168, 28) | `0x800819BA` |
| controller chart, column headings | child 1 (256, 0, 128, 66) | 5 | (168, 28) | `0x800819E6` |
| selected value, large: voice + text | child 1 (96, 148, 107, 45) | 3 | (180, 42) | `0x800819FC` |
| … voice only | child 1 (0, 148, 96, 48) | 3 | (185, 110) | `0x80081A12` |
| … stereo | child 1 (96, 196, 96, 32) | 3 | (185, 53) | `0x80081A28` |
| … mono | child 1 (0, 196, 96, 32) | 3 | (185, 113) | `0x80081A3E` |

The plate names both values small; the **selected** value is then drawn large, as an opaque
rectangle carrying its own slice of the gradient, over its small twin — so a plate always
shows one value large and the other small. `ON`/`OFF` are already Latin and untouched.

**What the recipe draws.** The heading: the plaque interior is refilled with its own flat
colour and *Settings* set in the plaque's dark ink, centred (49 px of a 50 px interior).
Small labels: set 1× in the plate's white on the rows the Japanese occupied, centred on the
plate. Large values: the largest of 2× or 1×-bold that fits the cell (*Stereo* and *Mono*
2×; the two message modes 1×-bold, with their note 1×), with a two-pixel drop shadow in the
darkest entry the Japanese shadow used. Chart headings: turned a quarter clockwise to read
top to bottom, in the column the Japanese occupied, bottom-aligned with it; `Sub // Screen`
is two turned lines. The sheet's `(` `)` are vertical-writing forms, so the notes on skipping
go without parentheses.

**Proof.** `tests/test_real_texture_text.py` finds each tracked string in its slot exactly
once, as the game's glyphs (plain, 2×, bold or turned), and requires the type-coloured pixels
of the slot to be exactly those strings — no Japanese left.
`tests/test_real_texture_text_beetle.py` drives Beetle to the message and sound pages and
requires every texel the build changed and left opaque to show its colour on screen exactly,
the large value included.

The back button (`もどる`, a stone) is built with the other buttons (§ "Buttons").

## `T_MEMORY` — the "summer memories" album

`_DATA_T_MEMORY.BIN__00d634` (640×202, 6 CLUTs): five filmstrip miniatures, which stay, and the
heading plaque. The plaque's interior is flat, x 16–114, y 158–187 (the most-used entry of
the plaque, measured through CLUT 0), but for three corner pixels at (112–114, 158) that
the recipe leaves alone; the other five CLUTs recolour the same pixels. *Summer
Memories* is 107 px on one line against 99, so the tracked string breaks it onto two lines
(`flat_plaque`, the same recipe as the settings heading). The six menu labels under it are
renderer text (`exe@8003DA00`, `TXT-05`).

**Not seen in the game.** The album is reached from the title menu only with a card holding
a *finished* game; with anything else the title answers "no file that has finished this game"
(`exe@8003D5F0.5`, `g_mc_msg` record 8). A generated card is not one, whichever of these it
carries — measured on Beetle, 2026-09-22: a day-5 morning; the summary's unknown `flag` byte
(`0x80025914`) at 1 or `0xFF`; `g_clock.day` 32; `flag[250]` 1 and `flag[251]` 12. What
marks a finished file is not decoded. The proof here is the rebuilt texture
(`tests/test_real_texture_text.py`: each line found once, in order, and nothing else on the
plaque).

## `M_C15` — the notice board on the path to the beach (PLAN `GFX-09`)

The audit had this as the one **subtitle** image: a notice "painted into a background at an
angle", so a caption beside it. Seen on Beetle it is neither angled nor alone:

* **The board is frontal**, dark wood with two lines of white painted type, in the
  bottom-right corner of the screen, and it runs off the screen's right edge — in the game the
  sign is cut mid-line (the first line after four characters, the second after six). A bird
  and a wave are painted at its left.
* **It is in both variants of the map.** `M_C15000` (the one day 1 loads) and `M_C15100` each
  carry a 490×252 8bpp background atlas with the board in its top-right corner at the same
  place, in two lightings (different indices and palettes). The census missed `C15000` — its
  rule's regex read `M_C1510?0` (corrected; the census and plan tables regenerated, 198 rows).
* The board is drawn through **CLUT 5**; atlas (330, 20) lands at screen (161, 178), so atlas
  x 489 is just past the right edge.

So it is programmatic, like the plates: the type (pale, through CLUT 5) is painted out along
the wood's horizontal grain, and the English painted in the white the Japanese used most, at
2× the game's glyphs (the Japanese is ~22 px with 2 px strokes). Line boxes: x 392–489 rows
18–47 (starting after the bird) and x 334–489 rows 50–77. Each English line starts where its
Japanese did and runs off the board exactly as the Japanese does; nothing is shortened.
`beach_notice` does this to both atlases.

**Reaching it.** After a new game's opening movie the game enters the map named at
`g_movie_return_map` ([movies.md](movies.md)); poking `C15` into it during the movie
(`run_core.py --poke 5300:0x80036588=43313500` with `boot-to-dialogue.press`) lands day 1 on
this screen at frame ~6000. `C15100` is not reached that way on day 1; its board is checked
at the texture level.

**Proof.** `tests/test_real_texture_text.py` finds each line in both atlases, at 2×, cut at
the atlas edge, and no other pale type in the line boxes. `tests/test_real_texture_text_beetle.py`
warps a texture-only image there and requires every texel the build changed on the visible
board to show its CLUT-5 colour exactly.

**When a translation rebuilds the map.** The board lives in child 6 of a map pack that also
carries event text. If a later day's translation grows `C15`'s text, the pack is rebuilt (and
perhaps relocated), and a patch at the board's old offset would land on the rebuild. The
build hands its texture patches to the reinserter (`boku.reinsert.plan(carry=…)`), which
applies each one that falls inside a rebuilt member to the rebuilt bytes, in the same child at
the same distance, and the build drops it from its own patches (`Plan.carried`). A patch into
the text table itself, or into a bare `EV.BIN` block, is refused.

## Buttons — stone "Back" plaques and speech balloons

`boku/texture_buttons.py`; one row of `BUTTONS` per button, its English `btn@<member>.<key>` in
`translation/textures/buttons.txt`. Measured 2026-09-23 on Beetle by pulling VRAM out of a
save state (the `&GPURAM[0][0]` variable of a mednafen state is the 1 MB of VRAM) and finding
each sprite's bytes in `BOKU.BIN`, and by walking the GPU draw list in RAM.

**Trap: a TIM's header is not the depth the game draws it at.** `_DATA_NIKKI_W.BIN__005450`
says 8bpp 28×184 and is drawn as 4bpp 56×184; `SUB`, `PK_WAL`, `TK_WAL`, `M_S01100`, `MZ02` and
`SAMP` are 8bpp atlases with 4bpp sprites cut from the same bytes (their balloons; of their
stones, `TK_WAL`'s and `M_S01100`'s), each drawn through a 16-entry slice of a 256-entry CLUT
row. `boku.texture_paint.Canvas(drawn_4bpp=True)` edits such a texture a nibble at a time,
low nibble on the left.

**How a button is drawn.** Each screen has an atlas table of 12-byte entries
`{u16 x_words, y, w_words, h, mode (0 = 4bpp, 0x80 = 8bpp), clut code}` (x relative to where
the texture is uploaded; `w` in VRAM words, so 4 texels at 4bpp). `atlas_convert`
(`0x8002A500`) turns the table into sprites in RAM at load; `0x80042ABC` → `sprite_draw`
(`0x800428CC`) draws entry *n* at a position from a separate table. Nothing but the sprite
reads the width — the hand cursor, selection ring and hit targets have their own tables — so
a wider balloon is its pixels plus one halfword. The bug-sumo screen (`MUSI.OVL`) instead
uses 22-byte records at `0x8007A538` (`u16 semi, s16 x, y, u8 u, v, u16 w, h, …`) drawn by
`0x8007CDD0`.

**Stones.** Every stone "Back" (もどる) on the disc is the same drawing (found by matching one
against every atlas): the Japanese inked on the 33×13 box 6 right and 2 down of the stone's
top-left opaque corner. Its last two rows are where the bottoms of the three glyphs meet the
top of the lip; a box two rows shorter leaves them on the lip. Each stone's corner and CLUT
are its row of `BUTTONS`; where it is drawn:

| screen | texture | on screen |
|---|---|---|
| settings | `T_CONFIG` `0x14` | texture origin (176, 150) |
| load / save | `M_S01001` `0x14` | texture origin (8, 0) |
| memory album | `T_MEMORY` `0x14` | not seen (`T_MEMORY` above) |
| diary desk | `NIKKI_W` `0x5450`, 4bpp | (256, 204) |
| bug-sumo desk | `M_S01100` `0x14`, 4bpp | (254, 200) |
| kite record | `TK_WAL`, 4bpp | (248, 190) |
| kite book | `TZICON` | (256, 202) |
| the bag | `PK_WAL` | (248, 190) |
| specimen grid | `MZ00` `0x350` | (252, 192) |
| specimen box | `SAMP` `0x14e48` | (240, 201) |

The stone is textured, so the recipe changes **only the Japanese's own pixels** (Jay,
2026-09-23: the mock-up's kite button banded because it repainted more): the ink (darker than
`INK_DARK` through the CLUT) and the antialias touching it (darker than `SOFT`) -- but never a
pixel within two of transparency, which is the stone's outline running into the box -- each
refilled from the nearest clean stone pixel — a row away counting as two columns, so the lip keeps its
bands, and one pixel at a time, never a run copied along the row. The English is the game's
glyphs made bold (every stroke doubled one column right), in the ink entry the Japanese used,
centred on where it was. `M_S02000` carries a stone too, but nothing loads that pack (no
`file_load(148)` in the executable or any overlay), so it is not built.

**Balloons.** A balloon is flat paper, so the recipe blanks the Japanese's whole rectangle
(grown one pixel, inside the paper) to paper before setting the English. The type is the
groups of non-paper the paper surrounds, and any other group on only the rows those span (a
stroke that runs out to the outline, as the last kana of リストへ does) — which leaves the
tail's shading, above or below the type, alone. Lines break at ` // `, `face.pitch` apart;
every inked pixel must keep one pixel of paper between it and anything not paper, or the build
refuses. A balloon is set in the game's glyphs where it holds them, widened where its texture
has free texels, and in Bean where it has none (Jay's ruling, 2026-09-23); only one balloon
shows at a time on every screen here, the one for the item under the cursor.

**Widening** (`Widen`, `layout`) repeats the pair of columns at the balloon's centre (a pair,
so a dither keeps its phase), may set the widened art down elsewhere in texels that are
transparent or were widened balloons' own (a repack), and grows — and moves — every stored
size of the sprite, each checked against its measured bytes first. A sprite may not cross a
256-texel page. `stretch` inserts more columns than the sprite grows by where the sprite ends
in transparent columns the art may take.

| screen | balloons | how |
|---|---|---|
| diary desk (`NIKKI_W`) | おやすみ *Good // night* | widened 4 (atlas entry 6, 12 bytes in front of the TIM); the idle hint, drawn at (40, 16) while `0x80047E50` is set, after 61 frames with no input |
| desk (`SUB`, CLUT 1 slices 2–3; table 0xB4 in front of the texture) | the tackle, cage, glove and net band (page 14, rows 211–250) repacked: tackle +12, glove +4, the others moved right; *Belongings* in Bean, +4 (stretch 8) — the page-15 band holds 96 texels for it and the kite, and 72 would be the game's glyphs; kite, back fit | `SUB.BIN` is loaded once at boot (resident), so a state saved on another image shows the old desk |
| the bag (`PK_WAL`) | *Belongings* +28 and the two page balloons +4, all moved into the empty rows 154–239 of page 14 | the page balloons are drawn only by an idle hint nothing calls (recon); built so no Japanese is left if it is |
| kite record (`TK_WAL`) | *Fly a // Kite* | fits |
| kite book (`TZICON`, a true 4bpp TIM 12 VRAM words wide) | *Make // This Kite* in Bean | no free texels |
| bug sumo (`M_S01100` `0x164b4`, CLUT 2; `MUSI.OVL` 22-byte records from `0x8007A538`, `{u16 semi, s16 x, y, u8 u, v, u16 w, h, u16 tpage x, y, clut x, y, u8 depth, abr}`, one per balloon in each of the two tables) | *Release* +12 and *Bug // Rank* +8 into the free x 484–511; the rest fit; the swap plate (4bpp, slice 3, record `0x8007A7B4`) +8, set by the `plate` recipe (its ground is a checkerboard: refilled from donors an even number of steps away, only its text area, not the arrow); the とじる board (8bpp, CLUT 5, records `0x8007A742`, `0x8007A786`) by the `plank` recipe, its punched-through Japanese transparent | the stone on this screen is drawn through a CLUT not in its TIM |
| insect box (`MZ02`, CLUT 4, the same texture as `SAMP.BIN`'s copy; `SAMP` `0x14e48`, CLUT 6 slices 0–1) | *Bug // Cage*, *Bug // Box* in the game's glyphs; the rest in Bean; *Remove // Specimen* in Sprout — one pixel short in Bean | no free texels (one 44×40 slot at x 684, y 160, and nothing wider) |

**The attendance card** (`PK_ITM` `0x6c`, item 0x6c; seen in the bag, drawn dithered: every
texel its colour or 8 less on each channel). Its title (beside the radio picture) and its
footer (under the grid) are printed blue on a near-white card whose ground turns faintly pink
toward the bottom, so the `label` recipe finds the type by saturation (not the tinted fringe
of the punched hole in its corner), clears the whole of its rectangle grown a pixel (Jay,
2026-09-23: the mock-up had painted over the Japanese) — refilled from the card beside it in
the same rows, so the grid's pale shadow one row above the footer is not drawn down into it,
and on the flat title ground that is the paper itself — and sets the English in Sprout, in
the type's own blue: *Radio // Calisthenics // Attendance Card* beside the picture (its box
stops a column short of the picture's frame) and the footer between the reference marks,
drawn as `*`.

`M_S01100` `0x164b4` also carries the bug-record card (its labels beside numbers drawn at run
time: the catch date, wins and losses, the value in saw-stag beetles), laid out like `FS_WAL`
below, not built.

**Proof.** `tests/test_real_texture_buttons.py`: each stone's dark pixels are exactly its
English bold in the disc's glyphs (only its outline besides), each balloon's type exactly its
English lines, each board's dark pixels and each card label's printed pixels exactly its
English, each widened sprite's stored sizes grown and moved; on Beetle (`./make.sh emu-test`)
settings, load (a generated day-5 card), the diary desk, the desk (tackle and belongings), the
bag, the kite record, the kite book, bug sumo and the insect box show every opaque texel of
each button's box in its rebuilt colour (but where the hand cursor covers it; the attendance
card within its dither), and the stock image fails every one.

## Measured while looking at the rest of `GFX-07`

What remains of the row is listed in `PLAN.md` `GFX-07`; these are the facts it rests on.

* `FS_WAL`, the fishing record: its labels sit beside numbers the game draws at run time over
  the texture's own `.` and `cm`, so the English has to be laid out against the screen, not
  just the atlas. Opening the tackle box from the desk (△, cursor on it, ○) does nothing on a
  generated day-5 card, which is story-naive (no rod yet).
