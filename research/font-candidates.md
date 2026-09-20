# English on screen: advance models, typefaces, and what a page holds (PLAN `TXT-02` leftover, `TXT-03`, `TXT-06`, `TXT-07`)

Evidence for two decisions that are Jay's — `TXT-03` (how English gets on screen) and `TXT-06`
(the typeface) — plus the measurements `TXT-05`/`TXT-07` need. **Measured** = printed by a script
under the gitignored `work/txt06/` on 2026-09-20 against the dump in [disc-recon.md](disc-recon.md);
*estimate* and *recommendation* say so. The mock-ups are composited over the game's own frames, so
they stay in `work/txt06/` and are described here, not shown. The engine facts this builds on are
in [font.md](font.md) (cell, planes, `glyph_draw`'s three sprites), [text-renderer.md](text-renderer.md)
(§ 4a `band2`, § 4b the 9-slot advance hook) and [renderer-runtime.md](renderer-runtime.md) (what
the in-RAM trial looked like).

Regenerate, from the repo root (Pillow through `uv run --no-project --with pillow python …`, run
inside `work/txt06/`): `python3 work/txt06/slots.py` (slot recount, stdlib) · `gamepages.py`
(Japanese page sizes) · `measure.py` (sample-page fit) · `extrapolate.py` (whole-script estimate) ·
`sheets.py` (every image). Fonts are fetched into `reference/fonts/`; `reference/fonts/SOURCES.md`
has URL, version, licence and a sha-256 for each.

## 1. Glyph slots: the structural recount (`TXT-02` leftover)

`work/txt06/slots.py` marks an id used if it occurs in any of the 6,183 structural text sites
(`work/rec03/text_sites.py`'s walk, imported, never its `main`), in any array of
[`data/text-arrays.tsv`](data/text-arrays.tsv) (which adds the raw tables the walk does not
cover), as a code immediate or `0x34 + d` digit ([text-outside-events.md](text-outside-events.md)
§ "Text made at run time", [font.md](font.md) § "The draw code"), or in the three small-kana nudge
tables (`0x80036700`, `TITLE 0x80079BD4`, `MUSI 0x8007A8B8`).

* Used: 1,328 ids by event/array text, **1,333** with raw tables and code (adds 40 ％, 47 △,
  1431, 1432, 1456). Id 0 is the space.
* **Free: 179 of 1,511 — 155 inked-but-unused + the 24 blank cells 1488–1511.** Not 583: that figure
  came from a heuristic scan filtered to lines with a speaker label, which missed most of the
  script. With the 168 cells the sheet can grow by ([font.md](font.md)), **347** are available.
* By class (free / used): punctuation 1–51 20 / 31 · digits 0 / 10 · capitals 17 / 9 (used:
  `Ａ Ｂ Ｃ Ｌ Ｍ Ｐ Ｔ Ｘ Ｚ`) · lowercase 25 / 1 (`ｚ`) · hiragana 2 / 79 · katakana 7 / 77 · kanji
  84 / 1,111 · specials 1474–1487 0 / 14.
* Free ids: `3 7 10-11 17 19-20 31 33-36 39 41-44 48-50 65-72 75-76 78-80 82-84 86 88-112 147 191
  199 231 272 274 276-278 292 296 309 421-423 427 447 770 772-773 780 785-787 792 794-796 802 811
  815-817 820 826-827 832 837 839 842 844 883 951 973 977 981 984 1053 1060 1066 1081 1083 1085
  1124 1245 1302 1307 1315 1327 1333-1339 1341-1342 1344 1346-1351 1355-1359 1361 1374 1407-1412
  1430 1457 1463 1466 1469 1488-1511`. Contiguous runs of 8 or more: 65–72, 88–112, 1488–1511.
* **Correction to [font.md](font.md):** "every capital but `Ｔ` is unused by the Japanese text" is
  wrong — nine capitals and `ｚ` are used. Redrawing them in place is still harmless (they stay the
  same letters); only their position inside the cell changes in untranslated lines.

**What English needs versus what is free.** The style guide
([style-guide.md](../translation/style-guide.md) § 3, § 9) asks for *no* macrons in game text,
three full stops for an ellipsis, straight ASCII punctuation, hyphens everywhere, and `~` for sung
lines (§ 10). Needed: 52 letters + 10 digits + about 25 punctuation marks. Already in the sheet
at a usable id: all 62 alphanumerics and `, . : ; ? ! _ | / + = < > % # & * @ ‘ ’ ―`. **New cells
to draw: about 12** — `' " ( ) - ~ $ [ ]` and, if wanted, `… “ ” ♪` (16 if Q9 ever turns macrons
on: `ō ū Ō Ū`). The sheet's `−` (id 30) is a full-width minus and its `（ ） … 〜` are
vertical-writing forms, so none of those can be reused.

Slots are therefore not a constraint, but *where* the new cells go decides the size of the width
table, because the 9-slot hook indexes it by glyph id (`sltiu at, v0, N`): below id 114 only seven
free cells are junk English does not want (`゛ ± ÷ ￥ → ← ↑`); **below id 279 there are 16** (those
seven plus kana 147, 191, 199, 231, 272, 274, 276–278). So about 12–16 new cells fit under id 279
and the table is **279 bytes**. Putting them in the blank run 1488–1511 instead costs a
1,512-byte table, which does not fit the 1,116-byte heap-gap and would have to go in the dead
debug printer ([text-renderer.md](text-renderer.md) § 6).

## 2. The mock-up renderer

`work/txt06/render.py` draws what `glyph_draw` draws: per glyph a 12×12 1-bit sprite at the pen
in (24,24,24) over two shadow copies at (x+1, y) and (x, y+1) in (148,148,140); anything wider
than the 12-px sprite is clipped, as on hardware; the pen advances by the model's advance; a line
break returns x to the origin and adds the line pitch (13). Primitives are prepended to one
ordering-table slot, so a *later* glyph lies *under* an earlier one — the frame is painted last
glyph first, which reproduces the `H`-over-`e` collision the emulator trial showed at 8 px. The
band is `band2` (Y = 168, H = 72, opaque (231,231,231), or additive white 168 for the translucent
variant); pen (24, 176). Backgrounds are two un-banded emulator frames from
`work/txt01-emu/shots/`: `t8-01050` (the courtyard, wide shot) and `t8-02700` (the close-up where
five actors stand with their legs in the bottom third). Wrapping is greedy, at spaces only, to
272 px (pen 24 + a symmetric right margin) — 300 px (10-px margins) is also reported. A "CRT-ish"
column (3×, horizontal blur, scanlines) and a phone-scaled bilinear crop are rough looks, not
simulations.

Advance models, all kerning-free:

| model | what it needs in the engine | how the glyph sits |
|---|---|---|
| (a) fixed 14 | nothing — today | sheet untouched |
| (b) fixed 8 | one immediate (`0x8002BF7C`) | sheet untouched |
| (c1) width table, sheet untouched | the 9-slot hook + table | glyph still drawn at its native 1–5 px bearing; advance = bearing + ink, so the visible gap before each glyph is *its own* bearing |
| (c2) width table, Latin cells re-aligned | the same hook + table, and the Latin cells shifted to column 0 | advance = ink + 1; space 4 |
| (d) width table, replacement cells | the same hook + table, new cells | advance = the font's own; a negative bearing (`j`) is shifted right by the baker |

(c1), (c2) and (d) are the *same code*. The "real hook" of [text-renderer.md](text-renderer.md)
§ 4b — adjusting x before `jal glyph_draw` — is only needed if the sheet may not be touched.

## 3. Does a page fit? (the feasibility number)

Page count per message is fixed by the voice timing, so the question is whether every English
page fits the lines one band holds. Corpus: the three files in `translation/samples/` — 65
messages, **80 pages**, median 36 characters, longest 92 — with the speaker label inline on a
message's first page (`Aunt: …`), as the Japanese has it.

**Whole-script estimate.** The samples are 80 pages of 3,484. `gamepages.py` pairs each sample
page with its Japanese page (label, brackets and indent cells excluded): English = **2.63
characters per Japanese glyph** (least squares through 80 pairs, intercept ≈ 0; residual p10 −11,
p90 +15, max +28 characters). The longest Japanese page in the game is 41 glyphs → about 108
characters typical, 136 at the worst residual. Every game page × every residual, plus 7
characters of label on *every* page (conservative), against each font's measured characters per
wrapped line:

| font · model | chars / 272-px line (wrapped) | sample pages in ≤ 3 lines (272 px, label) | *est.* % of all 3,484 pages in 2 / 3 / 4 lines, 272 px | same, 300 px |
|---|---|---|---|---|
| game sheet · (a) fixed 14 | 17.2 | 76 % (worst page 6 lines) | 31 / 57 / 79 | 37 / 65 / 86 |
| game sheet · (b) fixed 8 | 32.4 | 99 % | 74 / 97.1 / 100 | 81 / 98.9 / 100 |
| game sheet · (c1) table, native bearings | 36.4 | 99 % | 83 / 99.3 / 100 | 89 / 99.9 / 100 |
| **game sheet · (c2) table, re-aligned** | 43.6 | 100 % | 93 / 100 / 100 | 97 / 100 / 100 |
| Galmuri9 · (d) | 51.3 | 100 % | 98 / 100 / 100 | 99.5 / 100 / 100 |
| Ark Pixel 12 proportional · (d) | 45.4 | 100 % | 95 / 100 / 100 | 98 / 100 / 100 |
| Pixel Operator · (d) | 41.7 | 100 % | 91 / 99.9 / 100 | 96 / 100 / 100 |
| Galmuri11 · (d) | 39.4 | 100 % | 88 / 99.8 / 100 | 94 / 100 / 100 |
| m5x7 · (d) | 49.4 | 100 % | 98 / 100 / 100 | 99 / 100 / 100 |
| Cozette, Terminus 6×12, Spleen 6×12, Tamzen 6×12, Monogram (6-px mono) · (d) | 43.4 | 100 % | 93 / 100 / 100 | 97 / 100 / 100 |
| Departure Mono (7-px mono) · (d) | 36.7 | 100 % | 83 / 99.3 / 100 | 89 / 99.9 / 100 |
| Press Start 2P (8-px mono) · (d) | 32.4 | 99 % | 74 / 97.1 / 100 | 81 / 98.9 / 100 |
| Ark Pixel 10, Spleen 5×8, Tamzen 5×9 · (d) | 52–53 | 100 % | 99 / 100 / 100 | 99.8 / 100 / 100 |
| Galmuri7 / Galmuri11 Condensed / Tiny5 · (d) | 63 / 60 / 78 | 100 % | 99.9–100 / 100 / 100 | 100 / 100 / 100 |

Reading it: **with any per-glyph advance at about 6 px mean or less, every page of the game fits
three lines and nothing has to be cut**; the fixed pitches do not (fixed 14 fails a quarter of
even the samples). The estimate's weakness is its base — 80 pages from three scenes, one
translator's density — and the ratio will move when more of the script exists; the margin is
what matters: at (c2) the worst modelled page is 143 characters against a three-line capacity of
about 131, i.e. the far tail sits at the limit and four lines absorb it. `TXT-07`'s lint should
be the real gate.

## 4. Typefaces at the 12×12 cell (`TXT-06`)

All rendered through the same engine model with the same lines (a short line, a long Aunt page
with label, the longest sample page, a punctuation torture line, and the five-row syrup menu).
"Ink" is the height of the dialogue character set; the minimum line pitch is ink + 1 (the shadow
row). Licence facts and URLs: § 6.

| font | cap / x-height / ink | mean advance | fits 12×12? | has `— … “ ” ♪ ō ū` | note from the mock-ups |
|---|---|---|---|---|---|
| game sheet, re-aligned | 9 / 6 / 11 | 5.9 | yes | no — 12 cells to draw | the game's own look; wide round letters (`o` 7 px), light; `p`/`g` descenders read a little odd; survives the blur well because letters are wide; pitch could drop to 12 |
| **Galmuri9** | 9 / 6 / 12 | 5.1 | yes | all | same cap and x-height as the game's set, tighter and more even; built for handheld-game dialogue; pitch 13 is its minimum |
| Ark Pixel 12 prop. | 9 / 6 / 12 | 5.7 | yes | all | rounder and wider than Galmuri9, space is 6 px (wide); ships matching Japanese glyphs |
| Pixel Operator | 9 / 7 / 11 | 6.2 | `$` clips | no ♪, no macrons | tallest x-height of the set — the most legible small, the fewest characters per line; squarish `a`/`u` |
| Galmuri11 | 11 / 8 / 13 | 6.5 | **no — `g j p q y` clip** | all | too tall: lines touch at pitch 13 |
| Galmuri11 Condensed | 10 / 7 / 12 | 4.4 | yes | all | very narrow; strokes merge in the blurred column |
| Cozette / Terminus / Spleen 6×12 / Tamzen 6×12 | 8 / 6 / 12 (Tamzen 7 / 5 / 11) | 6.0 mono | yes | Cozette, Terminus: all | terminal fonts: even rhythm, slashed or dotted zero, read as "computer", not as a storybook |
| Departure Mono | 8 / 6 / 11 | 7.0 mono | yes | all | handsome, but monospace at 7 px costs 20 % of the line |
| m5x7 | 7 / 5 / 9 | 5.2 | yes | macrons only | small: cap height 7 |
| Monogram | 7 / 5 / 9 | 6.0 mono | yes | no | small |
| Ark Pixel 10 / Galmuri7 / Spleen 5×8 / Tamzen 5×9 | 7 / 5 (5 / 4) | 4.2–5.0 | yes | Ark, Galmuri: all | small: x-height 5 or less |
| Silkscreen | 5 / 5 / 7 | 5.2 | yes | most | capitals only by design — wrong for dialogue |
| Tiny5 | 5 / 4 / 7 | 3.4 | yes | most | illegible under the shadow |
| Press Start 2P | 7 / 5 / 8 | 8.0 mono | yes | all | too wide (as expected), heavy |
| GNU Unifont | 16 tall | — | **no** | — | 8×16 / 16×16 glyphs; not fetched |

The phone case: Mode One shows 240 lines on a panel about 64 mm tall in landscape (*assumption:*
a 6-inch phone, 4:3 image at full height), so one game pixel ≈ 0.27 mm. An x-height of 6 px is
1.6 mm and a cap height of 9 px is 2.4 mm — about the size of 9-pt print at reading distance; an
x-height of 5 is 1.3 mm and of 4 is 1.1 mm, under what is comfortable. That is why every face
with x-height < 6 is marked "small" above regardless of how much it fits.

## 5. Lines and band height (`TXT-07`)

A band holding N lines at pitch p needs `4 + (N − 1)·p + 12 + 1 + 3` rows (top pad, cells, shadow
row, bottom pad):

| lines | pitch 13 | pitch 12 | pitch 11 |
|---|---|---|---|
| 2 | 33 | 32 | 31 |
| 3 | **46** | 44 | 42 |
| 4 | 59 | 56 | 53 |
| 5 | 72 | 68 | 64 |

* **H = 72 holds 4 lines comfortably** (pen y 176, last line's shadow ends at row 228). Five lines
  fit only with the pen at 172 and the last shadow row at 239 — the bottom edge of the frame,
  which a CRT's overscan eats. Treat H = 72 as a 4-line band.
* Pitch: minimum is ink + 1 — **12 for the game's own glyphs, 13 for Galmuri9 and Ark Pixel 12**
  (at 12 their descenders' shadows touch the next line's ascenders); 11 works only for the
  small faces (ink ≤ 10). The literal is `0x8002BF48`.
* **What the text needs is 3 lines, mostly 2.** Sample pages with the label inline at 272 px:
  game sheet re-aligned — 48 one-line, 29 two-line, 3 three-line, none longer; Galmuri9 — 60 /
  20 / 0. Whole-script estimate (§ 3): 93–98 % of pages in two lines, all in three.
* So the 4-line band (H ≈ 58) asked about is *more* than needed: **a 3-line band, Y = 194,
  H = 46 at pitch 13, shows 26 more rows of the scene than `band2`'s 72** and still holds every
  modelled page; the next-page arrow's stock position (266, 220) is still inside it. In the
  close-up mock-up the 72-row band covers the smallest child up to her eyes and everyone else
  from the waist down; the 46-row band shows her whole and cuts the others at the knee. The translucent variant (fade level 168) over the
  same frame is also mocked up; it is legible over these two backgrounds.
* The speaker label inline costs 5–9 characters on a message's first page only and changed no
  sample page's fit under any per-glyph model. A label on its own line would cost a line of
  every first page and push the band to 4 lines — inline is cheaper and is what the original does.
* Left for `TXT-07` proper: the other 25 surfaces. Each draws at its own fixed step (12 px for 20
  of them) until it gets its own hook, and **narrow left-aligned cells look gappy at a fixed
  12-px step** ("M e l o n") — true of every option here, including the game's own glyphs
  re-aligned. The syrup menu's longest row, "Rainbow Special", is 95 px (game sheet re-aligned),
  76 px (Galmuri9), 180 px at the stock fixed 12.

## 6. Licence facts (read from the files that ship with each font, 2026-09-20)

| font | licence | source | clean for this repo? |
|---|---|---|---|
| Galmuri 2.40.4 | SIL OFL 1.1, © Lee Minseo; no Reserved Font Name declared in the header | <https://github.com/quiple/galmuri> | yes |
| Ark Pixel 2026.09.01 | fonts SIL OFL 1.1 (`OFL.txt` in each release zip); build code MIT | <https://github.com/TakWolf/ark-pixel-font> | yes |
| Pixel Operator | CC0 1.0 (`LICENSE.txt` in the zip) | <https://www.dafont.com/pixel-operator.font> (author's notabug repo 404 on the day) | yes |
| Departure Mono 1.500 | font SIL OFL 1.1 (`LICENSE` inside the release zip); the repo-root MIT file covers the website — GitHub's licence badge is misleading | <https://github.com/rektdeckard/departure-mono> | yes |
| Cozette 1.30.0 | MIT | <https://github.com/the-moonwitch/Cozette> (formerly slavfox/Cozette) | yes |
| Spleen 2.2.0 | BSD 2-Clause | <https://github.com/fcambus/spleen> | yes |
| Terminus 4.49.1 | SIL OFL 1.1, **Reserved Font Name "Terminus Font"** — a modified sheet must not carry the name | <https://terminus-font.sourceforge.net/> | yes, renamed |
| Silkscreen, Tiny5, Press Start 2P | SIL OFL 1.1 (`OFL.txt` in google/fonts) | <https://github.com/google/fonts/tree/main/ofl> | yes |
| m5x7 | itch.io licence field "Creative Commons Zero v1"; page text "free to use but attribution appreciated"; no licence file ships | <https://managore.itch.io/m5x7> | probably — the only record is a web page |
| Monogram | "free and CC0" on the page and in the itch.io licence field | <https://datagoblin.itch.io/monogram> | probably — same |
| Tamzen | Tamsyn licence: "free… use, copy, modify, and distribute it as you see fit" — permissive, home-made, not OFL/OSI | <https://github.com/sunaku/tamzen-font> | usable, not tidy |
| m6x11 | "free to use with attribution", no licence named | <https://managore.itch.io/m6x11> | **no** — not fetched |
| GNU Unifont | GPL 2+ with font exception / SIL OFL 1.1 dual | <https://unifoundry.com/unifont/> | licence yes, size no |

The game's own glyphs are the disc's pixels: a re-aligned sheet can never be committed. Option (c2)
therefore means **a tool that shifts the Latin cells at build time from the contributor's own
`ONMEM.BIN`**, plus about 12 punctuation cells drawn for the project and committed (new pixels,
ours). An OFL/CC0 face is committed as its source file plus the baker `TXT-06` already asks for.

## 7. Recommendations — for Jay; both rows are `[MINE: product]`

**`TXT-03` — recommendation: horizontal `band2` + the in-place 9-slot width table + cells that are
left-aligned in the sheet. The "real hook" for bearings is not needed.**

* The cheap hook is enough *because the sheet has to be edited anyway* (the missing `' " ( ) -`),
  and once it is edited, zeroing the bearings there is free. (c1) — table only, sheet untouched —
  is the one configuration that would want the real hook, and the mock-up shows why it is not
  worth keeping: gaps of 1–5 px that follow the next glyph's bearing ("cou ld", "L iv ing"), and
  17 % fewer characters per line than (c2).
* What the cheap hook cannot do, and whether it matters: kerning (none of the candidates needs it
  at this size); ink wider than 12 px (no candidate has any in the dialogue set); negative
  bearings (one glyph, `j`, shifted by the baker). Wrapping is done at build time — the engine has
  none.
* Put the ~12 new cells under id 279 so the table is 279 bytes (§ 1).
* Fixed 8 px is not a fallback: 97 % estimated page fit and visible collisions.
* Subtitle overlay and two-letters-per-cell are not needed: the renderer change is nine
  instructions and a table, and the pages fit.
* A cost to know: re-aligning Latin cells in place moves the ten Latin ids and the digits that
  untranslated Japanese text and the code-drawn digit sites use by up to 5 px inside their cell.
  Cosmetic, and only until those surfaces are translated or hooked.

**`TXT-06` — recommendation: Galmuri9 (SIL OFL 1.1); runner-up, the game's own Latin glyphs
re-aligned.** Look at section B of the contact sheet before taking this.

* Galmuri9 has the *same* cap height and x-height as the game's own Latin (9 / 6), so it sits in
  the cell and beside leftover Japanese the same way; it is more even in rhythm, 18 % more
  characters per line, and already has every typographic character the style guide could want,
  macrons included, under a licence that lets the baked sheet's source live in the repo.
* The game's own glyphs are the conservative choice — the look the developers chose, wide letters
  that survive blur — at the price of drawing 12 cells to match and of a build step that can only
  run against a disc. If Jay's eye prefers them, nothing in § 3 or § 5 argues against it: every
  page still fits three lines.
* Ark Pixel 12 is the third option worth a look (rounder; the only candidate with matching
  Japanese, which would matter only if mixed-script lines ever appear). Pixel Operator is the
  pick if phone legibility is weighted above everything (x-height 7).
* Not recommended: every face with x-height < 6 (phone), the 6-px terminal monospaces (tone),
  Galmuri11 (does not fit the cell), Press Start 2P and Departure Mono (width).

**Band** (`TXT-07`, follows from the above): 3 lines at pitch 13, H = 46, Y = 194, label inline.

## 8. The mock-ups (in `work/txt06/`, gitignored)

* `DECIDE.png` — one tall sheet, three sections, each row = the 1× frame, the band at 3×, the band
  at 3× "CRT-ish". **A**: the four advance models with the game's own glyphs on the same long Aunt
  line. **B**: sixteen typefaces under the per-glyph advance, the game's own re-aligned first,
  labelled with licence, cap/x-height, characters per line and sample fit. **C**: band variants
  over the close-up — H = 72 opaque, H = 72 translucent, H = 46, H = 58, and H = 37 at pitch 11 —
  for the game's glyphs and Galmuri9. The sections also exist separately as
  `out/decide-A-advance-models.png`, `out/decide-B-typefaces.png`, `out/decide-C-band-height.png`.
* `out/font-<key>.png` — per font: five 1× frames (short line, long line, longest sample page,
  punctuation line, the syrup menu as rows in a centred panel — a layout sketch, since
  `select_draw` is its own surface), two bands at 3×, and the CRT-ish and phone-scaled crops.
* `out/crop-shortlist-3x.png` (game re-aligned, Galmuri9, Ark 12, Pixel Operator, Galmuri11,
  Departure Mono, same line, 3×), `out/crop-band-heights-1x.png` (H = 72, H = 46, H = 72 translucent, at 1×),
  `out/specimen.png` (every font, one pangram line, no shadow).
* The game-sheet rows use nine hand-drawn stand-ins for `' " - ~ ( ) [ ] $` in the sheet's weight
  so that real sentences can be shown; they are placeholders, not proposals.

## Open

* The fit estimate rests on 80 sample pages; re-run `extrapolate.py` as the translated corpus grows.
* Shadow overlap order (later glyph under earlier) is inferred from `AddPrim` prepending and from
  the trial's `H`/`e` collision, not read from `glyph_draw`'s three `AddPrim` calls; it only
  matters when inks touch, which (c2)/(d) avoid.
* Not mocked: SELECT in its real geometry, the 24 other surfaces, light-on-dark text
  (`g_text_flags & 4`).
