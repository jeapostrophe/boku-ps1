# Texture recipes — English typeset into textures at build time (PLAN `GFX-07`, `GFX-08`, `GFX-09`, `GFX-12`)

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

**Seen on Beetle** (2026-09-23): the album is reached from the title menu only with a card
holding a *finished* game (`boku save --finished`, [save-format.md](save-format.md)); Summer
Memories → the file → "is this file all right?" → yes opens it by ~5900 frames
(`tests/test_real_texture_text_beetle.py`, `ALBUM_PRESSES`). The heading's box lands at screen
(36, 24), drawn exactly; every texel the build changed shows its colour, and the stock image
fails. The album's stone "Back" matches `T_CONFIG`'s and `M_S01001`'s texel for texel, so
which of the loaded copies it is drawn from is not told apart; `T_MEMORY` child 0's own copy
is built with the other stones.

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
  x 489 is just past the right edge. That last column is not wood: it is another region's
  entry (175 in `C15000`, 177 in `C15100`), 0x0000 through CLUT 5 -- transparent -- and a
  refill that takes donors from it lets what lies behind the board show through, red specks
  on Beetle, which a Beetle comparison skipping transparent texels cannot see. No line box
  reaches it.

So it is programmatic, like the plates: the type (pale, through CLUT 5) is painted out along
the wood's horizontal grain, and the English painted in the white the Japanese used most, at
2× the game's glyphs (the Japanese is ~22 px with 2 px strokes). Line boxes: x 387–488 rows
18–47 (the bird and wave end at x 385) and x 334–488 rows 50–77. The English is worded to fit
the part of the board on screen (Jay, 2026-09-24: the sign is too small for a cut
"...orbidden" to read as off-screen), so it is never cut: each line starts where its Japanese
did, moves left just enough to end at x 488 if it would run past it, and is refused if that
takes it out of its box. `beach_notice` does this to both atlases.

**Reaching it.** After a new game's opening movie the game enters the map named at
`g_movie_return_map` ([movies.md](movies.md)); poking `C15` into it during the movie
(`run_core.py --poke 5300:0x80036588=43313500` with `boot-to-dialogue.press`) lands day 1 on
this screen at frame ~6000. `C15100` is not reached that way on day 1; its board is checked
at the texture level.

**Proof.** `tests/test_real_texture_text.py` finds each line in both atlases, whole at 2× and
ending on screen, with no other pale type in the line boxes and no entry on screen that the
stock board did not show there. `tests/test_real_texture_text_beetle.py`
warps a texture-only image there and requires every texel the build changed on the visible
board to show its CLUT-5 colour exactly.

**When a translation rebuilds the map.** The board lives in child 6 of a map pack that also
carries event text. If a later day's translation grows `C15`'s text, the pack is rebuilt (and
perhaps relocated), and a patch at the board's old offset would land on the rebuild. The
build hands its texture patches to the reinserter (`boku.reinsert.plan(carry=…)`), which
applies each one that falls inside a rebuilt member to the rebuilt bytes, in the same child at
the same distance, and the build drops it from its own patches (`Plan.carried`). A patch into
the text table itself, or into a bare `EV.BIN` block, is refused.

## `M_I14000` — Saori's farewell note (PLAN `GFX-08`)

`_DATA_M_FILES.BIN_M_I14000.BIN__000214`, 320×240 8bpp, one CLUT: the whole close-up screen
(scene `E2860`, [textures-plan.md](textures-plan.md) § "The Wolf Girl's letter"). A spiral
notepad lies on a log, turned about 23° and a little foreshortened; the Japanese is four
vertical columns of handwriting across its horizontal rules, the pen dark grey with grey
antialiasing, and the page's top-right corner is curled over.

**The page's plane.** `boku/texture_closeups.py` treats the page as a flat rectangle, 100×123
upright with the spiral on the left, mapped onto the picture by the homography through its four
corners. Each corner is where two of the page's edges, fitted to the outline of its paper, meet:
(84.2, 73.7), (179.7, 35.9), (239.3, 140.3), (149.0, 181.7) — the top-right one off the paper,
under the curl. Read back upright through that map the rules come out level (within half a
pixel across the page) at the heights `NOTE_RULES` lists, 4.5–5.5 apart as painted.

**What the recipe does**, all in the text area — upright (11, 3) 86×119, right of the spiral's
holes:

* **The Japanese** is every group of pixels darker than luminance 150 that the area surrounds
  (the curl and the log reach into its top right from outside, and are left), plus the grey
  within two pixels of them that is darker than 215 and no bluer than grey — the paper round the
  writing is paler, and bluer toward the foot of the page. Grown by a pixel, it is refilled
  pixel by pixel from the nearest clean pixel **on its own rule**: walking along the page's
  horizontal in half-pixel steps, the first pixel whose upright height is within half a pixel of
  its own. So a ruled line stays a line and the page's shading, which runs in bands along the
  rules, keeps its bands.
