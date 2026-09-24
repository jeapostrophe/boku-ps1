# Redrawing the picture diary programmatically (PLAN `GFX-02`, `GFX-04`)

`GFX-02` asks which path translates each texture category. This file is the measured case for
the **programmatic** path on the 94 `NIKKI.BIN` pages — the third option that row names, and
over half the texture work. It records what the pages' pixels turned out to be, what a program
can and cannot do with them, and what a full `GFX-03` run would still need. What a diary page
*is*, and how the game picks and composites one, is [textures.md](textures.md) § How the
picture diary works and [text-outside-events.md](text-outside-events.md) § The picture diary;
neither is repeated here.

Everything below was re-run on 2026-09-20 against `disc/` and is stated only where the run
agreed; where an earlier draft of this file was wrong, the measured number replaces it.

The prototype is [`tools/diary/redraw.py`](../tools/diary/redraw.py), a tracked script (stdlib
plus `boku`; Pillow only to scale and stack the comparison sheet — every pixel that reaches a
TIM is written by the script itself, so the image path takes no dependency):

```
uv run --no-project --with pillow python tools/diary/redraw.py measure
uv run --no-project --with pillow python tools/diary/redraw.py render  --page 001
uv run --no-project --with pillow python tools/diary/redraw.py compare --page 001
uv run --no-project --with pillow python tools/diary/redraw.py build   --page 001 --face game
```

Its outputs are the game's own pixels, so they land under the gitignored `work/diary/` and
`build/diary/` (README principle 2). `measure` writes `work/diary/geometry.json`, one record
per page, which is where the numbers below come from; a full sweep of all 94 pages takes about
five seconds.

## Method

1. Export the page through `boku.textures`/`boku.tim` — the same inventory `boku textures
   export` uses, so the page is addressed by the census id `_DATA_NIKKI.BIN_NIKKI_001__000000`
   and the edit comes back out as byte edits at every occurrence.
2. Measure the ruled panel from the pixels of **all 94 pages**, not one: the panel's top edge,
   the vertical rules, the date column and the day-numeral slot (below).
3. Blank the panel back to the page's own background, erasing the vertical rules; draw
   horizontal rules at the English line pitch; typeset the entry in a 1-bit face.
4. Feed the new index array through `Tim.with_indices`, which changes pixels and nothing else,
   and `textures.patches_for`, which yields one verified `(file, offset, old, new)` run per
   changed byte range.
5. `boku.build.build(..., binary_patches=edits)` writes the patched image with EDC/ECC and
   verifies every `old` before the first sector is written; `verb_build` then re-reads the
   written sectors through `build.verify_written_sectors`.

**Everything is done in palette indices.** No colour is ever chosen: the paper, the rule and
the ink are entries the page already uses, read back out of its own panel. `boku.tim` refuses
an off-palette colour by design, and this path never offers it one — the `--nearest`
quantiser is not involved and no `Quantisation` report is produced.

## The panel, measured

All coordinates are page pixels. Every one of the 94 pages is **240×192, 8bpp, one 256-colour
CLUT** and — unlike almost everything else on the disc — occurs **exactly once** (measured:
`Texture.copies == 1` on all 94), so a diary edit propagates nowhere.

| | |
|---|---:|
| drawn top edge of the ruled page | 109 on 51 pages, 110 on 24, 108 on 7, 97–107 on the other 12 |
| first paper row | **113**, on all 94 |
| last paper row | **185**; 186 is the page's bottom edge, 187–191 the desk under the book |
| vertical column rules | **13**, pitch **17** (one 16 px step at the fold), nominal x 18/19, 35/36 … 221/222 |
| text columns between them | 14, the rightmost being the date |
| date column | x **222–239** |
| day-numeral slot | x 223–238, rows 138–150 |
| repaintable rectangle | x **1–221**, rows **113–185** |

* **The rules are artwork, not a generated grid.** A rule is 1 or 2 px wide depending on the
  page and sits up to 2 px either side of its nominal pair, so both the erase and the check
  work over a **6-column window** per rule (`Panel.rule_window`). A naive "the rule is at x=18
  and x=19" would leave a stripe of the old rule standing on the pages that drift.
* **The book's centre fold is background and it survives.** Columns ≈118–155 carry a band of
  shadow and cream paper whose width wanders page to page. Blanking to one flat paper colour
  would iron the book flat, so the blank restores a **per-column** background: the panel's
  background is a function of x alone (vertical rules, vertical crease), so the modal pale
  colour of each column is the page with its text taken out.
