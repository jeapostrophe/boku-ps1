# Textures — where Japanese is baked into pixels (PLAN `REC-08`)

Everything here was measured on the dump identified in [disc-recon.md](disc-recon.md) unless it
is marked *hypothesis*. The per-image list is [`data/texture-census.tsv`](data/texture-census.tsv);
the tools that produce it live in `work/rec08/` (gitignored, stdlib plus Pillow for PNG output):

```
uv run --no-project --with pillow python work/rec08/extract.py --report   # PNGs + metadata
uv run --no-project --with pillow python work/rec08/sheets.py             # contact sheets
uv run --no-project python           work/rec08/classify.py               # the tracked census
uv run --no-project --with pillow python work/rec08/group.py <name> <id regex> [per] [scale]
uv run --no-project --with pillow python work/rec08/one.py <id> [--clut N] [--crop x,y,w,h] [--scale N]
```

`extract.py` regenerates every PNG and the metadata TSV from `disc/files/` alone. Nothing under
`disc/` is written. `classify.py`'s rule table is the written record of what was seen on which
image, keyed by the distinct-image id rather than by the sheet-local `T####` labels.

## Method

A TIM decoder was written from the PsyQ layout (`work/rec08/tim.py` documents it): magic `0x10`,
a flag word carrying the depth and a CLUT-present bit, an optional CLUT block, then a pixel block
whose `w` counts **16-bit VRAM units** — so the real width is `w*4` at 4bpp and `w*2` at 8bpp. A
colour is ABGR1555 and `0x0000` is fully transparent, so every PNG is composited over a mid-grey
checker; without that, white lettering on a transparent sprite is invisible against a white page.
The decoder was validated by *looking* at pictorial TIMs whose content is unambiguous (the title
screen, a diary page, a painted background) before any classification was done; the 4bpp nibble
order is confirmed the same way, since the glyph sheet and the UI buttons come out legible. Its
16bpp and 24bpp paths are written but **unexercised — the disc contains no such TIM**.

Enumeration is a greedy, 4-byte-aligned scan for the magic word inside each member of
`BOKU.BIN` (member boundaries from [boku-bin.md](boku-bin.md)) and inside `SCPS_100.88`: a
candidate that parses is accepted and the scan resumes past its end, so a stray `0x10` word in an
accepted TIM's pixels cannot manufacture a nested false positive. **In the event, the greediness
never mattered**: over all 104 MB, exactly 2,606 4-aligned offsets parse as a TIM at all, and
they are exactly the 2,606 accepted — no candidate lies inside another, and none was skipped. The
acceptance test is what does the work: both block sizes must equal `12 + w*h*2` and
`12 + colours*cluts*2` exactly, which random data does not satisfy.

Distinct images are keyed by the SHA-1 of the TIM's bytes; each is rendered once, classified once,
and the classification propagates to its copies. Classification was done by eye from labelled
contact sheets, grouped by size class and packed so that no sheet exceeds what an image read
shows without resampling (≈1.0 MP, ≤1500 px a side); tiny tiles are upscaled, 320×240 and larger
images stay at 1:1 so signage inside a background stays readable. Anything suspected of carrying
text was then cropped and zoomed on its own.

That packing budget was wrong on the first pass — it summed the cells and ignored the padding and
the slack in ragged rows, so three sheets landed over the limit (worst 1.62 MP) and were shrunk
on the way in, which is exactly what the 1:1 promise rules out. The budget now measures the
rectangle actually saved (99 sheets, largest 0.99 MP), and the 21 images that had been on those
three sheets were re-read at true 1:1: no classification changed.

`has_text` is **conservative**: `maybe` means marks that are probably lettering but were not read
(too small, or hidden by the CLUT caveat below).

## Totals

| | |
|---|---:|
| TIM occurrences on the disc | **2,607** |
| …in `BOKU.BIN` | 2,606 |
| …in `SCPS_100.88` | 1 (three 16×16 face sprites; no text) |
| distinct images (by SHA-1) | **824** |
| distinct images with Japanese text | **180** (`yes`) + **17** (`maybe`) |
| occurrences of those | 198 + 19 |

**Duplication is heavy**, as it is for text (boku-bin.md § "Where the text is"): 199 distinct
images account for 1,982 of the 2,607 occurrences. The most-copied are a 98×79 watercolour
minimap that appears in 287 map packs and two small 4bpp tiles (8×8 and 16×8) at 239 and 189
copies; only ten distinct minimaps serve all 483 maps that carry one. Every copy is a separate
TIM in a separate member, so an edit to one image has to be written back to each of them.