* **The English** is the game's glyphs, set upright: the note's lines (at most five, split at
  ` // `) from x 14 with their capitals standing on every third rule from the fifth, the
  signature right-aligned on the twenty-first; a line is at most 83 px. Each picture pixel is
  sampled 4×4 in the upright plane for how much of it the English covers; the coverage, scaled
  by 1.5 (a one-pixel stroke off the grid covers two pixels by half, which reads grey beside the
  Japanese's strokes; `paint.bold` clogs at this size), mixes the pen over the paper under it,
  and the mix is matched to the nearest entry the page already uses. The pen is the entry the
  darkest tenth of the Japanese's stroke pixels use most — its core, (33, 41, 41); the
  darkest quarter's gave a mid grey (57) that read faint. A line that would be written off the
  paper — onto the curl or the log — is refused.

Only the Japanese, the pixel round it, and the English change; the rules, the shading and
everything off the page are the original's.

**Reaching it.** The real route is examining the empty camp from day 28. For a check, poking
`I14` into `g_movie_return_map` during the opening movie (`run_core.py --poke
5300:0x80036588=49313400` with `boot-to-dialogue.press`, as for `M_C15`) lands day 1 on the
close-up, drawn exactly at the screen's top-left, with Boku standing on it at x 146–172,
y 57–118.

**Proof.** `tests/test_real_texture_closeups.py`: the rebuilt page read back upright through
its plane holds each line of the tracked English (found by search, not by the recipe's
placement), every dark pixel on the paper is within two pixels of one, and every line stands
on its rule alike; the stock page fails. Where the Japanese was, the refilled paper is bluer
on a rule than between rules, as the untouched paper is; nothing outside the text area
changed. `tests/test_texture_closeups.py` checks the plane, and that a refill along a turned
page keeps each pixel's band where a refill along the picture's rows does not.
`tests/test_real_texture_text_beetle.py` warps a texture-only image there and requires every
texel the build changed (but where Boku stands) to show its colour exactly; the stock image
fails.

## Marker signs — `M_I18` and `M_S01000` (PLAN `GFX-08`)

Two images lettered by hand in coloured marker on a flat ground (Jay, 2026-09-24: G8-I18 and
G8-NB, option b — painted over by us in the game's glyphs, not redrawn):

* **The keep-out sign** (`_DATA_M_FILES.BIN_M_I18000.BIN__000450`, CLUT 0; `M_I18000` and
  `M_I18001` hold the same image): pink marker, a child's *はいっちゃダメ!*, on a white oval hung on
  the upstairs door. The texture is the whole 320×240 close-up and is drawn 1:1 at the
  screen's corner. English: *Don't // come in!*, both lines at twice the game's glyphs.
* **The bug-trading notebook's cover** (`_DATA_M_S01000.BIN__017d24`, CLUT 3): red marker,
  虫 / こうかん / ノート, inside the cover's printed frame, on the left of the bug-sumo desk.
  English: *Bug // Trading // Notebook* (glossary § 4b: 虫交換 is bug trading), the first line
  at twice the game's glyphs as the 虫 is large, the other two at their own size.

`paint_marker_sign` (`boku/texture_text.py`, table `MARKER_SIGNS`) finds the marker by hue, not
brightness — the pink is barely darker than the white — as pixels redder than the box's median
ground, and paints it and everything within `MARKER_REACH` of it out: the notebook's red has a
brown shading two rows under a stroke. What makes this harder than the beach is the notebook's
printed frame, which runs through the tail of ん and is broken by lighter texels into short
runs, so no run length tells it from a smudge; instead a dark group that reaches beyond the
marker's reach is the picture's own, and neither it nor its pale edge is painted out or used to
refill. Each pixel takes one nearby donor (`fill_from_nearest`), which keeps the tan's grain.

**Reaching them.** The keep-out sign: the beach's warp with `I18` (`KEEP_OUT_WARP`,
`tests/test_real_texture_text_beetle.py`) — the game enters the upstairs landing and plays the
locked door's close-up (`E0835`) by itself. The notebook cover: on the bug-sumo desk in the
records' single-card screen (`MARKER_SIGNS_ON`, `tests/test_real_texture_records.py`).

**Proof.** `tests/test_real_texture_text.py`: in each rebuilt image the marker's red holds
exactly the English, once; near where the Japanese was nothing is still red and no dark smudge
is left; and no colour of a picture line is refilled into the ground. On Beetle, the two tests
named above show every changed texel exact (the stock image fails).

## `M_I23000` — the hunting association's warning board (PLAN `GFX-08`)

`_DATA_M_FILES.BIN_M_I23000.BIN__000354`, 320×240 8bpp, one CLUT: the whole close-up screen of
the board on map `A14` (scene `E4045`). A frontal, weathered white board: キケン! in red on a
yellow starburst, 民家近し、 and 発砲注意! in ~20 px black painted strokes, 県狩猟組合 small in
the corner, and a cartoon of a hunter whose shot hits a man, its gun and two-line bullet trail
running between the two black lines. Jay (2026-09-24): a clean plate with the writing
removed, keeping the explosion's colours (an image model had changed them), then our text in
the game's glyphs.

**The clean plate.** `boku/texture_closeups.py` `board`, one `BOARD_SIGNS` row per piece of
writing: the box its Japanese is found in and the room its English may use (the thresholds
and the trail's fit are the `BOARD_*` constants, each with its measurement). The Japanese is
the red in the starburst's box, and in the other boxes the dark near-neutral groups that are
not specks of weathering, with the grey round them. The bullet trail (`BOARD_TRAIL`, a band
fitted to its two lines) is never taken for type. The writing, grown a pixel, is refilled from
the nearest pale board pixel (a row away counting as two columns, `Canvas.fill_from_nearest`),
so a stroke across the yellow burst is refilled with the burst's own yellows and one on the
board with the board's whites and weathering; the trail, the gun, the man and the dirt are
never donors, and never change.

**The English**, in the Japanese's own black and red (`pen`: the entry the darkest tenth of its
strokes use): the three large lines are the game's glyphs twice as tall and emboldened, each
letter set on its own so a column of air stays wherever two would touch side by side
(`emboldened`; `paint.bold` of a whole line runs "m" into its neighbours). Twice the glyphs'
size does not fit: "Homes nearby," would be 178 px where the board has ~90 between the burst
and the trail. At their own size, emboldened, they read but are half the Japanese's height
(`BOARD_TALL = False`, the alternative shown to Jay). The corner is the glyphs as they are,
two lines. Each line goes where its Japanese was — the houses line from its left edge, the
association from its right, the others centred — or the nearest place in its room clear of
the drawing: no pixel of the English, or the pixel round it, on the trail, on a group of dark
pixels big enough to be drawing and not the Japanese, or on anything saturated but the burst's
yellows (the black type is painted over the burst's lower spike, as 民 is), and a pixel clear
of the English already set. The trail pushes the shooting line ~9 rows below its Japanese,
and the corner's two lines go under it. A line with no such place is refused, and so is a
line break where a sign has one line.

**Reaching it.** As for `I14`: `g_movie_return_map` poked to `I23` during the opening movie
(`--poke 5300:0x80036588=49323300`) lands day 1 on the board, drawn exactly at the screen's
top-left; Boku is not seen on it.

**Proof.** `tests/test_real_texture_closeups.py`: each line's English, as the build sets it
from the tracked string and the disc's glyphs, is painted whole, once, in its room and paint,
and no group of ten or more pixels of that paint is left in any box but the English and the
trail — the trail fitted by the test itself where it crosses open board, not taken from the
recipe; the stock board fails. Only the boxes and rooms changed; the trail's lines are the
original's; the starburst's refill is only entries the burst had, none red, and nine in ten of
the red Japanese's pixels are yellow again (the rest, the top of its "!", ran onto the board).
Too wide a line, a line break where a sign has one line, an empty line, and a room the trail
crosses (and that the same line takes once the trail is moved away) are refused.
`tests/test_texture_closeups.py` checks `emboldened`. On Beetle
(`test_a_closeup_on_beetle_is_the_written_english`) every texel the build changed shows its
colour exactly; the stock image fails.

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
| insect book | `MZKAN` `0x48` | texture origin (256, 202) |
| fishing record | `FS_WAL`, 4bpp | texture origin (204, -10) |

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
has free texels, and in Bean where it has none (Jay's ruling, 2026-09-23); and a button is in
Bean or Sprout only where the game's glyphs do not fit it (Jay, 2026-09-24: mixing faces looks
bad), which `tests/test_real_texture_buttons.py` checks through the recipe. Only one balloon
shows at a time on every screen here, the one for the item under the cursor.

**Widening** (`Widen`, `layout`) repeats the pair of columns at the balloon's centre (a pair,
so a dither keeps its phase), may set the widened art down elsewhere in texels that are
transparent or were widened balloons' own (a repack), and grows — and moves — every stored
size of the sprite, each checked against its measured bytes first. A sprite may not cross a
256-texel page.

| screen | balloons | how |
|---|---|---|
| diary desk (`NIKKI_W`) | おやすみ *Good // night* | widened 4 (atlas entry 6, 12 bytes in front of the TIM); the idle hint, drawn at (40, 16) while `0x80047E50` is set, after 61 frames with no input |
| desk (`SUB`, CLUT 1 slices 2–3; table 0xB4 in front of the texture) | the tackle, cage, glove and net band (page 14, rows 211–250) repacked: tackle +12, glove +4, the others moved right; *Stuff* (Belongings), kite and back fit as they are | `SUB.BIN` is loaded once at boot (resident), so a state saved on another image shows the old desk |
| the bag (`PK_WAL`) | *Stuff* (Belongings) fits as it is; the two page balloons +4, moved into the empty rows 154–239 of page 14 | the page balloons are drawn only by an idle hint nothing calls (recon); built so no Japanese is left if it is |
| kite record (`TK_WAL`) | *Fly a // Kite* | fits |
| fishing record (`FS_WAL`, 4bpp, CLUT 0) | *Fishing // Tackle* in Bean | no free texels measured |
| kite book (`TZICON`, a true 4bpp TIM 12 VRAM words wide) | *Make*, fits as it is | no free texels |
| bug sumo (`M_S01100` `0x164b4`, CLUT 2; `MUSI.OVL` 22-byte records from `0x8007A538`, `{u16 semi, s16 x, y, u8 u, v, u16 w, h, u16 tpage x, y, clut x, y, u8 depth, abr}`, one per balloon in each of the two tables) | *Release* +12 and *Bug // Rank* +8 into the free x 484–511; the rest fit; the trade plate (4bpp, slice 3, record `0x8007A7B4`) +10 for *Trade* (35 px), set by the `plate` recipe (its ground is a checkerboard: refilled from donors an even number of steps away, only its text area, not the arrow); the とじる board (8bpp, CLUT 5, records `0x8007A742`, `0x8007A786`) by the `plank` recipe, its punched-through Japanese transparent | the stone on this screen is drawn through a CLUT not in its TIM |
| insect box (`MZ02`, CLUT 4, the same texture as `SAMP.BIN`'s copy; `SAMP` `0x14e48`, CLUT 6 slices 0–1) | *Bug // Cage*, *Bug // Box*, *Take // Out* and the page pencils' *Prev* / *Next* (Jay, 2026-09-24) in the game's glyphs; the rest in Bean | no free texels (one 44×40 slot at x 684, y 160, and nothing wider) |

**The insect cage** (`MITIM`, a true 4bpp sheet, 10 CLUTs). Its sprite table is `KAGO_UV.BIN`
(`u32 18`, then the table's 12-byte entries): `cage_init` (`0x80043468`) loads `MITIM` to VRAM
(0x250, 0x100) with its CLUTs at (0x270, 0x1E0) and converts `KAGO_UV` against that place, so
its 18 records are `MITIM`'s sprites — the crowns (11–14), `BIG!` (0–1), `NEW!` (9–10), the
male/female marks (6–7), the hand cursor (17), and the three with Japanese:

| sprite (record) | rect, CLUT | where | English |
|---|---|---|---|
| leaf 出す (2) | (24, 80) 40×24, CLUT 1 | ○ on a bug in the cage view: the left of two buttons, at screen (216, 192) | *Take*, bold, the `stone` recipe (its ink read darker than 90: the leaf's ramp is lighter and its type's faint tails reach 85) |
| stone もどる (8) | (24, 104) 40×24, CLUT 4 | beside it at (264, 192), the hand cursor above it | *Back*, bold, the `stone` recipe — a smaller stone of its own drawing |
| starburst 希少 (3–5) | (0, 0/24/48) 32×24, CLUT 2 | the cage header, at (193, 20), for a rare bug (a type in the list at `0x80045B04`, each stored +1), turning a frame every four draws (`0x80045B24`): each frame is on screen 8 video frames, measured on Beetle | *Wow!* in the game's glyphs (Jay, 2026-09-25: the burst is there to excite), the `badge` recipe, the same in each frame (`Button.frames`) |

Every word on the sheet is the game's glyphs, one face on the screen: 出す as *Take* (Jay,
2026-09-24: *Take // Out* in Bean, with *Back* beside it in Bean, "looks bad"), and 希少 as
*Wow!* (2026-09-25), 29 px against the Japanese's 23. The `badge` recipe works on the whole
32×24 sprite, the Japanese's area its `text`: the type there is what is redder than the burst's
yellow (`BADGE_RED`), and what is dark but not the burst's outline; it is refilled from the
opaque burst round it, so its own shading comes back (the notches run into the type, so not
only from the burst's inside as a stone's is). The English is set at its own weight in the red
the type used most, over a drop shadow one pixel down and right in the dark it used most (the
game's text shadow), centred where the Japanese was, running onto the spikes and the
transparency beside them; a word that would leave the sprite is refused.

**The attendance card** (`PK_ITM` `0x6c`, item 0x6c; seen in the bag, drawn dithered: every
texel its colour or 8 less on each channel). Its title (beside the radio picture) and its
footer (under the grid) are printed blue on a near-white card whose ground turns faintly pink
toward the bottom, so the `label` recipe finds the type by saturation (not the tinted fringe
of the punched hole in its corner), clears the whole of its rectangle grown a pixel (Jay,
2026-09-23: the mock-up had painted over the Japanese) — refilled from the card beside it in
the same rows, so the grid's pale shadow one row above the footer is not drawn down into it,
and on the flat title ground that is the paper itself — and sets the English in Sprout, in
the type's own blue: *Radio // Calisthenics // Attendance Card* beside the picture (its box
stops a column short of the picture's frame) and *Have a healthy summer!* under the grid
(Jay, 2026-09-24), without the reference marks ※ the Japanese has around it.

**Proof.** `tests/test_real_texture_buttons.py`: each stone's dark pixels are exactly its
English bold in the disc's glyphs (only its outline besides), each balloon's type exactly its
English lines, each board's dark pixels and each card label's printed pixels exactly its
English, each widened sprite's stored sizes grown and moved; on Beetle (`./make.sh emu-test`)
settings, load (a generated day-5 card), the diary desk, the desk (tackle and belongings), the
bag, the kite record, the kite book, the insect book, bug sumo and the insect box show every opaque texel of
each button's box in its rebuilt colour (but where the hand cursor covers it; the attendance
card within its dither), and the stock image fails every one; the cage's buttons and its
rare starburst (a rare bug poked into cage slot 0, whichever frame of the burst is on screen)
likewise.

## `OTI0n` — the epilogue's closing card (PLAN `GFX-10`)

`_DATA_OTI00.BIN__0261f4`, 276×33 4bpp, one CLUT of greys, the same TIM in each of
`OTI00`…`OTI04` (one per ending), so one set of edits covers all five. It is the last card
`ENDOTI` shows ([event-scripts.md](event-scripts.md) § the epilogues): two centred lines of
pale grey antialiased type on transparent, 製作・著作 (rows 0–11) and the company's name
(rows 20–31), drawn on black. It is a still, not video — measured on Beetle, stock image,
day-31 card with no stars: `MOVIE 24`'s scrolling staff credits run ~29000–30500, which stay
Japanese (they are video), then `ENDOTI`'s stills, then this card at ~32200–32450, then the
save prompt. It is drawn exactly (no dither; where it lands is the Beetle test's `ON_SCREEN`).

`credits_strip` (`boku/texture_text.py`, strings `tex@OTI.production` / `tex@OTI.company` in
`ui.txt`) clears the card to transparent and sets each English line in the game's glyphs,
centred on the rows its Japanese used, in the grey the Japanese's pale core used most.

**Proof.** `tests/test_real_credits_card.py`: the card's opaque texels are exactly the two
English lines, and all five copies are edited; on Beetle (`./make.sh emu-test`) the ending
route shows every texel of the card exactly; the stock image fails it.

## The books — the insect and kite encyclopedias (PLAN `GFX-06`)

`boku/texture_books.py`; the English is `mzkan@<n>.<field>` and `tzkan@<n>.<field>` in
`translation/textures/books.txt`. The insect book is nine 252×188 8bpp spreads, the same nine
in `MZKAN1` (by day) and `MZKAN0` (by night, other indices and palette), page n of each the
same species, so each English page is set into both; the kite book is eight 244×186 spreads in
`TZKAN`. Both are drawn dithered (every texel its colour or 8 less on each channel, as the
attendance card) at texture origin (38, 23) for the kite book and (45, 23) for the insect book
— measured on Beetle with the book modes forced by hand (mode 12 and 13, the diary's pokes).

Every text area was found by classifying every pixel of every page of the pack: furniture
(the photograph, the green rules; saturation over `FURNITURE`), ink, paper — and taking the largest
rectangles no page has furniture in:

| area | box | set |
|---|---|---|
| insect name, on the grey of the right page's curled top edge | (140, 12, 111, 13) | the game's glyphs, centred; Bean where they do not fit (*Great Purple Emperor*, 128 px) |
| insect header: family, size, likes | (140, 27, 108, 60) | Bean, each field wrapped and centred |
| insect body, left page under the photograph | (8, 96, 120, 77) | Bean, left, the first lines |
| insect body, right page under the rule | (130, 95, 118, 78) | Bean, left, the rest |
| kite page: the right page and the left page's last column | (106, 13, 134, 159) | cleared; the name (game glyphs), `[level]` (Bean) and body (Bean) set in (128, 14, 110, 156) |

The Japanese body runs in vertical columns from the right page to the left; the English runs
down the left page and on to the right, as an English book reads. A body area is blanked whole
first, each column to the paper that column shows most, so the shading toward the spine
stays. The name and header straddle the diagonal edge of the grey curl at the page's top, so
there only the pixels that are not one of the area's paper entries (white, the curl's grey —
the entries covering `PAPER_SHARE` of it) change, each refilled from the nearest that is. The
Japanese running out of an area goes too: its first strokes start on the photograph's sloping
lower edge, above the box, and its last end on the rule at the foot. A mark darker than the
paper outside the box is the Japanese's when it is paper all round and within `GAP` pixels of the
box or of a stroke already found; a group touching the photograph or a rule is the page's and
stays (a first build that cleared by darkness alone took dull stretches out of twelve
photographs). With Bean at a pitch of 9 the longest bodies fill the spread (the insect pages
hold 16 lines); a page that does not fit is refused, never cut.

**Proof.** `tests/test_real_texture_books.py`: on every page, in both lightings, each text
area's dark pixels are exactly as many as its English lines ink; outside the areas only strokes
of the Japanese change — no pixel next to the photograph's or a rule's colour — and no stroke
is left across a body's edge; the curl's white and grey stay under the name and header. On
Beetle (`./make.sh emu-test`) both books open on page 0 with every texel of the text areas as
rebuilt, within the dither; the stock image fails both.

## Records — labels beside numbers the game draws (`FS_WAL`, the notebook's card)

`boku/texture_records.py`; the English is `rec@<member>.<key>` in
`translation/textures/records.txt`. A label's Japanese rectangle is cleared (its ink, and the
shadow and antialias darker than the paper, refilled from the nearest paper) and its English
set in a measured room against the number the game prints beside it: a label before a
number ends at its room's right edge, one after a number starts at its room's left edge.

**The fishing record** (`_DATA_FS_WAL.BIN__0000d8`, 8bpp, CLUT 2), from the desk's tackle box.
It opens only once the rod is owned — `g_flags[10]` = 1; a story-naive generated card has it 0,
which is why the tackle box did nothing — and shows the catch once any fish has been caught:
the catch record at `0x8003E0B0` is 3 fish × `{u8 picture, u8 count, s16 average mm, s16
largest mm}` (Iwana, rainbow trout, yamame), saved (body offset 1196). `g_flags[53]` picks the
four-row tackle list over the three-row one. Route: △ (the desk, cursor on the belongings) →
RIGHT → ○ (the tackle box) → LEFT (into the list) → DOWN ×4 (the summer's catch).

| sprite | texture | screen | English |
|---|---|---|---|
| the field labels' plate | (72, 64) 112×48 | (176, 124) | *[count] fish* (Sprout: 14 px between the count and the plate's edge), *Size*, *Average* and *Largest*, each ending where the number starts |
| tackle list, 4 rows / 3 rows | (48, 154) / (136, 112), 88 wide | (48, 96) | *Bait (Worm)*, *Bait (Worm) + Float*, *Tenkara (Small Fly)*, *Tenkara (Large Fly)*, Bean |

The numbers are the game's (`FUN_80044008` → `FUN_800402d8`, 7-px digit cells): the count at
screen x 260, the average and largest whole parts at x 250 with their tenths at 268, after the
texture's own `.` and before its `cm`, which stay. The tackle words and しかけ / 夏休みの釣果 /
the fish's name / the tackle's description are drawn text (`TXT-05`'s). The screen's balloon
つり道具 (4bpp, slice 0 at (0, 200)) and its stone are in § "Buttons".

**The bug-trading notebook's record card** (`_DATA_M_S01100.BIN__0164b4`, 4bpp, CLUT 2), at the
bug-sumo desk: the offered bug's card alone (the MUSI record `0x8007A758`, texture (512, 0),
slice 5, at screen (124, 48)) or over the held bug's (`0x8007A79C`, (256, 0), slice 4, at (124,
18); the second card 106 rows below the first). The notebook's offer is saved (`0x8003DE18`,
body offset 740). Each card reads *[size]mm Caught 8/[day]* / *[wins] W [losses] L* / *Worth as
many as* / *[6.4] Saw Stags*: "Caught 8/" ends where the day starts, and the day's 日 is cleared
with nothing in its place (an English date needs none), W and L are the glossary's, and
ノコギリクワガタ換算で … 匹の価値 — its value converted into saw stag beetles — is the last two lines. The type
has a drop shadow, and so does the English. The numbers are the game's (MUSI `FUN_8007e670`,
`FUN_80080888`).

