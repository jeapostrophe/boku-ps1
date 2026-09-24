# Textures — the path chosen for every image that carries Japanese (PLAN `GFX-03`)

`REC-08` counted the Japanese in the pixels ([textures.md](textures.md),
[data/texture-census.tsv](data/texture-census.tsv)): **180 distinct images `yes` + 17 `maybe`
= 197**. (Ruling 2026-09-22, Jay: the model-kit box `M_I19000` stays Japanese — the narrator
says what it is — and 2026-09-23, `GFX-09`: the beach notice is frontal, not at an angle, and is
in both variants of its map, so it is **P** twice; and `GFX-10`: the epilogue's closing card is translated, **P**;
and 2026-09-24, `GFX-08`: Saori's farewell note is built programmatically, **P** — the
counts below are now **142 P, 26 R, 0 S, 30 N** of 198; the tables keep the audit's original
split.) This file assigns each of those 197 a **path**, and says where the English comes from.
The per-image table is [`data/texture-plan.tsv`](data/texture-plan.tsv); it is generated from
the census by `tools/textures/make_plan.py` (`./make.sh texture-plan`) whose rule table *is* the
written record of what was looked at, so a census row can never silently lose its decision. The
script refuses to write unless every `yes`/`maybe` row matches **exactly one** rule, and unless
every rule matches **the number of rows it says it expects** — which is how a re-classified or
new census row swallowed by a broad rule is caught, since such a row leaves both "everything
matched" and "every rule matched something" true. `tests/test_texture_plan.py` regenerates the
table and diffs it against the tracked copy; it needs no disc.

**Nothing here contains the original's pixels.** Ids, categories and decisions only
(`CLAUDE.md` § "This repo is public"). Every image named was looked at, at 1:1 or zoomed, from
the local export under `work/rec08/png/` (regenerate with `work/rec08/extract.py`).

## The four paths

| | path | what it means | what is tracked |
|---|---|---|---|
| **P** | programmatic | a flat panel: blank it back to its own background in palette indices, re-rule if it was ruled, typeset the English with the game's own glyphs — the diary recipe of [diary-redraw.md](diary-redraw.md) | the English text + the geometry; the rebuilt image is emitted at build time |
| **R** | redraw | stylised lettering, or lettering over artwork: needs an artist or an image model, then a quantise back to the original CLUT | the redrawn image (README principle 2) |
| **S** | subtitle | painted into a background where a redraw means repainting the object; an English caption composited beside or below it is the honest option | the caption text + its placement only — never the original |
| **N** | none | stays Japanese by the charter: a shop sign is a shop sign | nothing |