* **The drawing dips into the top of the panel.** On **56 of the 94** pages a saturated
  (crayon) pixel reaches row 113 or below — the V-notch where the two halves of the book meet.
  The blank therefore never writes over a saturated pixel, and no English is drawn above row
  117 (`Panel.repaint_top`).
* **The panel's own colours are all near-neutral, and that is what makes the crayon test
  safe.** Over the whole repaintable rectangle of all 94 pages, every palette entry covering
  ≥ 0.1 % of the panel has an R/G/B spread of at most **41**, against the `CRAYON_SPREAD`
  threshold of 48 — so the blank cannot mistake paper, rule, fold or ink for crayon on any
  page. (The panel is not three flat colours: it uses between 22 and 96 distinct entries per
  page, the rest being the Japanese text's antialiasing and the fold's shading.)
* **The day-numeral slot is blank on all 94 pages**, which is the pixel-side confirmation of
  `nikki_date_upload` compositing a 14×10 tile there. Ink in the date column starts at row 115
  (10 pages) or 116 (84) and stops at row 160, 161 or 162 — three bands, `8`, `月` and `日`,
  with the slot between the last two and nothing below. The prototype does not touch x ≥ 222,
  so the date strip and the slot come through untouched.

### What the gate can and cannot catch

`measure` exists to disagree with the constants above when they are wrong, so each was
perturbed in turn and the pages that noticed were counted. **The perturbations were re-run;
this table replaces an earlier one that was wrong about the rules.**

| perturbation | pages flagged |
|---|---:|
| `top` 113 → 112 or 114 | **94/94** |
| `bottom` 185 → 183 or 187 | **94/94** |
| `day_slot` moved 10 rows up, onto 月 | **94/94** |
| every rule +3 | **94/94** |
| every rule +2 | 14/94 |
| one rule +3, away from the fold | 83–94/94 |
| one rule +2, away from the fold | 1–11/94 |
| one rule ±3 **at the fold** (index 6, x 119/120) | **1/94 — invisible** |
| one rule declaration deleted | 94/94, but by the step check below, not by pixels |
| `repaint_top` 117 → 113 | 57/94 (the pages whose fold notch reaches that far) |
| `date_left` 222 → 218 | 6/94 |
| `date_left` 222 → 226 | 2/94 |

Three honest limits, and one of them was hidden by the earlier table:

* **A ±2 rule shift is invisible by construction** — the rules really do move that far page to
  page, so the window has to be that wide. ±3 is caught away from the fold.
* **The rule inside the book's fold is not checked by the pixels at all.** `rule_like` is
  satisfied by the fold's own pale cream, so `pairs` agrees with any placement of that one
  rule within the crease band; `extras` skips the crease deliberately. It does not matter in
  practice — the 6-column window still covers the real rule's ±2 drift — but the gate is not
  what proves that, and a contributor's page with a differently-placed fold rule would pass.
* **The `wide_steps` note is derived from the declared constants, not from any page.** It is a
  self-consistency check on `rule_pairs` (a deleted declaration leaves a double step), so it
  flags all 94 pages or none, for every page equally. It is useful — it is the only thing that
  catches a deleted rule — but it must not be read as 94 pages agreeing about pixels.
* `date_left` is weakly held in both directions because the date glyphs sit a couple of columns
  inside their column and the band count cannot see a couple of clipped pixel columns; a
  `date_left` error is instead caught by looking at a rendered page, which is what `compare` is
  for.

**93 of the 94 panels match this geometry exactly.** The one exception is **`NIKKI_047`**,
whose panel has extra pale columns at x = 2, 15 and 157–163 — shading, not rules; the redraw
handles it correctly because those columns simply keep their own background. No page differs
in the numbers that matter: top, bottom, rule pitch, date column, slot.

## Palette facts

| | |
|---|---|
| paper | `#F7F7F7` on 93 pages, `#FFFFF7` on one |
| rule | `#CED6DE` (54), `#C6D6DE` (31), `#CEDEDE` (4), five more on one page each |
| ink | 12 distinct values, every one of luminance ≤ 8 — `#080808` on 64 pages, the rest tiny tints of it |

The ink is taken as the darkest entry the page's own panel and date column already use, so a
redraw writes the same black the Japanese was drawn in. Each page has a private CLUT, so all
three indices are per-page; nothing is shared and nothing has to be reconciled.

## Layout

The English band is 12 rows (`INK_ROWS`; the game's cell is 12 px and Galmuri9 needs 12 of the
band), the line pitch is **13**, and five lines fit: tops at 118, 131, 144, 157, 170, with a
horizontal rule drawn in the page's own rule colour under each, at top + 12. Usable width is
**215 px** (x 4–218). 13 is the minimum pitch [font-candidates.md](font-candidates.md)
measured for Galmuri9 and one more than the minimum for the game's own glyphs, so it is the
pitch both faces can share.