**Proof.** `tests/test_real_texture_records.py`: every label at every place it is drawn holds
exactly its English, in its face, once, with nothing of the Japanese; on Beetle the fishing
record (a card with the rod and three fish), the single card and the pair (a card with an
offer) show every texel of every label as rebuilt, and the stock image fails.

## Bug sumo's bout — the banner, the stamina plate, the rank mark (PLAN `GFX-12`)

`boku/texture_sumo.py`; the English is `sumo@<part>.<key>` in
`translation/textures/sumo.txt`. Three things a bout draws from the desk's textures, none of
which the census saw ([textures-plan.md](textures-plan.md) § "What the census could not see").
Measured on Beetle, 2026-09-30, by walking the ordering table in a RAM dump at each moment of
a bout (`g_ot` `0x8002593C`) and reading the primitives' texture pages, CLUTs and corners.

**Where the desk's textures are.** `M_S01000` `0x17d24` is uploaded at VRAM (320, 0) and
`M_S01100` `0x14` at (320, 272): the two halves of the desk, both drawn through the CLUT at
row 241, which is `M_S01000`'s CLUT 1 and `M_S01100` `0x14`'s CLUT 0 — the same 256 entries.
`M_S01100` `0x164b4` is at (832, 0), its six CLUTs at rows 245–250. A 4bpp sprite cut from
`M_S01000` uses the page at (448, 0), so its `u` is its canvas x less 512
(`Canvas(drawn_4bpp=True)`, § "Buttons").