**P is not "easy" and R is not "hard".** The split is *what the pixels are*, not what they
cost. A 94-page diary is **P**, because every one of those pages is the same flat ruled panel.
(The audit made the Wolf Girl's letter **R** because its page is turned and foreshortened; it
turned out to be **P** in the page's own plane — below.)

## Counts

| path | images | what they are |
|---|---:|---|
| **P** programmatic | **138** | 94 diary pages, 26 encyclopedia spreads, 1 item card, 17 UI atlases/plates |
| **R** redraw | **28** | 21 book-cover animation frames, 4 close-up signs, the result badges, a notebook cover, a brush-lettered button set |
| **S** subtitle | **1** | the beach notice board (now **P** in both map variants — see its section) |
| **N** none | **30** | scenery signage, packaging, calligraphy, the glyph sheet, the publisher credit |
| | **197** | |

By category (the census's own `category` values, so they grep):

| category | P | R | S | N | total |
|---|---:|---:|---:|---:|---:|
| `picture-diary page` | 94 | — | — | — | 94 |
| `insect/fish/item book` | 27 | 21 | — | 1 | 49 |
| `signage or label` | — | 4 | 1 | 22 | 27 |
| `title/menu/UI art` | 17 | 3 | — | 4 | 24 |
| `calendar/clock` | — | — | — | 1 | 1 |
| `font/glyph sheet` | — | — | — | 1 | 1 |
| `credits` | — | — | — | 1 | 1 |
| **total** | **138** | **28** | **1** | **30** | **197** |

`maybe` rows are all resolved below; the TSV keeps the census's `yes`/`maybe` provenance out of
the way and records only the decision, so "resolved" means *looked at again and settled*.

---

## `picture-diary page` — 94, all **P**

The owner has ruled (Jay, 2026-09-20): *"The game option is great, much more plausibly reliable
than the untested ChatGPT option."* The recipe and every measurement it turns on — the
repaintable rectangle, the column-rule pitch and erase window, the pages that need care — are
[diary-redraw.md](diary-redraw.md), and this file does not repeat them. What `GFX-03` takes from
it is the shape of the job:

* one rectangle is blanked back to the page's own background and re-ruled at the English line
  pitch, and it is the **same rectangle on 93 of the 94 pages** — so this is one recipe run 94
  times, not 94 drawings;
* the **day-numeral slot stays blank**: `nikki_date_upload` composites a 14×10 tile from
  `\_DATA\NIKKI_W.BIN` there at run time, and that tile is a numeral, not a word (§ "Composed
  text" below).

**English source: entirely new.** The diary entries are not in the script and have no line ids —
they exist only as pixels. 94 entries is the single largest block of new text in the project,
larger than any one day file.

## `insect/fish/item book` — 49

### The 26 encyclopedia spreads — **P**

**They are one layout with a per-page photograph, not 48 paintings.** This is the answer to the
question `GFX-03` was going to have to ask first.

* `\_DATA\MZKAN0.BIN` and `\_DATA\MZKAN1.BIN` hold **the same 9 insect spreads twice** —
  `MZKAN1` is the pack loaded before 19:00 and `MZKAN0` after (`zukan_insect_book_load`), and
  child *n* of one differs from child *n* of the other only by a lighting shift (mean 8 levels
  between the pair, 42 between different pages; measured 2026-09-21, `work/gfx05`) — so **9 pages
  to typeset, 18 images to write**, every one 252×188 8bpp with **one** CLUT. The layout is
  identical on all 18: a photographic panel top-left; to its right a **horizontal** header
  block (species name, family, wingspan or body length, food); a green horizontal rule; then
  the body paragraph in **vertical** columns
  filling the lower two-thirds. The type sits on **flat white paper**, not on the photograph —
  which is what makes it P and not R.
* `\_DATA\TZKAN.BIN` holds **8 kite spreads**, 244×186 8bpp, one CLUT, a different but equally
  flat layout: a painted kite panel on the left, vertical body columns in the middle, the kite
  name and a difficulty bracket in the right margin, on flat cream paper.
* `MZKAN.BIN` *without a digit* is not a page — it is a 44×74 sprite set, listed under
  `title/menu/UI art` below.

So the 49 of the census (48 `yes` + 1 `maybe`) is **26 page images (17 distinct pages: 9 insect
in two lightings, 8 kite) + 21 cover frames + 2 item pictures**, and only the 17 pages are a
typesetting job. Geometry to blank: the white/cream page area only, leaving the photo or
kite panel untouched; re-rule the single horizontal rule under the header; reflow the vertical
body to horizontal (the same reflow decision the diary faces, and it should be the same answer).

The insect book's cover calls it a **rare**-insect encyclopedia, and 9 pages against the 60
insect ids of `HHON`'s grid (57 names in [../translation/glossary.md](../translation/glossary.md)
§ 4a) is consistent with that: the book is not a page per catchable insect.

**The body paragraphs are pixels, and nothing in `hhon@5328` duplicates them** (`GFX-05`,
measured 2026-09-21). The `MZKAN` spreads are `ZUKAN.OVL`'s insect-book mode and draw no glyph;
`hhon@5328` is drawn only by `HHON.OVL`, the insect *box*, on screens of its own with no page
under them. The measurement, the modes and which item each walker draws are
[text-outside-events.md](text-outside-events.md) § "The insect and kite books"; the walkers'
origins are [text-renderer.md](text-renderer.md) § 3, surfaces 3 and 4.

### The 21 book-opening frames — **R**

`DOPA1‑6`/`DOPN1‑6` (diary), `MOPA`/`MOPN` (insect book), `TOPA`/`TOPN` (kite book), plus three
loose frames in the `Z_`/`MZ_` families — `Z_N02`, `Z_N03` and `MZ_A01`; their siblings `Z_A06`
and `MZ_A08` are blank pages, and no `MZ_N` file exists on the disc. These are six-frame
open/close animations of which the first frames show the cover. Frame 1 of each family is the cover flat on a desk or tatami and is legible;
frames 2–3 show it swinging open, **at an angle and in perspective**, with the type foreshortened
and partly occluded. There are only **three logical covers** (picture-diary book, rare-insect
encyclopedia with an author-and-photographer credit under the title, kite book) but each must be
redrawn consistently across every frame it appears in, or the animation will flicker between
languages.

### The two item pictures

* `PK_ITM` `0x00006c` (= `SBP01.TIM`), the **radio-exercise attendance card** — **P**. A flat
  frontal card, blue print on white: a two-line title and a footer line; the 31 stamp boxes are
  numerals. The title has about 62 px beside the picture and the footer ~6 px type; built in
  the Sprout face ([texture-recipes.md](texture-recipes.md) § "Buttons", the attendance card).
* `PK_ITM` `0x012acc` (census `maybe`) — **N**, *resolved*: an old book prop whose title is
  embossed dark-on-dark and does not resolve at any CLUT. The player never reads it.

## `signage or label` — 27

### The Wolf Girl's letter — `M_I14000`, **P** (was **R**)

Jay's recollection is right, and it is the only such texture on the disc.

* **What it is.** `\_DATA\M_FILES.BIN\M_I14000.BIN` at `0x000214`, 320×240 8bpp, one CLUT: a
  spiral-bound ruled notepad page lying on a mossy fallen log, two mushrooms beside it. **Four
  vertical columns, right to left, fully legible, ≈25 characters**, ending in a signature column
  that reads "from Saori". A complete, signed farewell note — *goodbye; you were a pretty good
  guy*.
* **Where it appears.** Scene **`E2860`** (`data/scenes.tsv`): `map_bases: D07,I14`,
  `triggers: auto=1 examine:z0=2`, `condition: (day>27 & flag[96]>0)`. `D07` is Saori's camp at
  Ryūjin Pond ([../translation/glossary.md](../translation/glossary.md) § 2 *Places*, the
  `Ryūjin-ike` entry: *"where Saori camps"*); she says goodbye in `E2760` on day 27 and is gone
  from day 28. From then on, examining zone 0 at the empty camp opens
  close-up `I14`.
* **How its text is stored: as texture pixels, and nowhere else.** `E2860` has **`messages: 0`**
  and no voiced nodes; `M_I14000` has **zero rows** in `data/text-sites.tsv`; there is no line id
  for the letter's words and none for a narrating "you examine the note" line. The close-up is
  shown silently and dismissed. It is the only plot-bearing string in the game with no line id.
* **The path: P, in the page's plane** (Jay, 2026-09-24: un-rotate the page, erase and write
  it upright, rotate it back, and keep the blue rules). The page is turned about 23° and
  slightly foreshortened, and the audit took that to need an artist. It does not: the page is
  one flat quadrilateral, so a single homography maps it upright, the Japanese is refilled
  from the page's own pixels along its rules, and the English is written on the rules in the
  game's glyphs and carried back through the same map
  ([texture-recipes.md](texture-recipes.md) § `M_I14000`). The dappled shadow the audit
  expected is not on the page. The caption (**S**) stays the fallback, and is not needed. The
  English is **new text** — the note and its signature, `tex@M_I14000.note` / `.signature` —
  and was checked against the Japanese for Saori's voice.

### The three other close-ups — **R**

These are `M_I*` **close-up screens**: the player entered them by choosing to examine the thing.
Leaving them Japanese would be leaving untranslated the thing the player just asked to read.

* `M_I23000` — the hunting-association warning board: an alarm word in a starburst, two large
  hand-painted lines, and the association's name in the corner, over a weathered frontal board.
* `M_I18000` (2 members, 1 image) — the hand-lettered "keep out!" sign hung on a door: flat
  white panel, frontal, marker lettering.
* `M_I19000` — the model-aeroplane kit box: scale plus a Japanese product name over a
  specification line that is **already Latin**, on a flat frontal box face. The parody brand
  mark stays.

### The beach notice — `M_C15000` and `M_C15100`, **P** (was **S**)

The notice board about high tides and swimming is painted into the **map-background atlas** of
the path down to the beach, drawn through CLUT 5 where the atlas's CLUT 0 shows noise. The audit
put it at an angle and chose a caption beside it (**S**). Seen on Beetle (2026-09-23,
[texture-recipes.md](texture-recipes.md) § `M_C15`) that is wrong: the board is **frontal** dark
wood with white painted type, in the screen's bottom-right corner and cut off by the screen's
right edge, and it is in **both** variants of the map (`C15000`, the one day 1 loads, and
`C15100`; the census now has both). With the grain running horizontally,
the type paints out cleanly along its rows, so it is **P**: the English is painted onto the
board, and only the text is tracked.

### The 22 that stay Japanese — **N**

Charter: *a shop sign is a shop sign*. None of these is read by the player; several are below
the size at which any lettering could be read.

| what | images |
|---|---:|
| pottery-workshop calligraphy banner (a proverb over the bench) | 4 |
| shaved-ice syrup-bottle label, two kana | 5 |
| food-item pictures, a few kana on a wrapper | 2 |
| hanging scroll, four characters of calligraphy | 1 |
| superhero poster title in a boy's room | 1 |
| study-room chart and poster (`maybe`, *resolved*: sub-glyph-size print) | 2 |
| shop front signboard (`maybe`, *resolved*: a shop sign, and CLUT 0 never resolves it) | 2 |
| attic of stacked books and papers (`maybe`, *resolved*: suggested lettering, none legible) | 1 |
| house front door plate (`maybe`, *resolved*) | 1 |
| refrigerator food packaging (`maybe`, *resolved*: dozens of packets, individually illegible) | 3 |

The calligraphy is the one worth a second thought: it is meaningful Japanese, and it is also an
art object hanging on a wall. Translating a hanging scroll would be localizing, which the charter
forbids.

## `title/menu/UI art` — 24

**TXT-05's `asm/title.asm` covers none of these images.** That work re-routes text the engine
*already* drew through `glyph_draw` — it changes the pen advance so those strings become
variable-width, and `asm/select.asm` turns SELECT menus horizontal. It converts **zero texture
pixels**, and it cannot: a string is renderer output only if some retail routine feeds its glyph
ids to `glyph_draw`, and none of these atlases' pixels are produced that way. The "overlay-wide
ORIGINAL gate" is a *build* check (`ORIGINAL equ 1` in `asm/vwf.asm` reassembles every patch site
and refuses unless the EXE and four overlays come back byte-identical) — it verifies patches, it
does not route text.

