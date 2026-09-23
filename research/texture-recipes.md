# Texture recipes — English typeset into textures at build time (PLAN `GFX-07`)

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
  `FAMILIES` under the id before the last dot (`tex@T_TITLE`). It reads the image out of the
  contributor's import, checks the image is the one it was measured on, blanks and typesets
  in the image's own palette indices, and returns `ByteEdit`s — the texture's changed bytes
  at every occurrence (`boku.textures.patches_for`) plus any code or data word the screen
  needs changed to show the English. A family takes all its strings or refuses; an id no
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
bands changed. `tests/test_real_title_menu_beetle.py` (`./make.sh emu-test`) boots an image
carrying only these edits on Beetle to the menu (START at frame 3300, shot at 3650) and
requires every opaque texel of the three idle lines to show its CLUT-0 colour on screen
exactly; the stock image fails it, and so does an image with the English but not the widened
records.