### The winning-move banner

When a bout ends the ring is veiled by a grey band and two strips of white brush lettering
fade in over it: the heading 決まり手 and how the bout ended. The strips are 4bpp sprites in
the first 256×256 page of `M_S01100` `0x164b4` — that page holds nothing else — drawn
through CLUT 2's third 16 entries (VRAM (288, 247)): entry 1 white, 2–7 greys, 8 near black,
the rest unused.

* **Retail's page**: 20-texel columns of vertical lettering, eleven from row 0 (143 tall; the
  heading is the first, drawn 128 tall) and twelve from row 144 (111 tall).
* **Which strip.** How the bout ended is a number 0–21 (`0x8008EFC0`), and `MUSI.OVL`'s 22
  bytes at `0x8007A2F0` give its strip: 0 → 20 (押し出し, the push-out), 1–8 → 1–8 and 9–17 →
  11–19 (the seventeen moves of `musi@2C.13`–`.29`, in order), 18 → 21 and 19 → 10 (the two
  mantis moves, `musi@2C.30`, `.31`), 20 → 9 (両者、引き分け, a draw — shown alone, with no
  heading), 21 → 22 (スタミナ勝ち, won on stamina). So the banner is what retail shows in
  place of the move-name array, which nothing draws ([sumo.md](sumo.md) § "The desk's text").