Depth and palette, over all 2,607: **every TIM is 4bpp/16 colours (1,230) or 8bpp/256 colours
(1,377), and every one carries a CLUT block.** There is no 16bpp or 24bpp TIM on the disc. Sizes
run 8×8 to 764×256; 488 distinct images carry more than one CLUT (up to 21). Both block sizes are
always exactly `12 + w*h*2` and `12 + colours*cluts*2` — no padding slack anywhere. **VRAM
origins are two separate fields and they behave differently**: the pixel block's origin is
non-zero in only 32 TIMs, but the CLUT block's is non-zero in **758**, so a rebuild that carries
only the image coordinates loses the palette placement for nearly a third of the disc. Both are
in `work/rec08/tims.tsv` as `pix_x/pix_y` and `clut_x/clut_y`.

Not every family stores its graphics as TIMs: `H_FILES.BIN`'s 115 model packs contain **no TIM at
all**, so this census says nothing about model textures beyond the shared ones in `MDLTIM.RTM`.

### Reconciliation with jPSXdec

psyouloveme's `boku.idx` lists 2,606 TIM positions inside `BOKU.BIN`. The scan here finds **the
same 2,606 byte offsets: zero only-mine, zero only-theirs.** `boku.idx` additionally lists the one
TIM in `SCPS_100.88`, which this census also extracts, giving 2,607 against jPSXdec's 2,607.

### Categories

Counts are distinct images; `maybe` in brackets.

The category names are exactly the TSV's `category` values, so they grep.

| category | with text | what it is |
|---|---:|---|
| `picture-diary page` | **94** | the `NIKKI.BIN` pages, 240×192 8bpp |
| `insect/fish/item book` | **48** (1) | encyclopedia spreads, book covers, one item card |
| `signage or label` | **18** (9) | signs, posters, a note, packaging, calligraphy |
| `title/menu/UI art` | **17** (7) | title menu, settings, action buttons, record screens, result badges |
| `calendar/clock` | **1** | the August wall calendar in a close-up screen |
| `font/glyph sheet` | **1** | see below |
| `credits` | **1** | the production/copyright line, one copy each in `OTI00`…`OTI04` |
| — | — | 627 images with no text: map artwork, model textures, tiles, pictures, numerals |

Difficulty over the 197 text-bearing images: 129 easy, 20 medium, 41 hard, 6 unknown, 1 n/a.

The publisher logo screen (`T_BUMPER`) is several lines of Latin logotype and needs nothing; the
one Japanese credit is a separate 276×33 4bpp strip carried by each opening/ending cut.

## How the picture diary works

**The 94 diary pages are full pages with the Japanese baked into the bitmap.** Each
`\_DATA\NIKKI.BIN\NIKKI_nnn` member is a single 240×192 8bpp TIM: a crayon drawing occupying the
upper half or two-thirds, and below it a ruled page whose **vertical** columns carry the day's
entry in plain gothic type, already set. The text is texture, not renderer output.

Two details pin the mechanism down:

* Every page's date line reads "8月　日" — the month is drawn, **the day numeral is blank** — and
  `\_DATA\NIKKI_W.BIN` holds exactly 31 numeral tiles of 14×10 8bpp (plus one unrelated 28×184
  sprite strip). The renderer composites the day number onto an otherwise finished page; it draws
  nothing else there.
* `NIKKI_000` is an unused placeholder whose text columns are empty and whose picture area says,
  in effect, "this is a dummy picture" — so a page with no entry is a page with blank columns,
  not a page the renderer fills in.

Consequence for `GFX`: the diary is 94 whole-page redraws, and the English has to be re-set into
(or across) those columns. It is the single largest block of texture text on the disc, and it is
also the easiest kind to redraw — plain type on a flat, lightly ruled white page, 8bpp with a
private 256-colour CLUT per page.

*Not established here:* whether the game ever shows a diary page the player did not "earn", and
how the 94 pages map onto the 30-odd days — `NIKKI.SEC`'s ids run 0–100 with gaps
(boku-bin.md § Unknown). That is a `REC` question, not a texture one.

## The kinds of Japanese-in-texture, and how hard each looks to redraw

Easiest first.

1. **Menu and settings text on a flat or transparent ground** — the title screen's four menu
   lines plus `PRESS START BUTTON`, the settings screen's audio options, `設定`/`OFF` plates.
   Flat colour fills, outlined type, a private CLUT. A redraw is a typesetting job.
2. **Record and collection screens** (`FS_WAL`, `PK_WAL`, `TK_WAL`, the `M_S0*` and `T_CONFIG`
   atlases) — field labels ("size / average / largest / cm"), bait and tackle names, and dozens of
   small oval buttons carrying one to three characters ("back", "look", "net"). Flat ground, but
   many small pieces spread over large atlases, and English is wider than two kana. The
   insect-catch result badges (`MITIM.BIN`: a "rare" starburst, "BIG!", size crowns) and the
   production/copyright strip belong here too — transparent ground, one word each.
