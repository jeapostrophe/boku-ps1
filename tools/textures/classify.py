"""Turn the extracted TIM inventory into the tracked census (PLAN REC-08).

    ./make.sh texture-census

**Reads** `work/rec08/distinct.tsv` — one row per distinct image (id, sha1, depth, size,
CLUT count, copies, members), written by the gitignored `work/rec08/extract.py` from the
contributor's own import.  **Writes** `research/data/texture-census.tsv`: the same rows
with the classification this file's rule table carries.  Neither the pixels nor any of
the game's text passes through here, which is why this half is tracked and the extractor
is not (CLAUDE.md § "This repo is public").

The rules are the record of what was seen, image by image, on `work/rec08/sheets/*.png`
and the zoomed crops in `work/rec08/crops/`.  A rule is keyed by the distinct-image id
(member path + offset of the first occurrence), which is stable as long as the archive
is; the short T#### ids on the contact sheets are a sheet-local convenience and are
deliberately NOT the key.  First matching rule wins; anything unmatched falls through to
a no-text default, which is where the tile, model-texture and plain-scenery bulk lands.

has_text is conservative: `maybe` means small or CLUT-0-illegible marks that are
probably lettering but were not read.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DISTINCT = ROOT / "work" / "rec08" / "distinct.tsv"
CENSUS = ROOT / "research" / "data" / "texture-census.tsv"

# (id regex, has_text, category, amount, style, difficulty, notes)
RULES: list[tuple[str, str, str, str, str, str, str]] = [
    # --- the picture diary ------------------------------------------------------------
    (
        r"^_DATA_NIKKI\.BIN_NIKKI_000__",
        "yes",
        "picture-diary page",
        "a word",
        "plain type",
        "easy (flat page)",
        "unused placeholder page: empty text columns and a 'this is a dummy picture' caption",
    ),
    (
        r"^_DATA_NIKKI\.BIN_NIKKI_\d+__",
        "yes",
        "picture-diary page",
        "a paragraph",
        "plain type, vertical columns",
        "easy (flat lined page)",
        "crayon drawing on the upper half, 4-10 vertical text columns below; the date reads "
        "'8 month / day' with the numerals left blank for the renderer",
    ),
    (
        r"^_DATA_NIKKI_W\.BIN__005450$",
        "maybe",
        "title/menu/UI art",
        "a word",
        "unknown",
        "unknown",
        "the one non-numeral image in NIKKI_W.BIN (28x184, 4 CLUTs): a pull cord with a star, "
        "an oval tag, a wreath, a mushroom and pencils - the tag carries about three glyphs "
        "that no CLUT here resolves",
    ),
    (
        r"^_DATA_NIKKI_W\.BIN__",
        "no",
        "calendar/clock",
        "none",
        "numerals",
        "n/a",
        "one of the 31 day-of-month numeral tiles (14x10) composited into the diary page's "
        "date line",
    ),
    # --- the reference books ----------------------------------------------------------
    (
        r"^_DATA_MZKAN\.BIN__",
        "maybe",
        "title/menu/UI art",
        "a word",
        "unknown",
        "unknown",
        "MZKAN.BIN (no digit) is not a page: a 44x74 sprite set - a flower badge and two small "
        "plates carrying two or three glyph-like marks that no CLUT here resolves",
    ),
    (
        r"^_DATA_MZKAN[01]\.BIN__",
        "yes",
        "insect/fish/item book",
        "a paragraph",
        "plain type, vertical + horizontal",
        "easy (flat page)",
        "insect encyclopedia spread: species name, family, wingspan, food, then a body of text",
    ),
    (
        r"^_DATA_TZKAN\.BIN__",
        "yes",
        "insect/fish/item book",
        "a paragraph",
        "plain type, vertical",
        "easy (flat page)",
        "kite encyclopedia spread: kite name, difficulty bracket, how to build it",
    ),
    (
        r"^_DATA_(DOP|MOP|TOP)[AN][123]\.BIN__",
        "yes",
        "insect/fish/item book",
        "several lines",
        "stylised cover type",
        "hard (over artwork)",
        "book-opening animation frame with the cover legible: diary 'picture-diary book', "
        "insect book 'rare insect encyclopedia' plus author/photographer credits, kite book",
    ),
    (
        r"^_DATA_(DOP|MOP|TOP)[AN][456]\.BIN__",
        "no",
        "other",
        "none",
        "n/a",
        "n/a",
        "book-opening animation frame, blank pages only",
    ),
    (
        r"^_DATA_TZICON\.BIN__",
        "yes",
        "title/menu/UI art",
        "a word",
        "stylised handwriting",
        "easy (transparent)",
        "kite-workshop UI: a speech balloon, a 'back' button, portrait",
    ),
    # --- menus, records, settings ------------------------------------------------------
    (
        r"^_DATA_T_TITLE\.BIN__000014$",
        "yes",
        "title/menu/UI art",
        "several lines",
        "plain type, outlined",
        "easy (transparent)",
        "the title screen's menu: new game / continue / summer memories / settings, plus the "
        "copyright line and PRESS START BUTTON",
    ),
    (
        r"^_DATA_T_TITLE\.BIN__",
        "no",
        "other",
        "none",
        "n/a",
        "n/a",
        "title-screen atlas: the picture frame and shelf the menu sits on, no lettering",
    ),
    (
        r"^_DATA_M_S01001\.BIN__011364$|^_DATA_MZ00\.BIN__0160b0$",
        "no",
        "other",
        "none",
        "n/a",
        "n/a",
        "UI atlas page with no lettering (a framed picture wall; the insect sprite strip)",
    ),
    (
        r"^_DATA_M_S01001\.BIN__000014$",
        "maybe",
        "title/menu/UI art",
        "a word",
        "Latin logotype",
        "easy (transparent)",
        "'PLAYTIME' in Latin plus small marks that may be labels",
    ),
    (
        r"^_DATA_(M_S01000\.BIN__017d24|M_S02000\.BIN__000024)$",
        "maybe",
        "title/menu/UI art",
        "a word",
        "unknown",
        "unknown",
        "UI atlas page whose small labels CLUT 0 does not resolve",
    ),
    (
        r"^_DATA_T_MEMORY\.BIN__",
        "yes",
        "title/menu/UI art",
        "a line",
        "stylised plate",
        "medium",
        "'summer memories' album: heading plate plus thumbnails of the diary and collections",
    ),
    (
        r"^_DATA_(T_CONFIG|MZ02|MZ00|M_S0\d+|SUB|SAMP)\.BIN__",
        "yes",
        "title/menu/UI art",
        "several lines",
        "plain type and stylised buttons",
        "medium",
        "in-game UI atlas: action buttons ('back', 'look', 'net', …), settings screen "
        "(voice only / voice+subtitles, mono / stereo, on / off)",
    ),
    (
        r"^_DATA_(FS_WAL|PK_WAL|TK_WAL)\.BIN__",
        "yes",
        "title/menu/UI art",
        "several lines",
        "plain type",
        "easy (flat/transparent)",
        "collection record screen: size / average / largest / cm / count, and bait and "
        "tackle names; renders faint at CLUT 0",
    ),
    (
        r"^_DATA_T_BUMPER\.BIN__",
        "no",
        "credits",
        "none",
        "Latin logotype",
        "n/a",
        "publisher and developer logo screen; several lines of it, but all Latin logotype, so "
        "there is no Japanese to translate",
    ),
    # --- the font ---------------------------------------------------------------------
    (
        r"^_DATA_ONMEM\.BIN__004aa0$",
        "yes",
        "font/glyph sheet",
        "a paragraph",
        "bitmap glyphs",
        "n/a",
        "THE GLYPH SHEET (research/font.md: ONMEM.BIN child 2, four 1bpp planes, 12x12 cells, "
        "1512 slots). The only glyph-sheet TIM on the disc; CLUT 0 shows one plane only",
    ),
    # --- the number font, and the image the first pass mistook for it --------------------
    (
        r"^_DATA_NUMBER\.TIM__",
        "no",
        "other",
        "none",
        "numerals",
        "n/a",
        "the game's general-purpose number font, 144x10 4bpp: 0-9 plus mm / infinity / . / cm "
        "in 18 cells (research/textures-plan.md section 'Composed text')",
    ),
    (
        r"^_DATA_KAGO2\.BIN__000000$",
        "no",
        "other",
        "none",
        "numerals",
        "n/a",
        "a second, narrower number strip, 120x10 4bpp in 15 cells - a different image from "
        "NUMBER.TIM, not a copy of it",
    ),
    (
        r"^_DATA_KAGO\.BIN__002784$",
        "no",
        "other",
        "none",
        "n/a",
        "n/a",
        "green cage bars (GFX-03 re-look, 2026-09-20: not the number strip the first pass "
        "took it for)",
    ),
    # --- item / photo pictures ---------------------------------------------------------
    (
        r"^_DATA_PK_ITM\.BIN__00006c$",
        "yes",
        "insect/fish/item book",
        "a line",
        "stylised handwriting",
        "easy (flat card)",
        "item picture: the radio-exercise attendance card, title plus a footer line",
    ),
    (
        r"^_DATA_PK_ITM\.BIN__(00442c|00ce8c)$",
        "yes",
        "signage or label",
        "a word",
        "package lettering",
        "medium",
        "item picture: packaged food, a few kana on the wrapper/jar label",
    ),
    (
        r"^_DATA_PK_ITM\.BIN__012acc$",
        "maybe",
        "insect/fish/item book",
        "a word",
        "unknown",
        "hard (over artwork)",
        "item picture: an old book, title embossed and hard to read",
    ),
    (r"^_DATA_PK_ITM\.BIN__", "no", "other", "none", "n/a", "n/a", "item picture, no lettering"),
    (
        r"^_DATA_(FISH00|TK_ITM)\.BIN__",
        "no",
        "other",
        "none",
        "n/a",
        "n/a",
        "collection picture (fish / kite) on a plain field, no lettering",
    ),
    (
        r"^_DATA_PK_PHO\.BIN__",
        "no",
        "other",
        "none",
        "n/a",
        "n/a",
        "photo-album picture in a print border; the only lettering is a tiny Latin film-brand mark",
    ),
    # --- backgrounds with lettering -----------------------------------------------------
    (
        r"^_DATA_M_FILES\.BIN_M_I13000\.BIN__",
        "yes",
        "calendar/clock",
        "several lines",
        "print",
        "medium",
        "wall calendar for August: weekday heads and day numbers are Latin/numerals, but a "
        "printed sheet beside it is Japanese and very small",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_I14000\.BIN__",
        "yes",
        "signage or label",
        "several lines",
        "handwritten",
        "hard (over artwork)",
        "a notepad page left on a log - a plot-bearing farewell note, vertical handwriting",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_I15000\.BIN__",
        "yes",
        "signage or label",
        "a word",
        "stylised poster type",
        "hard (over artwork)",
        "a superhero poster on the wall, katakana title",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_I18000\.BIN__",
        "yes",
        "signage or label",
        "a line",
        "handwritten",
        "hard (over artwork)",
        "a hand-lettered 'keep out!' sign hanging on a door",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_I23000\.BIN__",
        "yes",
        "signage or label",
        "several lines",
        "hand-painted",
        "hard (over artwork)",
        "a weathered hunting-association warning board, large painted text plus a cartoon",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_I19000\.BIN__",
        "yes",
        "signage or label",
        "several lines",
        "print",
        "medium",
        "a model-aeroplane kit box: Japanese product name over Latin specification lines",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_I0600\d\.BIN__",
        "yes",
        "signage or label",
        "a word",
        "package lettering",
        "medium",
        "shaved ice on a table with a strawberry-syrup bottle; the label is two kana",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_C15[01]00\.BIN__",
        "yes",
        "signage or label",
        "several lines",
        "paint on a board",
        "medium (frontal board, wood grain)",
        "beach notice board about high tides and swimming; the same board in both variants "
        "of the map (C15000, C15100)",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_H261?0\d\.BIN__",
        "yes",
        "signage or label",
        "a line",
        "calligraphy",
        "hard (over artwork)",
        "pottery workshop: a calligraphy banner over the bench ('failure is the root of success')",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_G082?0\d\.BIN__",
        "yes",
        "signage or label",
        "a word",
        "calligraphy",
        "hard (over artwork)",
        "a hanging scroll with four characters of calligraphy",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_G140?0\d\.BIN__",
        "maybe",
        "signage or label",
        "a word",
        "print",
        "hard (over artwork)",
        "study room: a poster and a chart pinned over the desk, lettering too small to read",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_H0620\d\.BIN__",
        "maybe",
        "signage or label",
        "a word",
        "shop sign",
        "hard (over artwork)",
        "a shop front with a signboard; CLUT 0 does not resolve the lettering",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_I2100\d\.BIN__|^_DATA_M_FILES\.BIN_M_I2102\d\.BIN__|"
        r"^_DATA_M_FILES\.BIN_M_I1620?0\.BIN__",
        "maybe",
        "signage or label",
        "a word",
        "package lettering",
        "hard (over artwork)",
        "the open refrigerator: many printed food packages, individually illegible",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_I25000\.BIN__",
        "maybe",
        "signage or label",
        "a word",
        "print",
        "hard (over artwork)",
        "an attic of stacked books, papers and posters; lettering suggested, not resolved",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_I31000\.BIN__",
        "maybe",
        "signage or label",
        "a word",
        "print",
        "hard (over artwork)",
        "a house front with a post box and a door plate",
    ),
    # --- credits, result badges, more book covers ----------------------------------------
    (
        r"^_DATA_OTI00\.BIN__0261f4$",
        "yes",
        "credits",
        "a line",
        "plain type",
        "easy (transparent)",
        "the production / copyright line naming the publisher, 276x33 4bpp; one copy in each of "
        "OTI00.BIN … OTI04.BIN, one per opening or ending cut",
    ),
    (
        r"^_DATA_MITIM\.BIN__000000$",
        "yes",
        "title/menu/UI art",
        "a word",
        "stylised badge",
        "easy (transparent)",
        "insect-catch result badges: a 'rare' starburst, 'BIG!', size crowns, male/female marks",
    ),
    (
        r"^_DATA_(Z_N0[23]|MZ_A01)\.BIN__",
        "yes",
        "insect/fish/item book",
        "several lines",
        "stylised cover type",
        "hard (over artwork)",
        "another book-opening frame with the cover legible (diary / insect encyclopedia)",
    ),
    (
        r"^_DATA_(Z_A06|MZ_A08)\.BIN__",
        "no",
        "other",
        "none",
        "n/a",
        "n/a",
        "book-opening frame, blank pages only",
    ),
    (
        r"^_DATA_TBG0[01]\.BIN__00001c$",
        "maybe",
        "title/menu/UI art",
        "a word",
        "unknown",
        "unknown",
        "kite-flying HUD atlas: digits and m / m/s are Latin, but small marks beside them "
        "were not resolved",
    ),
    (
        r"^_DATA_TBG0[01]\.BIN__",
        "no",
        "other",
        "none",
        "n/a",
        "n/a",
        "kite-flying sky and mountain backdrop",
    ),
    (
        r"^_DATA_(MI\d+|MITIM|TA\d+)\.BIN__",
        "no",
        "other",
        "none",
        "n/a",
        "n/a",
        "insect or kite model texture",
    ),
    # --- the rest of the archive --------------------------------------------------------
    (
        r"^_DATA_M_FILES\.BIN_M_\w+\.BIN__",
        "no",
        "other",
        "none",
        "n/a",
        "n/a",
        "map pack artwork: background strip atlas or a 98x79 watercolour minimap, "
        "no lettering seen",
    ),
    # (no rule for H_FILES: not one of its 115 model packs contains a TIM at all.)
    (
        r"^_DATA_MDLTIM\.RTM__",
        "no",
        "other",
        "none",
        "n/a",
        "n/a",
        "shared model texture atlas: faces, insects, clothing",
    ),
    (
        r"^SCPS_100\.88__",
        "no",
        "other",
        "none",
        "n/a",
        "n/a",
        "the executable's only TIM: three 16x16 face sprites",
    ),
]

CATEGORY_ORDER = [
    "picture-diary page",
    "insect/fish/item book",
    "title/menu/UI art",
    "signage or label",
    "calendar/clock",
    "font/glyph sheet",
    "credits",
    "other",
]


def classify(ident: str) -> tuple[str, str, str, str, str, str]:
    for pattern, has, cat, amount, style, diff, note in RULES:
        if re.search(pattern, ident):
            return has, cat, amount, style, diff, note
    return "no", "other", "none", "n/a", "n/a", "no lettering seen on the contact sheet"


def main() -> None:
    lines = DISTINCT.read_text().splitlines()
    head = lines[0].split("\t")
    rows = [dict(zip(head, ln.split("\t"), strict=True)) for ln in lines[1:]]
    counts: dict[tuple[str, str], int] = {}
    with CENSUS.open("w", encoding="utf-8", newline="\n") as f:
        f.write(
            "id\tcopies\twhere\tbpp\tw\th\tcluts\thas_text\tcategory\tamount\tstyle\t"
            "difficulty\tnotes\n"
        )
        for r in rows:
            ident, bpp, w, h, cluts = r["id"], r["bpp"], r["w"], r["h"], r["cluts"]
            copies, where = r["copies"], r["members"]
            has, cat, amount, style, diff, note = classify(ident)
            counts[(cat, has)] = counts.get((cat, has), 0) + 1
            f.write(
                f"{ident}\t{copies}\t{where}\t{bpp}\t{w}\t{h}\t{cluts}\t{has}\t{cat}\t"
                f"{amount}\t{style}\t{diff}\t{note}\n"
            )
    print(f"wrote {CENSUS.relative_to(ROOT)}: {len(rows)} distinct images")
    for cat in CATEGORY_ORDER:
        line = "  ".join(
            f"{has}={counts[(cat, has)]}" for has in ("yes", "maybe", "no") if (cat, has) in counts
        )
        if line:
            print(f"  {cat:24s} {line}")


if __name__ == "__main__":
    main()