* **How it is drawn.** `0x8008659C` fills the heading's record at `0x8008F2D8` and
  `0x800865F8` the move's at `0x8008F2F8`: halfwords `u, v, w, h, x, y, drawn w, drawn h`,
  then the texture page (832, 0) and the CLUT, and at `+0x18` how far it has faded in. The
  heading is at (163, 42) and the move at (142, 46) — (150, 46) for the draw. `0x800867DC`
  draws them through the executable's `0x80036DE0`, which emits the quad twice: subtracting
  white through an all-white CLUT at (256, 271), then adding the strip, both scaled by the
  fade — so at full fade a strip's texels are on screen exactly, opaque. That routine reads
  `u, v, w, h` as halfwords and hands the GPU their low bytes, adding `u + w` and `v + h`
  **in a byte**: a strip must end by texel 255. The veil is a
  half-transparent grey rectangle whose `x, y, w, h` are the four halfwords at `0x8007A308`
  (130, 35, 60, 140), drawn by `0x800866BC`.

**What the recipe does.** English does not stand on end, so the banner is turned on its side
(the alternative, the lettering turned a quarter as the settings chart's headings are, needs
no code; Jay's decision page has both). Each real technique is shown as its Japanese name over
an English gloss, `sumo@move.gloss-N` (`GLOSSED`; Jay, decisions § 29b, PLAN `GFX-15`): three
lines, heading, name, gloss. Every line is the game's glyphs, each letter emboldened with a
column of air kept between letters (`boku.texture_closeups.emboldened`), centred, in the white
the lettering used most, every pixel round it in the darkest entry the page used; a line wider
than its strip less the edge (122 px, the heading 88) is refused, and so is a gloss whose
letters would touch the name's.

* **The strips.** A bold line's ink is rows 1–10 of the glyphs' 12-row cell (all but `j`'s
  dot, on row 0 — the refusal above), so two lines 11 rows apart keep one dark row between a
  descender and a capital: a strip is 124×23, the
  name's cell from row 0 and the gloss's from row 11. A move with no gloss (the five jokes, the
  draw, the stamina win) has its name midway, its cell from row 6. The page is cleared and the
  22 strips set down it in two columns, cells 0–10 from (0, 0) and 11–21 from (128, 0), 23
  rows apart: 253 rows a column. `0x8007A2F0` is rewritten with each move's strip one earlier
  than retail's, the heading's cell 0 having left the page.
* **The heading** is one line, 90×12, in the free corner of the atlas's third page (canvas
  (599, 160) to the bottom right at 4bpp, empty beside the portraits the 8bpp view shows) at
  (602, 192): page `u` 90, `v` 192. Its routine stores `u` from `$a1`, the register that holds
  its width, and `v` from `$v1` while it holds the page's x, 960, whose low byte is 192 — which
  is why the heading is where it is.