3. **Encyclopedia and diary pages** — the insect book (`MZKAN0`, `MZKAN1`; note `MZKAN.BIN`
   without a digit is a sprite set, not a page), the kite book
   (`TZKAN`), the 94 diary pages. A paragraph each, plain type, flat page: mechanically easy,
   large in volume, and vertical-to-horizontal reflow is a layout decision, not a drawing one.
4. **Book covers and jackets** (`DOPA*`/`MOPA*`/`TOPA*` and a few `Z_*`/`MZ_A*` opening frames —
   the first three of each six-frame animation show the cover, the rest are blank pages) —
   stylised cover type over painted artwork, down to the insect book's author-and-photographer
   line. Medium: the type is decorative and sits on texture.
5. **Signage inside backgrounds** — hardest. A weathered hunting-association warning board, a
   hand-lettered "keep out" sign, a calligraphy banner in the pottery workshop, a hanging scroll,
   a beach notice about tides, a superhero poster, a model-kit box, a farewell note in
   handwriting on a notepad. These are painted *into* the scene, at an angle, with shading,
   weathering and perspective, and several are plot-bearing rather than scenery. A clean redraw
   means repainting the object; the composited-subtitle fallback (README principle 2) is the
   realistic option for most of them.

Two things that look like text and are not: the ruler/measurement strip (`NUMBER.TIM`,
`KAGO*.BIN`) is digits plus `mm` and `cm` unit marks, and the publisher logo screen (`T_BUMPER`)
is Latin logotype. Neither needs translation.

## The glyph sheet

**Exactly one** of the 824 distinct images is the font: `\_DATA\ONMEM.BIN` at offset `0x4AA0`.
A TIM scan of the whole disc finds no second glyph sheet anywhere, which is the census's
contribution here; everything about the sheet itself — that it is four interleaved 1bpp planes,
not a 16-colour image, with 12×12 cells and 1,512 slots — is [font.md](font.md), measured there.

Worth knowing when looking at this census's PNG of it: rendering with CLUT 0 shows **one plane
only**, so the sheet appears to hold about a quarter of its glyphs, in rows of 21 that jump by 84
ids. That is the rendering, not the sheet.

The other TIM in `ONMEM.BIN` (`0xBA00`, 48×88, 3 CLUTs — font.md's child 3) is the hand cursor
and some gem sprites.

## Caveat: multi-CLUT images render wrong at CLUT 0

488 of the 824 distinct images carry more than one palette, and the map backgrounds in particular
are atlases whose regions each use a different CLUT. Every PNG in this census is rendered with
**CLUT 0**, so parts of those atlases come out with wrong colours (flat red, green or white
patches are the usual symptom). Shape and lettering survive, which is all the census needs, but:

* a `maybe` on a background often means "the sign is there, CLUT 0 will not resolve it";
* `GFX-01`'s round trip and any redraw must carry the per-region CLUT assignment, which lives in
  the drawing code, not in the TIM.

The one place this was checked directly: the diary-book cover image (`DOPA1.BIN`) has two CLUTs,
one correct for the wooden desk and one correct for the photograph printed on the cover.

## Coverage and open doubts

* **Examined at full attention:** the full set of size-class contact sheets (every distinct image
  appears on exactly one of them, at 1:1 for everything ≥ 128 px), plus targeted re-look sheets
  for the 65 `M_I*` close-up screens, the 36 book-opening frames, the 13 item pictures, 14 of the
  UI atlases, the 6 opening/ending screens, the ~100 images that no classification rule had
  claimed, and the 21 images caught by the packing-budget bug above; plus about 35 individual
  zoomed crops. The unclaimed-image re-look is where the copyright strip, the result badges and
  three more book covers were found — the size-class pass alone had missed them, which is the
  measure of how much a pass over 824 images at once misses.
* **Skimmed:** the last two of the eight kite pictures (`TK_ITM`) were seen only at 1:1 on their
  size-class sheet. Everything else in the picture families was re-looked at 3× — the 14 fish and
  tackle pictures, the 19 photo-album prints (whose only lettering is a tiny Latin film-brand
  mark) and all ten 98×79 watercolour minimaps at 4× (no labels of any kind on the minimaps).
* The 426 distinct map-pack images were read at 1:1 but a two- or three-character label painted
  small into a background could still have been missed; the `maybe` rows name the places where
  something is visibly there and unread.
* Text drawn by the renderer over a texture (the diary's day number is the proven case) is not
  visible to this census at all. A texture that looks blank here may carry text in game.
* FMV frames (`__STR/*.IKI`) are out of scope (README § "What gets translated", row 3) and are
  not TIMs; nothing here covers them.