Two screens are **split between the two mechanisms**, and that is the thing to hold on to:

| screen | renderer (TXT-05 owns it) | texture (GFX-03 owns it) |
|---|---|---|
| settings | the five left-column labels, `exe@8003D9BC.0`–`.4`, via `config_draw` | the **value plates** — voice only / voice + subtitles, mono / stereo, on / off |
| "summer memories" album | the six menu labels, `exe@8003DA00`, via `extras_draw`; the "n of 31" and percent counters | the **heading plate** |
| title screen | nothing — no `TITLE.OVL` walker draws this menu | **all four menu lines** |

`research/text-renderer.md` raises the reverse move for surfaces 6/8 (`date_label_draw`,
`count_label_draw`) — English labels there may be cheaper *as* a texture. That is a `TXT`
question; it is noted here so the two sides do not both assume the other has it.

### **P** — 17

* `T_TITLE` — the four title-menu lines on a transparent ground, outlined type with a drop
  shadow. `PRESS START BUTTON` and the copyright line are already Latin. Clearing a transparent
  ground is trivial; the work is reproducing the outline-and-shadow pass.
* `T_CONFIG` ×2 — the settings value plates.
* `SUB`, `M_S01100` ×2, `M_S02000` ×2, `MZ00`, `MZ02`, `SAMP` — the in-game UI atlases carrying
  the **oval action buttons** ("back", "look", "net", …) and their plates. One of these,
  `M_S02000` `0x000024`, was a census `maybe`; *resolved* at CLUT 3 — it is the insect-cage
  close-up atlas with two action ovals in its corner, the same family as its siblings. These are
  multi-CLUT atlases: any rebuild must carry the per-region CLUT assignment, which lives in the
  drawing code and not in the TIM ([textures.md](textures.md) § Caveat).