* **The code: 26 words of `MUSI.OVL`** (`banner_code`), each checked against retail's before
  it is written. The heading's routine (`0x8008659C`) keeps its length: `0x800865A0`, which
  zeroed `u`, loads 960 into `$v1`; `0x800865A8`/`AC` the width and height; `0x800865B0`
  stores `$v1` as `v` and `0x800865B4` as the page's x, where retail placed `x`;
  `0x800865B8` the heading's `y`; `0x800865C0`/`C4` load and store `x` where the page was;
  `0x800865D4`, which zeroed `v`, stores `u` from `$a1`. The move's routine (`0x800865F8`):
  `0x8008661C`, the branch's delay slot, sets the strip's height once for both columns;
  `0x80086620` jumps the first column to `0x80086630`, its delay slot `0x80086624` zeroing
  `u`; `0x8008662C` gives the second column `u` 128; `0x80086630`–`3C` compute the cell's `v`
  as 24c − c (`c << 1`, plus c, `<< 3`, less c), where retail's three words made 20c; then, as GFX-12
  made them, `0x80086648` stores the stepped value to `v`, `0x80086660` the picked one to
  `u`, `0x8008664C`/`8C` the width, `0x80086670`/`74` the draw's and a move's `y`, stored as
  `y` by `0x80086678`, and `0x80086684`/`88` the shared `x`. Data: the 22 bytes at
  `0x8007A2F0` and the veil at `0x8007A308`.