Both faces are re-aligned to each glyph's own ink and advanced by `ink + 1`, which is the
"game sheet re-aligned" variant of font-candidates.md rather than the engine's fixed 14 px
pitch — a fixed pitch would fit about 15 characters a line here.

Capacity, measured over the lowercase alphabet:

| face | mean advance (lower / caps) | chars per 215 px | per 5-line page | ASCII it cannot set |
|---|---|---:|---:|---|
| the game's own 12×12 glyphs | 6.62 / 8.77 | ≈32 | ≈162 | `"` `$` `-` `[` `\` `]` `^` `` ` `` `{` `}` `~` |
| Galmuri9 (BDF, native size) | 5.54 / 5.62 | ≈39 | ≈194 | — |

The hyphen is in that list on purpose: the sheet's only dash is a full-width minus (U+2212),
which sits high and wide, so `-` is not mapped to it. `GameFace` draws its own instead
(`TRN-04`, 2026-09-24): a 4 px stroke on the row of `e`'s crossbar, so the diary sets
"Moe-neechan" as the day files write it.

## The two faces, looked at

The game's glyphs are decoded from the one sheet on the disc (`ONMEM.BIN` child 2) by
`boku/typeset.py`, shared with the other texture recipes, using [font.md](font.md)'s formula — four interleaved 1bpp planes, `col = id % 21`, `plane =
(id / 21) % 4`, `row = id / 84` — and keyed through `research/data/glyph-table.tsv`. ASCII
reaches it by the full-width offset `U+0021..U+007E → U+FF01..U+FF5E`, with one exception the
offset gets wrong because the sheet draws the typographic character: the apostrophe is U+2019.
Galmuri9 is read from `Galmuri9.bdf` in `reference/fonts/galmuri/` (present, SIL OFL 1.1, as
`reference/fonts/SOURCES.md` records) — the shipped BDF rather than a rasterised TTF, so the
comparison is against the designed pixels and not one rasteriser's opinion of them.

Both decoders were checked against something that is not this script, and both checks were
re-run:

* The glyph sheet reproduces [font.md](font.md)'s `metrics.py` numbers **exactly**: caps ink
  mean 7.77 on rows 1–9 with `Ｉ` 1, `Ｊ` 6 and `Ａ Ｍ Ｔ Ｖ Ｗ Ｙ` 9; lowercase mean 5.62 on
  rows 0–10 with every named outlier (`ｉ ｌ` 1, `ｊ` 2, `ｆ ｒ ｔ` 4, `ｇ ｏ ｖ ｙ` 7, `ｍ ｗ` 9).
* The BDF decode was compared with Pillow rasterising the shipped bitmap strike
  (`Galmuri9Bitmap-Regular-2.40.4.ttf` at 12 px): over all 94 printable ASCII characters the
  ink box agrees in width and height on **every one**. Against the *outline* `Galmuri9.ttf` at
  9 px it agrees on 89 of 94 — `#`, `%`, `@`, `z`, `~` differ by one column — which is the
  rasteriser, and the reason the BDF is what the script reads.

The comparison sheet is `work/diary/COMPARE.png` (original, game glyphs, Galmuri9 at 1× and
3×) and `work/diary/panel-zoom.png` (the panel alone at 6×). Both were looked at.

**At 1× (240×192, which is what a player sees) both are legible and Galmuri9 is the more
comfortable.** Its cap and x-height are the same as the game's (9 and 6), but its caps are as
narrow as its lowercase, so a line holds about a fifth more and the placeholder entry sets in
four lines instead of five. Nothing crowds; the counters in `a`, `e`, `o` stay open.

**At 3× and 6× the ranking reverses, and it is a preference rather than a legibility one.** The
game's glyphs are rounder, wider and slightly irregular on the baseline — they were drawn to
sit beside hand-lettered kana — and on a page that is otherwise a child's crayon drawing they
look like they belong there. Galmuri9 reads as a modern, even, machine-cut pixel font:
cleaner, and visibly a different hand from the page around it. The game's wider caps also break
the paragraph up in a way that suits a diary.

The one place the game's set is plainly worse is punctuation, and the zoom shows it: its comma
and period are the full-width `，` `．`, which sit low and leave a full-width gap after them, so
`soon， so` and `country． I` read with a visible hole where English wants a tight comma. It has
no straight or double quote at all, its `(` `)` are vertical-writing forms, and it has no
hyphen. Galmuri9 sets all of it correctly.