* `FS_WAL`, `PK_WAL`, `TK_WAL` — the census gave all three the same note, and only `FS_WAL`
  fits it (looked at 2026-09-22): field labels (size / average / largest / count) on flat pale
  plates, plus the bait and tackle names. `PK_WAL` and `TK_WAL` carry only frames, photographs
  and the small speech-balloon buttons, which belong with the action buttons.
* `T_MEMORY` ×2 — the album heading plate (child `0xd634`; child 0 is the frame and a back
  button). The filmstrip of thumbnails beside it is a strip of
  illegible miniatures of the diary and collection pages; they are pictures of pages, not pages,
  and stay as they are.
* `TZICON` — the kite-workshop speech balloon, its confirm word and a "back" button, flat on
  transparent.

### **R** — 3

* `MITIM` — the insect-catch result badges: a "rare" starburst, size crowns, male/female marks,
  on a transparent 4bpp sheet with 10 CLUTs. `BIG!` is already Latin. Stylised badge lettering,
  not type.
* `M_S01000` `0x017d24` (census `maybe`) — *resolved* at CLUT 3: a spiral notepad in the
  insect-cage close-up whose cover is hand-lettered in marker, "bug swap notebook". Legible,
  real, and in a style no glyph typeset reproduces.
* `MZKAN.BIN` `0x000048` (census `maybe`) — *resolved* at CLUT 1: a 44×74 sprite set: the
  insect book's stone "Back" — *corrected* 2026-09-23: the same stone drawing as every other
  "Back", built with them ([texture-recipes.md](texture-recipes.md) § "Buttons") — above a
  wreath and two pencils (`H`, `HB`), which carry no Japanese.

