"""Derive research/data/texture-plan.tsv from the census (PLAN GFX-03 audit).

    ./make.sh texture-plan

It reads research/data/texture-census.tsv, keeps every has_text yes/maybe row, and applies
the decision table below -- which is the written record of what was looked at
(research/textures-plan.md).  No census field (member, size, category) is retyped here:
those are copied from the row, and the rule supplies only the decision.

Two refusals keep a census change from silently moving a decision.  Every yes/maybe row
must match **exactly one** rule -- all rules are tried, not just the first, so rule order
carries no meaning and a second rule claiming a row is an error rather than dead text.  And
each rule states how many rows it expects: a row that is re-classified or added into a
broad rule's reach changes that count and is refused, which a "did any rule match nothing"
check cannot see.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CENSUS = ROOT / "research" / "data" / "texture-census.tsv"
OUT = ROOT / "research" / "data" / "texture-plan.tsv"

# (id regex, rows expected, path, text kind, english source, note).
RULES: list[tuple[str, int, str, str, str, str]] = [
    # ---- picture diary: the owner's ruling (research/diary-redraw.md) ----
    (
        r"^_DATA_NIKKI\.BIN_NIKKI_\d+__",
        94,
        "P",
        "diary entry",
        "new",
        "the recipe and every measurement are research/diary-redraw.md: blank the panel, "
        "erase and re-rule, typeset in the game's 12x12 glyphs; the day numeral slot stays "
        "blank because nikki_date_upload composites a tile into it",
    ),
    # ---- encyclopedia spreads ----
    (
        r"^_DATA_MZKAN[01]\.BIN__",
        18,
        "P",
        "insect spread: name + family + wingspan + food, then a body paragraph",
        "new; species name from glossary s4a; every field is pixels (GFX-05: hhon@5328 is "
        "the insect box's own screen)",
        "flat white page right of the photo panel; horizontal header block over a green rule, "
        "vertical body columns below. One layout; MZKAN0 and MZKAN1 are the same 9 spreads "
        "lit for night and day, so each English page is written to both; blank the white "
        "page only",
    ),
    (
        r"^_DATA_TZKAN\.BIN__",
        8,
        "P",
        "kite spread: name + difficulty bracket + how to build it",
        "new; kite name is a glossary term",
        "flat cream page right of the painted kite panel; vertical columns. One layout, 8 pages",
    ),
    # ---- book covers: the 6-frame opening animations, frames 1-3 show the cover ----
    # Z_A and MZ_N are absent on purpose: the disc's only frames in those two families
    # (Z_A06, MZ_A08) are blank pages, and the census gives them no text.
    (
        r"^_DATA_(DOPA|DOPN|MOPA|MOPN|TOPA|TOPN|Z_N|MZ_A)\d+\.BIN__",
        21,
        "R",
        "book cover type (diary / rare-insect encyclopedia / kite book) + author-photographer line",
        "new (3 cover titles + 1 credit line)",
        "stylised cover type over painted artwork, several frames at an angle in perspective; "
        "the same 3 covers must be redrawn consistently across all frames of each animation",
    ),
    # ---- item pictures ----
    (
        r"^_DATA_PK_ITM\.BIN__00006c$",
        1,
        "P",
        "radio-exercise attendance card: title + footer line",
        "new (2 lines)",
        "flat frontal card, blue print on white, 31 numbered boxes are numerals",
    ),
    (
        r"^_DATA_PK_ITM\.BIN__(00442c|00ce8c)$",
        2,
        "N",
        "food packaging",
        "-",
        "a few kana on a wrapper at ~6 px; packaging is packaging (charter)",
    ),
    (
        r"^_DATA_PK_ITM\.BIN__012acc$",
        1,
        "N",
        "embossed book title",
        "-",
        "census maybe RESOLVED: an old book's embossed spine title, unresolvable at any CLUT "
        "and never read by the player; prop art",
    ),
    # ---- the Wolf Girl's letter ----
    (
        r"^_DATA_M_FILES\.BIN_M_I14000\.BIN__",
        1,
        "R",
        "Saori's farewell note: 4 vertical columns incl. the signature",
        "new (~25 chars); not in the script -- scene E2860 has 0 messages",
        "spiral notepad on a log, close-up screen I14 from day 28 (E2860, cond day>27 & "
        "flag[96]>0). Page is near-flat but rotated and dappled with foliage shadow; redraw "
        "the 3-4 ruled lines by hand. S is the fallback if no artist",
    ),
    # ---- the other close-up screens the player deliberately examines ----
    (
        r"^_DATA_M_FILES\.BIN_M_I23000\.BIN__",
        1,
        "R",
        "hunting-association warning board: alarm word, 2 painted lines, association name",
        "new (4 short strings)",
        "close-up screen; board is frontal and near-flat but hand-painted and weathered",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_I18000\.BIN__",
        1,
        "R",
        "hand-lettered keep-out sign",
        "new (1 line)",
        "close-up screen; flat white panda-shaped panel, frontal, marker lettering",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_I19000\.BIN__",
        1,
        "N",
        "model-aeroplane kit box: scale + product name (spec line already Latin)",
        "-",
        "close-up screen; flat frontal box face, printed type. Stays Japanese: the narrator "
        "says what it is (Jay, 2026-09-22)",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_I15000\.BIN__",
        1,
        "N",
        "superhero poster title",
        "-",
        "katakana hero name on a poster in the boy's room; a poster is a poster (charter)",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_I13000\.BIN__",
        1,
        "N",
        "printed sheet pinned beside the calendar",
        "-",
        "the calendar face itself is already Latin (AUGUST / SUN..SAT / numerals); the only "
        "Japanese is an illegible form pinned to its left",
    ),
    # ---- signage painted into backgrounds ----
    (
        r"^_DATA_M_FILES\.BIN_M_C15[01]00\.BIN__",
        2,
        "P",
        "beach notice board about high tides and swimming",
        "new (2 lines)",
        "frontal dark-wood board in the corner of both map variants' background atlas; the "
        "white type is painted out along the grain and the English painted in 2x "
        "(research/texture-recipes.md M_C15)",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_G08200\.BIN__",
        1,
        "N",
        "hanging scroll, four characters of calligraphy",
        "-",
        "the scroll is the art object; calligraphy is calligraphy (charter)",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_H261\d\d\.BIN__",
        4,
        "N",
        "pottery-workshop calligraphy banner",
        "-",
        "decorative proverb banner over the bench; calligraphy is calligraphy (charter)",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_I0600\d\.BIN__",
        5,
        "N",
        "syrup-bottle label",
        "-",
        "two kana on a shaved-ice syrup bottle; packaging is packaging (charter)",
    ),
    (
        r"^_DATA_M_FILES\.BIN_M_(G14000|G14003|H06200|H06202|I25000|I31000|I16200|I21000|I21020)\.BIN__",
        9,
        "N",
        "scenery signage",
        "-",
        "census maybe RESOLVED by re-look: study-room chart, shop signboard, attic papers, "
        "door plate, refrigerator packaging -- all sub-glyph-size scenery. A shop sign is a "
        "shop sign (charter); none is read by the player",
    ),
    # ---- title / menu / UI ----
    (
        r"^_DATA_T_TITLE\.BIN__",
        1,
        "P",
        "title menu: new game / continue / summer memories / settings",
        "new (4 lines)",
        "transparent ground, outlined type with a drop shadow -- clear and re-typeset with an "
        "outline pass. PRESS START BUTTON and the copyright line are already Latin. NOT touched "
        "by TXT-05: no TITLE.OVL walker draws this menu",
    ),
    (
        r"^_DATA_T_CONFIG\.BIN__",
        2,
        "P",
        "settings value plates: voice only / voice+subtitles, mono / stereo, on / off",
        "new (~6 plates)",
        "flat plates on a UI atlas. TXT-05 patches the settings LABELS (exe@8003D9BC.0-.4, "
        "config_draw) but the value panel is texture",
    ),
    (
        r"^_DATA_(SUB\.BIN__002050|M_S01100\.BIN__|M_S02000\.BIN__|MZ00\.BIN__|MZ02\.BIN__|SAMP\.BIN__)",
        8,
        "P",
        "action-button ovals (back / look / net / ...) and UI plates",
        "new (~12 button words)",
        "flat oval buttons on a multi-CLUT atlas; blank the oval, re-typeset. Carry the "
        "per-region CLUT assignment (textures.md caveat). Not touched by TXT-05",
    ),
    (
        r"^_DATA_M_S01000\.BIN__017d24$",
        1,
        "R",
        "'bug swap notebook' cover, marker lettering on a spiral notepad",
        "new (2 lines)",
        "census maybe RESOLVED at CLUT 3: legible hand-lettered marker on a tan notepad in the "
        "insect-cage close-up. Marker style, so not a glyph typeset",
    ),
    (
        r"^_DATA_M_S01001\.BIN__",
        1,
        "N",
        "none",
        "-",
        "census maybe RESOLVED: the only word is Latin 'PLAYTIME'; the row above it is its "
        "~6 px anti-alias/shadow plane, too short to hold a 12x12 glyph",
    ),
    (
        r"^_DATA_(FS_WAL|PK_WAL|TK_WAL)\.BIN__",
        3,
        "P",
        "record-screen field labels (size / average / largest / count) and bait and tackle names",
        "new (~6 labels + the bait/tackle list)",
        "flat pale plates and plain type; renders faint at CLUT 0. Not touched by TXT-05",
    ),
    (
        r"^_DATA_MITIM\.BIN__",
        1,
        "R",
        "insect-catch result badges: a 'rare' starburst, size crowns, male/female marks",
        "new (~4 words); BIG! is already Latin",
        "stylised badge lettering on a transparent 4bpp sheet, 10 CLUTs",
    ),
    (
        r"^_DATA_TZICON\.BIN__",
        1,
        "P",
        "kite-workshop UI: 'make it' speech balloon, confirm, back button",
        "new (3 short strings)",
        "flat transparent buttons",
    ),
    (
        r"^_DATA_T_MEMORY\.BIN__",
        2,
        "P",
        "'summer memories' album heading plate",
        "new (1 line)",
        "flat pale plate with outlined type; the filmstrip thumbnails beside it are "
        "illegible miniatures of the diary/collection pages and stay as they are. The album's "
        "MENU labels are renderer output already patched by TXT-05 (exe@8003DA00)",
    ),
    (
        r"^_DATA_TBG0[01]\.BIN__",
        2,
        "N",
        "none",
        "-",
        "census maybe RESOLVED at CLUT 0: the kite HUD atlas is kite thumbnails plus "
        "'1234567890', m, s, m/s, a compass rose and a wind vane -- all Latin/numeral",
    ),
    (
        r"^_DATA_NIKKI_W\.BIN__005450$",
        1,
        "N",
        "none",
        "-",
        "census maybe RESOLVED at CLUT 2: the 'oval tag with three glyphs' is two pencils "
        "marked H and HB. Pull cord, star, wreath, mushroom, pencils -- no Japanese",
    ),
    (
        r"^_DATA_MZKAN\.BIN__000048$",
        1,
        "R",
        "'back' plaque and two small action plates",
        "new (3 short strings)",
        "census maybe RESOLVED at CLUT 1: a 44x74 sprite set whose 'back' is brush-lettered on "
        "a stone plaque, not plain type",
    ),
    # ---- the two that are not translation work at all ----
    (
        r"^_DATA_ONMEM\.BIN__004aa0$",
        1,
        "N",
        "the glyph sheet itself",
        "-",
        "not a texture to translate: it is the font. Owned by the font/VWF work "
        "(research/font.md, research/vwf-prototype.md), not by GFX-03",
    ),
    (
        r"^_DATA_OTI00\.BIN__0261f4$",
        1,
        "P",
        "publisher production/copyright credit",
        "new (2 lines)",
        "the last card ENDOTI shows, one copy per ending; a still, so P by Jay's ruling "
        "(2026-09-23); cleared to transparent and the English set in the game's glyphs "
        "(research/texture-recipes.md OTI0n)",
    ),
]

HEAD = "id\tcategory\ttext_kind\tpath\tenglish_source\tcopies\twhere\tw\th\tnotes\n"


def build(census: str, rules: list[tuple[str, int, str, str, str, str]] = RULES) -> str:
    """The plan TSV for one census, or SystemExit naming what the rule table missed."""
    lines = census.splitlines()
    ix = {n: i for i, n in enumerate(lines[0].split("\t"))}
    out: list[str] = []
    matched: list[int] = [0] * len(rules)
    for line in lines[1:]:
        f = line.split("\t")
        if f[ix["has_text"]] not in ("yes", "maybe"):
            continue
        ident = f[ix["id"]]
        hits = [ri for ri, rule in enumerate(rules) if re.search(rule[0], ident)]
        if len(hits) != 1:
            claimants = ", ".join(rules[ri][0] for ri in hits) or "none"
            raise SystemExit(f"{ident}: {len(hits)} rules match, want 1 ({claimants})")
        matched[hits[0]] += 1
        rule = rules[hits[0]]
        _, _, path, kind, src, note = rule
        out.append(
            "\t".join(
                [
                    ident,
                    f[ix["category"]],
                    kind,
                    path,
                    src,
                    f[ix["copies"]],
                    f[ix["where"]],
                    f[ix["w"]],
                    f[ix["h"]],
                    note,
                ]
            )
        )
    wrong = [
        f"{rule[0]}: {n} rows matched, {rule[1]} expected"
        for rule, n in zip(rules, matched, strict=True)
        if n != rule[1]
    ]
    if wrong:
        listed = "\n  ".join(wrong)
        raise SystemExit(
            f"{len(wrong)} rule(s) no longer match what they were written for:\n  {listed}"
        )
    return HEAD + "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--census", type=Path, default=CENSUS, help="the census to read")
    ap.add_argument("--out", type=Path, default=OUT, help="the plan to write")
    args = ap.parse_args(argv)
    text = build(args.census.read_text())
    args.out.write_text(text)
    rows = text.splitlines()[1:]
    per_cat: dict[tuple[str, str], int] = {}
    for row in rows:
        f = row.split("\t")
        per_cat[(f[1], f[3])] = per_cat.get((f[1], f[3]), 0) + 1
    print(f"{args.out}  {len(rows)} rows")
    for (cat, path), n in sorted(per_cat.items()):
        print(f"  {cat:24s} {path}  {n}")


if __name__ == "__main__":
    main()