* **On screen** the heading is at (115, 89) and a move's strip at (98, 109), so the heading and
  the name are exactly where GFX-12 drew them; the draw's strip is at (98, 99), centred in the
  veil, and the veil is (90, 80, 140, 61), eleven rows taller, so the gloss has the room under
  it the name had.

### The stamina plate

The HUD of a fight is five quads from 28-byte records in `MUSI.OVL` (`s16 x, y` at +2,
`u8 u, v` at +6, `s16` drawn `w, h` at +8, `u8` texture `w, h` at +0xC and +0xE, then the
texture page and CLUT), drawn by `0x800828C0` through the executable's `0x80036BEC`: the left
bar's fill `0x80079DB0`, the right bar's `0x80079DCC`, the plate `0x80079DE8`, the left
frame `0x80079E04` and the right `0x80079E20`. All are 4bpp sprites of `M_S01000` through
CLUT 0 (the frames and the plate through its second 16 entries, the fills its first). The
plate is 36×20 at canvas (592, 193): a framed brown face, 31×15 from (2, 2), with スタミナ
raised on it in tan over a darker shadow.

The HUD slides in closed, then opens: a counter at `0x8008F284` falls by one a frame from
0xA0 to a floor of 0x8C while the plate's drawn width (`0x8008F286`) rises by two, to 40, and
the bars part with it — so retail draws the plate's 36 texels 40 wide. At rest the left frame
is at x 40, the plate at 136, the right frame and fill at 180, all at y 130.

**What the recipe does.** *Stamina* in the game's glyphs is 46 px and the face holds 31, so
the plate is widened by 20 texels (the pair of columns at its centre repeated, its face
cleared to the ground first), set down at canvas (652, 210) — texels no sprite used — and its
old place cleared. The word is raised in the entry the Japanese's light pixels used most,
over a shadow one pixel down and right in the entry its dark ones did. The plate's record
takes the new `u, v` and width, and the plate is drawn as wide as it is: the counter's floor
drops by 8 (`slti` at `0x80082954`, the `addiu` at `0x80082C0C`), so the plate opens to 56
over 28 frames, and each bar's resting place moves out by 8 (the three `addiu`s at
`0x80082C4C`, `0x80082CCC`, `0x80082CF0`; the two right-hand records' `x`). The slide-in
starts where retail's does.

### The rank mark

Left of the ring the opponent's rank is chalked on the desk in a ring of chalk, a stick of
chalk lying across its top right: 弱, 強 or キング. Each is a 64×56 drawing at 8bpp. 弱 is
painted into the desk itself, `M_S01000` (200, 27); the other two are sprites of `M_S01100`
`0x14`, at (256, 133) and (256, 77), drawn over it at screen (10, 27) with the desk scrolled
to the ring (`0x8008EFC8` the rank). The three rings are three different drawings.

**What the recipe does.** Per mark, an ellipse that the ring's inner edge follows is measured
by hand (`RANK_MARKS`); inside it, and outside the stick's box, every pixel lighter than the
desk's wood (chalk and its dust) is refilled from the nearest wood, and the rank is written
at the ellipse's centre in the game's glyphs, emboldened, each pixel in the chalk of one of
the old writing's own pixels so the word is as uneven as the ring. The ring, the stick and
the desk are untouched. A word that does not fit inside the ring is refused (*Strong*, 45 px,
is a pixel inside the ellipse at each end; twice as tall it does not fit).