### **N** — 4, all census `maybe`, all *resolved as having no Japanese*

* `M_S01001` — `PLAYTIME` is Latin (the row of marks above it is that word's ~6 px
  anti-alias/shadow plane), but the atlas also carries the load/save screen's stone "Back"
  at (233, 105) — *corrected* 2026-09-23: it is a **P**, built with the other buttons
  ([texture-recipes.md](texture-recipes.md) § "Buttons").
* `TBG00`, `TBG01` — the kite-flying HUD: at CLUT 0 the atlas is kite thumbnails plus
  `1234567890`, `m`, `s`, `m/s`, a compass rose and a wind vane. All Latin and numerals.
* `NIKKI_W` `0x005450` — *corrected* 2026-09-23: its header says 8bpp 28×184, and read that
  way it looks like a pull cord, a wreath, a mushroom and two pencils. The game draws it as
  **4bpp 56×184**: the pull cord, the diary desk's おやすみ ("good night") balloon, its stone
  "Back", and the pencils. A **P**, built with the other buttons
  ([texture-recipes.md](texture-recipes.md) § "Buttons").

## The three singletons

* `calendar/clock` — `M_I13000`, **N**. The August calendar itself is *already English*:
  `AUGUST`, `SUN`…`SAT`, and Arabic numerals, with a camel photograph above it. The only
  Japanese in the image is a small printed form pinned to the wall beside it, at a size where
  nothing is legible.
* `font/glyph sheet` — `ONMEM.BIN` `0x4AA0`, **N** *for `GFX-03`*. It is not a texture to
  translate: it is the font. Latin coverage in it belongs to the font and VWF work
  ([font.md](font.md), [vwf-prototype.md](vwf-prototype.md)). Recorded here only so that a later
  reader does not find it unassigned and assume it was missed.
* `credits` — the 276×33 4bpp production/copyright strip, one copy in each of `OTI00`…`OTI04`:
  **P** since Jay's ruling (2026-09-23: translate it if it needs no video re-encode). It is a
  still, the last card `ENDOTI` shows — `MOVIE 24`'s scrolling credits before it are video and
  stay. Built in [texture-recipes.md](texture-recipes.md) § `OTI0n`.

## Composed text — the blind spot the census names

The census is explicit that it cannot see *"text drawn by the renderer over a texture"*, so a
texture that looks blank there may carry text in game, and Japanese assembled from 8×8 or 16×8
tiles would be invisible to it twice over. **Audited, and there is none.**

* **The one proven compositor writes a numeral.** `nikki_date_upload` (`0x8007A53C`) uploads
  child `[day]` of `\_DATA\NIKKI_W.BIN` next to the diary page
  ([text-outside-events.md](text-outside-events.md)); the pack is 31 tiles of 14×10 8bpp and the
  slot they land in (x 223–238, rows 138–150) is blank on all 94 pages. Each tile is the day of
  the month as **Arabic numerals** — the page's own date line already carries the month in
  drawn type. Nothing to translate; the English date just has to leave the slot where the
  compositor expects it, or move the tiles with it.