**Recommendation for the entry text specifically: the game's own glyphs**, with Galmuri9 as
the fallback if an entry will not fit in five lines of 32. The diary is the one surface where
matching the page matters more than density, and the density difference (162 against 194
characters) is not the difference between fitting and not for a child's four-sentence entry.
The punctuation gap is the cost, and it is a *drawing* job of a dozen cells rather than a
reason to change face. This is a different recommendation from `TXT-06`'s for *dialogue*, and
for a different reason: dialogue is rendered by the engine over arbitrary backgrounds at a
fixed band width, where Galmuri9's evenness wins.

## Does it round-trip and build?

Yes. `build --page 001 --face game` produced **2,268 byte edits, 7,464 bytes**, one occurrence,
and wrote `build/diary/image.img` with **10 sectors** rewritten (LBA 47831–47840, inside
`BOKU.BIN`). The page is 8bpp so a byte is a pixel: 7,464 changed pixels out of the panel's
221×73 = 16,133, which is the text plus the rule swap.

Both verifications were made red on purpose rather than assumed:

* **Old bytes.** Flipping one bit of one edit's `old` and running `build(dry_run=True)` is
  refused with `BOKU.BIN+0x5b60c22 holds 04 22 and the build expects fb 22 (texture
  _DATA_NIKKI.BIN_NIKKI_001__000000 …)`. The unmodified edits pass.
* **EDC/ECC.** Flipping one user-data byte of LBA 47831 in the written image makes
  `build.verify_written_sectors` return exactly `[47831]`; restoring it returns `[]`. That
  check lives in `boku build`'s CLI and **was not being run by this prototype** — `verb_build`
  called `build()` and reported the sector count only. It now runs it and prints the result,
  which is the one substantive change this pass made to the script.

The image boots. On Beetle PSX (`tools/libretro/run_core.py`, `boot-to-dialogue.press`) the
patched image's frame 5850 is **byte-identical** to the stock boot's
(`work/beetle/stock/first-dialogue.png`, sha-256 `e35ec1d5…`).

## In game: reached by setting the mode (2026-09-23, `GFX-04`)

Walking to the desk at night was never managed (the clock and navigation searches of the
first pass are in git history, `research/diary-redraw.md` before `GFX-04`). What works is
entering the diary mode directly: after any in-game frame, the five words `mode_set` writes
(`tools/redux/book-pokes.lua` names them — previous mode `0x800237E5`, mode `0x800237E0` and
`0x800237E4` = 11, change flag `0x80024728` = 1, arena base `0x800258E0` = level A's
`0x801179F4`) put the desk up with the diary open and the cursor on its good-night button.
○ asks "write the diary and sleep?", ○ again opens **tonight's page**, which is
`g_diary_today` (`0x8004612C`) — so poking that first chooses the page. Measured on Beetle
from `boot-to-dialogue.press`: pokes at frame 6500, the page id at 7000, ○ at 7020 and 7320,
the page up by 7590, drawn at screen (53, 16), with the day numeral composited as expected.

**The page is drawn lit**, colour-modulated a few levels off its CLUT (165 → 168), unlike the
title and settings sprites, which show their CLUT colours exactly. A pixel check has to allow
for it: measured, every texel the build changed lands within 15 levels of luminance of its CLUT
colour at the right offset, and ~200 off at an offset one pixel wrong
(`tests/test_real_texture_text_beetle.py` gates at 24).

## The build (`GFX-04`)

The recipe is in the package now: `boku/diary.py` holds the panel geometry, `measure_page`
and `redraw_page` (the prototype imports them), and `boku/texture_text.py`'s `diary` family
builds every page `translation/textures/diary.txt` has an entry for, keyed by **page id**
(`nikki@NIKKI_072`) because the page is chosen at run time from `g_diary_pages[day]` and can
serve more than one day. For each entry it:

* refuses `NIKKI_000`, the unused dummy page, and an id that names no page;
* **re-measures the page on the contributor's import** (`measure_page`) and refuses one whose
  panel disagrees with the geometry above — `NIKKI_047`'s shading columns
  (`diary.SHADED_PAGES`) are expected there and nowhere else, and any other extra column is
  refused; the redraw keeps them because each column keeps its own background;
* redraws it (`redraw_page`) and refuses an entry that wraps past the five lines, has a word
  wider than a line, uses a character the glyph sheet cannot draw, or a ` // ` — every refused
  page reported at once.

`./make.sh textures check` runs the same build without writing an image (`--out DIR` writes
each rebuilt page as a PNG to look at) — the per-page lint a translator runs; `boku build
--textures` runs it too, and refuses the same way. The date strip stays as it is — Jay,
2026-09-21: keep the Japanese month/day symbols with the composited numeral.
