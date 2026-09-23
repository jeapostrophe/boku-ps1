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
`tex@<member>.<key>` for a single texture's strings (`tex@T_TITLE.0`); the bulk families will be
`nikki@NIKKI_nnn`, `mzkan@…`, `tzkan@…` (`research/textures-plan.md` § "The new English text
this creates"). An id may appear once across all the files.

A string is set in the game's own glyphs, so it may only use characters the glyph sheet has:
letters, digits and `! # % & ' ( ) * + , . / : ; < = > ? @ _ |`. There is **no hyphen and no
double quote** on the sheet, and the build refuses a string that uses one; the sheet's `(` `)`
are vertical-writing forms that look wrong in a line. A string that does not fit its space is
refused rather than shortened (README: nothing is cut to fit). Where each texture's space is,
and what the build does to it, is `research/texture-recipes.md`.

## Files

| file | textures | row |
|---|---|---|
| [ui.txt](ui.txt) | the title menu (`T_TITLE`), the settings screen (`T_CONFIG`), the album heading (`T_MEMORY`) | PLAN `GFX-07` |
| [signs.txt](signs.txt) | the notice board on the path to the beach (`M_C15`) | PLAN `GFX-09` |

To change a string, edit it here and run `./make.sh build-days`; the build prints which
texture families it typeset.