* **`NUMBER.TIM` is a font — a font of digits.** 144×10 4bpp, reading `0123456789`, `mm`, `∞`,
  `.`, `cm`. It is not the cage ruler `REC-08` took it for: `cage_init` (`0x80043468`) loads it
  at boot and uploads it to VRAM (592, 496), and `number_draw` / `number_draw2`
  (`0x800400F8` / `0x800402D8`; [text-outside-events.md](text-outside-events.md) counts their
  call sites and [text-renderer.md](text-renderer.md) calls the second one `number_draw_b`)
  emit 8×12 sprites at `u = 0x48 + 8·d` with a caller-chosen CLUT — it is **the game's
  general-purpose number font**, serving the cage HUD, fishing, bug sumo, the insect book, the
  item menu and the `TITLE` file list. Latin and numerals throughout; nothing to translate, and
  nothing spells a word with it. `\_DATA\KAGO_UV.BIN` is its sprite table: `u32 18` followed by
  18 twelve-byte rects, 2×8 to 10×24 — digits and unit marks, never kana components.
  Two census notes were corrected from this look: `\_DATA\KAGO.BIN` `0x2784` is green cage
  bars, not the number strip, and `\_DATA\KAGO2.BIN` `0x0` is a second, narrower strip of its
  own (120×10, 15 cells), not a copy of `NUMBER.TIM`.
* **The two mass-duplicated tiles are terrain.** The 8×8 and 16×8 4bpp tiles at 239 and 189
  copies both live in the map packs (`M_A01000` `0x2b48` and `0x3660`); at 20× they are a white
  blob, a water strip, grass and foliage. Nothing in the map-pack format arranges tiles into a
  label; the backgrounds are atlases addressed by region, not tilemaps addressed by index.
* **There is exactly one glyph sheet, and that was re-derived independently of the census.**
  Scanning all 824 distinct images for the four-plane 1bpp signature — a CLUT drawn only from
  `{0x0000, 0x8000, 0xFFFF}` — returns **exactly one hit**, `ONMEM.BIN` `0x4AA0`
  ([font.md](font.md): four interleaved 1bpp planes, 12×12 cells, 1,512 slots). A sweep of every
  `has_text: no` image ≤ 64 px and of all 42 at 128×88 found no glyph grid, and `NIKKI_W`'s 31
  numerals are the only set of many identically-sized tiny TIMs on the disc. The other
  candidates for a hidden sheet were looked at and are not: `ONMEM.BIN` `0xBA00` is the hand
  cursor and gem sprites, `MZKAN.BIN` `0x48` is a 44×74 sprite set with three brush-lettered
  plates (an **R** above, not a sheet), and `NIKKI_W`'s 28×184 sprite is the diary desk's
  buttons drawn at 4bpp (§ **N** above).
* **Every other run-time-drawn string already has a line id.** The glyph-drawing surfaces are
  enumerated in [text-renderer.md](text-renderer.md) and their sources in
  [text-outside-events.md](text-outside-events.md): 34 arrays, 301 strings, 4,492 glyphs, plus
  five immediate-id labels and the Shift-JIS memory-card title. That is the `TXT` side's
  inventory, it is complete, and none of it is composed from tiles — it all goes through
  `glyph_draw`, which reads the one sheet. The part of it worth naming here, because it has no
  data to extract and so looks like nothing until someone hits it, is the handful of labels
  built from **immediate glyph ids in code**: `date_label_draw` (`0x80037544`),
  `count_label_draw` (`0x800377F8`) and the title screen's date. Those are a code patch, not a
  texture and not an array — `TXT`'s problem, listed here only so `GFX-03` does not go looking
  for them in the pixels.

**So: no Japanese anywhere on this disc is assembled from tiles.** The only tile compositing that
happens is the diary's day numeral, and a numeral needs no translation. `GFX-03`'s surface is
exactly the 197 images of the census, and the `TXT` side's is exactly the 301 strings — the two
inventories meet with no gap between them and no overlap (the one candidate overlap, the
insect-book body paragraph, was closed by `GFX-05` — § "The 26 encyclopedia spreads").

*How far this is measured:* two UV tables were parsed by hand; the others inside packs were not
enumerated, so "no UV table spells Japanese" is measured for those two and inferred for the
rest. The check that would close it outright is already on
[text-outside-events.md](text-outside-events.md)'s emulator list — break on texture-page writes
selecting the font page (VRAM x = 768) outside `glyph_draw` — and **has never been run**.

## The new English text this creates

