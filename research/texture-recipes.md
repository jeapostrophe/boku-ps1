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
| the bag (`PK_WAL`) | *Belongings* +28 and the two page balloons +4, all moved into the empty rows 154–239 of page 14 | the page balloons are drawn only by an idle hint nothing calls (recon); built so no Japanese is left if it is |
| kite record (`TK_WAL`) | *Fly a // Kite* | fits |
| fishing record (`FS_WAL`, 4bpp, CLUT 0) | *Fishing // Tackle* in Bean | no free texels measured |
| kite book (`TZICON`, a true 4bpp TIM 12 VRAM words wide) | *Make*, fits as it is | no free texels |
| bug sumo (`M_S01100` `0x164b4`, CLUT 2; `MUSI.OVL` 22-byte records from `0x8007A538`, `{u16 semi, s16 x, y, u8 u, v, u16 w, h, u16 tpage x, y, clut x, y, u8 depth, abr}`, one per balloon in each of the two tables) | *Release* +12 and *Bug // Rank* +8 into the free x 484–511; the rest fit; the swap plate (4bpp, slice 3, record `0x8007A7B4`) +8, set by the `plate` recipe (its ground is a checkerboard: refilled from donors an even number of steps away, only its text area, not the arrow); the とじる board (8bpp, CLUT 5, records `0x8007A742`, `0x8007A786`) by the `plank` recipe, its punched-through Japanese transparent | the stone on this screen is drawn through a CLUT not in its TIM |
| insect box (`MZ02`, CLUT 4, the same texture as `SAMP.BIN`'s copy; `SAMP` `0x14e48`, CLUT 6 slices 0–1) | *Bug // Cage*, *Bug // Box*, *Take // Out* in the game's glyphs; the rest in Bean (*Page // Next* would fit the game's glyphs, but its pair *Page // Back* shows beside it and does not) | no free texels (one 44×40 slot at x 684, y 160, and nothing wider) |

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
card within its dither), and the stock image fails every one.

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
