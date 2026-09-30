# Texture strings

The English that the build typesets into the game's textures — the menu words, plates and
pages that the original has as pixels rather than as text (`research/textures-plan.md`, path
**P**). Licence: CC BY-SA 4.0 (`LICENSE-translation`). There is no Japanese here and no image:
each texture is rebuilt at build time from the contributor's own import, and only the English
is tracked (CLAUDE.md § "This repo is public").

## Format

One string per row: `id<TAB>English`. `#` lines and blank lines are notes. ` // ` splits a
string into lines, and only where the file's comment for that texture says it may; anywhere
else the build refuses it rather than drawing the slashes. The id is
`tex@<member>.<key>` for a single texture's strings (`tex@T_TITLE.0`); the bulk families are
`nikki@NIKKI_nnn`, `btn@<member>.<key>`, `rec@<member>.<key>`, `mzkan@<page>.<field>`,
`tzkan@<page>.<field>` and `sumo@<part>.<key>`.
An id may appear once across all the files.

A string is set in the game's own glyphs unless its texture says otherwise (a button whose
row in `boku/texture_buttons.py` names one of the pixel faces in `boku/faces/`, which also
have `-`, `"` and `[ ]`), so it may only use characters the glyph sheet has:
letters, digits and `! # % & ' ( ) * + , . / : ; < = > ? @ _ |`, plus a hyphen `-` the face
draws itself (the sheet has none; `boku.typeset.GameFace`). There is **no double quote**, and
the build refuses a string that uses one; the sheet's `(` `)` are vertical-writing forms that
look wrong in a line. A string that does not fit its space is
refused rather than shortened (README: nothing is cut to fit). Where each texture's space is,
and what the build does to it, is `research/texture-recipes.md`.

## Files

| file | textures | row |
|---|---|---|
| [ui.txt](ui.txt) | the title menu (`T_TITLE`), the settings screen (`T_CONFIG`), the album heading (`T_MEMORY`), the epilogue's closing card (`OTI0n`) | PLAN `GFX-07`, `GFX-10` |
| [signs.txt](signs.txt) | the notice board on the path to the beach (`M_C15`); Saori's farewell note (`M_I14000`); the hunters' warning board (`M_I23000`); the keep-out sign on the upstairs door (`M_I18`) and the bug-trading notebook's cover (`M_S01000`), both hand-lettered in marker | PLAN `GFX-09`, `GFX-08` |
| [buttons.txt](buttons.txt) | the stone "Back" buttons, the speech-balloon buttons, the attendance card's labels, and the insect cage's two buttons and "rare" badge (`btn@<member>.<key>`) | PLAN `GFX-07`, `GFX-08` |
| [records.txt](records.txt) | labels beside numbers the game draws: the fishing record, the bug-trading notebook's card (`rec@<member>.<key>`) | PLAN `GFX-07` |
| [sumo.txt](sumo.txt) | a bug-sumo bout: the stamina plate, the rank chalked on the desk, the winning-move banner (`sumo@<part>.<key>`) | PLAN `GFX-12` |
| [books.txt](books.txt) | the insect book and the kite book, one row per field of a page (`mzkan@<n>.<field>`, `tzkan@<n>.<field>`) | PLAN `GFX-06` |
| [diary.txt](diary.txt) | the picture diary, one entry per page id (`nikki@NIKKI_nnn`), every page but the dummy `NIKKI_000` | PLAN `GFX-04`, `TRN-04` |

To change a string, edit it here and run `./make.sh textures check` (add `--out
work/textures-en` to look at the result), then `./make.sh build-days`; the build prints which
texture families it typeset and refuses what `check` refuses.