**Reaching them.** The card with the mantis beaten (`shortcut-open`, slot 3 of
`boku-bug-sumo.mcd`): at the desk take a bug out, go to the ring, LEFT to the rank board and
choose a rank, put the bug down, ring the gong, tap △ until the bout ends
([sumo.md](sumo.md) § "Reaching a bout"). The banner is up once both records' fades read
0x80.

**Proof.** `tests/test_real_texture_sumo.py`: each strip, found through the import's own
table, is exactly its move's name — over the gloss `sumo.txt` gives it, or alone midway — and
the page holds nothing else; the heading is exactly its English, in texels that were free;
the two routines, run on the built `MUSI.OVL` (`tests/mips.py`), fill the heading's record
and each of the 22 moves' with its strip's box and place; utchari's first gloss is refused as
too wide; the plate's raised type is exactly the word, its frame the stock plate's, its old
place blank; inside each ring the only chalk is the rank, and nothing outside the ring
changed. On Beetle (`./make.sh emu-test`) a King bout that ends in the push-out shows every
texel of the mark, the plate, the heading and the strip, name and gloss, as rebuilt; the
plate opens to 56; and the two records hold the new places — with the move's `y` word left
at GFX-14's value the test fails on the record, and the strip's texels are 4 rows off on
screen. `tests/test_texture_sumo.py` holds the layout (the 22 strips and the heading end by
texel 255 and share none, the heading where its routine's registers put it and centred as a
strip would be), the lines and the refusals, the banner's wording to the move-name array's,
and each technique as one word.

## The kite-flying HUD — three labels over the compass and the numbers (PLAN `GFX-13`)

`boku/texture_kite.py`; the English is `kite@hud.<key>` in `translation/textures/kite.txt`.
Found by `GFX-12`'s sweep ([textures-plan.md](textures-plan.md) § "What the census could not
see"). Measured on Beetle, 2026-09-30, from the ordering table of a RAM dump with a kite up.

**The sheet.** Kite flying (`TAKO.OVL`, mode 6) loads one of two packs, file
`0xF0 | (hour >= 15)` (`0x8007A1A4`, the hour the byte at `0x80028FC1`): `TBG00` by day,
`TBG01` from 15:00. `0x8007F800` uploads a pack's three TIMs: child `0x1c` to VRAM (320, 0)
with its CLUTs at (256, 240), the other two — the backdrop — to (832, 0) and (320, 272). Child `0x1c`'s header says 8bpp 240×240; its left 110 columns are
an 8bpp picture, the panel Boku stands in, which differs between the packs (CLUT 1, drawn at
the screen's corner), and from canvas x 256 as 4bpp it is the same sheet in both, the
texture page at VRAM (384, 0), so a sprite's `u` is its canvas x less 256: the kite reels
(rows 0–119), the digits `1234567890` (row 120, 12 texels each), then on row 136 the three
labels 風向, 風速, 高度 in 32-texel sprites and the units `m` and `m/h`, and under them the
compass and its needle. The labels, digits and units are drawn through the CLUT's first 16
entries: 0–6 white to grey, 7 and 8 transparent, 9 near black. Right of the units (canvas
x 400–479, rows 120–151) and of the needle the sheet is entry 0 throughout, and no record of
the HUD points there.

**How it is drawn.** Every HUD sprite is a 22-byte record in `TAKO.OVL` — a `u16` (1 in the
labels', 0 in the last unit's, which is drawn all the same), `s16 x, y`, `u8 u, v`,
`u16 w, h`, then the texture page's and the CLUT's VRAM places — handed to the executable's
`0x800368C8`. `0x8007A510` draws the three labels from
`0x80079A8C` (at x 143, 188 and 265, y 190) and `0x8007A480` the three units from
`0x80079A48`; the digits are drawn beside them at y 205. On screen 風向 stands to the right
of the compass, 風速 over the wind's speed (`4.0m/h`) and 高度 over the kite's height
(`22 m`); the length of line let out, bottom left, has a reel for its label.

**What the recipe does.** On both sheets the strip the Japanese was in (canvas
(256, 136, 96, 16)) is cleared to its transparent entry and each label is set in a cell of
its own in the game's glyphs — the white the Japanese used most, every texel round it in the
strip's darkest entry, capitals standing on the row the kanji stood on. A cell is as wide as
the screen has room for with the label kept centred where the Japanese was: direction 32
texels where it was, speed 40 from canvas x 288, altitude 48 at (400, 136) in the free
texels. Each record takes its cell's `u` and width and an `x` that keeps its centre. A label
that with a texel of edge all round does not fit its cell is refused.

**Reaching it.** `mode_set(6)` by hand after a new game's first dialogue
(`tests/test_real_texture_buttons.py`'s `mode`, the arena level B): the kite is up and the
HUD drawn within 300 frames, with no kite owned; the hour byte set to 15 with it loads
`TBG01`. The desk's "Fly a Kite" opens only the list of kites owned, not a flight. Besides
the three labels the screen draws only renderer text — △'s menu `tako@4` and the crash
banner ([vwf-prototype.md](vwf-prototype.md) § "The banners") — English in the days build.

**Proof.** `tests/test_real_texture_kite.py`: on both sheets each cell is exactly its label
with its edge, nothing is left of the strip outside the cells, and no other texel changed;
each record holds its cell and keeps retail's centre. On Beetle (`./make.sh emu-test`), once
over each pack (the panel on screen must be that pack's), every opaque texel of the three
cells is on screen where its record puts it — with the records left as retail's the speed
label fails it. `tests/test_texture_kite.py` holds the layout — no two cells share a texel or
take a unit's, no two labels overlap on screen — and the narrowest fit and refusal.