All of it is new: **not one texture string has a line id today**. The translation files
(`translation/days/*.txt`) hold event dialogue keyed `E<dd>NN.<page>`; the UI/array strings that
`TXT-05` uses live as `exe@<RAM>.<item>` fixtures in `tools/vwf/prototype-lines.tsv`. Texture
strings need a third namespace, and `tex@<member>.<n>` (with `nikki@`, `mzkan@`, `tzkan@` for the
three bulk families) fits the existing `<container>@<offset>.<item>` convention. The `tex@`
ids are in use: `translation/textures/` holds them and `boku build --textures` typesets them
([texture-recipes.md](texture-recipes.md)).

| # | id space | what to translate | volume |
|---|---|---|---:|
| 1 | `nikki@NIKKI_nnn` | picture-diary entries, one per page | **94 entries** |
| 2 | `mzkan@MZKAN.n` | insect spreads: species name (glossary § 4a), family, wingspan/body length, food, body paragraph — all pixels (§ "The 26 encyclopedia spreads"); one id per page, written to child *n* of both `MZKAN0` and `MZKAN1` | 9 × 5 fields |
| 3 | `tzkan@TZKAN.n` | kite spreads: kite name, difficulty bracket, how to build it | 8 × 3 fields |
| 4 | `tex@DOPA1`, `tex@MOPA1`, `tex@TOPA1` | 3 book cover titles + the insect book's author-and-photographer credit | 4 strings |
| 5 | `btn@PK_ITM.title`, `btn@PK_ITM.footer` | radio-exercise attendance card: title + footer line | 2 strings |
| 6 | `tex@M_I14000.note`, `.signature` | **Saori's farewell note** — the highest-value string here | ~25 chars, 4 columns |
| 7 | `tex@M_I23000.*` | hunting-association warning board | 4 short strings |
| 8 | `tex@M_I18000.0` | "keep out!" sign | 1 line |
| 9 | `tex@M_I19000.0` | model-kit product name | 1 line |
| 10 | `tex@M_C15.0`, `.1` | beach notice board, painted onto the board in both map variants | 2 lines |
| 11 | `tex@T_TITLE.*` | title menu: new game / continue / summer memories / settings | 4 lines |
| 12 | `tex@T_CONFIG.*` | settings value plates | ~6 plates |
| 13 | `tex@SUB.*` | action-button words, deduplicated across the 8 atlas images in 6 files | ~12 words |
| 14 | `rec@FS_WAL.*`, `btn@FS_WAL.*`, `btn@PK_WAL.*`, `btn@TK_WAL.*` | record-screen field labels, the bait and tackle names, and their buttons | 16 strings |
| 15 | `tex@MITIM.*` | result badge words | ~4 words |
| 16 | `tex@TZICON.*` | kite-workshop balloon, confirm, back | 3 strings |
| 17 | `tex@T_MEMORY.0` | album heading plate | 1 line |
| 18 | `tex@M_S01000.*` | "bug swap notebook" cover | 2 lines |
| 19 | `tex@MZKAN.*` | brush-lettered back plaque + 2 action plates | 3 strings |

Rows 1–3 are **111 pages** and dwarf everything else; rows 11–19 are a few dozen short strings
that a single pass produces. The glossary already governs rows 2 and 3 (species and kite names)
and row 6 (Saori, and the register she uses with Boku — the glossary's § 1 entry for her *weird
kid / rotten brat* cites `E1861.6` and `E2760.0` as the two lines that fix how she talks to him;
both were read from the local extract, not from a translated day file, since the translation
covers days 1–7). The note has to sound like the same person.

## What this audit did not settle

* **The vertical-to-horizontal reflow** is one decision taken 120 times (diary, insect book, kite
  book) and it is a layout question, not a drawing one. `diary-redraw.md` answers it for the
  diary; the two encyclopedias should inherit the same answer rather than each inventing one.
* **`flag[96]`**, which gates the letter's scene alongside `day>27`, is not annotated in the
  bible's flag list. It also gates `E1910` on day 19. It does not change the letter's path.
* **`\_DATA\MI14.BIN`** (a separate map-level pack, member 68) carries one censused texture that
  was not inspected as part of this pass; it is not text-bearing by the census, but it is the one
  neighbour of the letter's scene that went unlooked.
* The exact wording of every string above is read off a 1:1 or zoomed render, not extracted
  byte-for-byte. A translator works from the import, not from this file.
