"""The buttons (`boku.texture_buttons`) against the contributor's own import, and on Beetle PSX.

Texture level: every tracked button's rebuilt box carries exactly its English -- a stone's
ink-dark pixels are the English set bold in the disc's glyphs, a balloon's type is the English
lines -- and nothing of the Japanese; a widened balloon's atlas entry is grown. The expected
pixels are derived from the translation file and the glyph sheet.

On Beetle (`BOKU_EMU_TESTS=1`): an image carrying only the texture edits is driven to the
settings screen, the load screen (a generated card, `./make.sh saves`) and the diary desk, and
every opaque texel of each button's box must show its rebuilt colour exactly. The stock image
fails it: the Japanese is on screen where the English is expected. Where each box lands was
measured by matching its texels against a screenshot (`research/texture-recipes.md` §
"Buttons").
"""

from __future__ import annotations

import dataclasses
import os
import struct
import subprocess
import sys

import pytest

from boku import REPO_ROOT
from boku import texture_buttons as tb
from boku import texture_paint as paint
from boku.png import read as read_png
from boku.texture_text import TextureTextError, ink_of, lines_of, read_entries
from boku.textures import Texture
from boku.tim import luminance, parse_exact
from boku.typeset import FONT_SHEET_ID, GameFace, face_named

ENTRIES = {e.id.removeprefix(tb.FAMILY): e for e in read_entries().values()
           if e.family == tb.FAMILY}  # fmt: skip


def rebuilt(inv, patched: bytes, source) -> paint.Canvas:
    """The texture of `source` (a button, a record: anything with `.texture` and `.drawn_4bpp`)
    as the build left it (its `stock` view is the rebuilt pixels)."""
    stock = inv.get(source.texture)
    tim = parse_exact(patched, stock.occurrences[0].file_offset)
    return paint.Canvas(Texture(stock.id, "0" * 40, tim, ()), drawn_4bpp=source.drawn_4bpp)


def box_of(button: tb.Button) -> paint.Box:
    return button.placed


@pytest.fixture(scope="module")
def game(texture_inventory) -> GameFace:
    return GameFace.from_sheet(texture_inventory.get(FONT_SHEET_ID).tim)


def test_every_measured_button_has_its_english_tracked():
    assert set(ENTRIES) == set(tb.BUTTONS)


FACE = (6, 0, 34, 15)
"""Where the Japanese could be on a stone, from its top-left corner: the face above the lip,
right of the wing's shading (measured on `TZICON`'s stone, atlas rows 72-86; the glyphs'
bottoms reach row 86, where they meet the lip)."""


STANDARD = [k for k, b in tb.BUTTONS.items()
            if b.kind == "stone" and b.box[2:] == tb.STONE_TEXT[2:]]  # fmt: skip
"""The stones of the one drawing every "Back" but the cage's shares (`tb.STONE_TEXT`)."""


@pytest.mark.parametrize("key", sorted(STANDARD))
def test_a_stone_carries_its_english_bold_and_no_japanese(
    key, texture_inventory, texture_patched, game
):  # fmt: skip
    button = tb.BUTTONS[key]
    canvas = rebuilt(texture_inventory, texture_patched, button)
    palette = canvas.palette(button.clut, button.chunk)
    stock = paint.Canvas(texture_inventory.get(button.texture), drawn_4bpp=button.drawn_4bpp)
    dx, dy, _, _ = tb.STONE_TEXT
    fx, fy, fw, fh = FACE
    around = (button.box[0] - dx + fx, button.box[1] - dy + fy, fw, fh)
    box = paint.points(around)
    dark = {p for p in box if luminance(palette[canvas.at(p)]) < tb.INK_DARK}
    outline = set(box) - tb.inside_stone(stock, button, around)
    english = paint.normalised(paint.bold(ink_of(game, ENTRIES[key])))
    shifts = [(x, y) for x, y in paint.points(around)]
    placed = [
        moved for dx, dy in shifts
        if (moved := {(x + dx, y + dy) for x, y in english}) <= dark
    ]  # fmt: skip
    assert len(placed) == 1, "the English, bold in the disc's glyphs, is not in the box once"
    left = {p for p in dark - placed[0] if not (p in outline and canvas.at(p) == stock.at(p))}
    assert left == set(), (
        f"dark pixels that are neither the English nor the stone's outline: {left}"
    )


@pytest.mark.parametrize("key", sorted(k for k, b in tb.BUTTONS.items() if b.kind == "label"))
def test_a_card_label_carries_its_english_and_no_japanese(
    key, texture_inventory, texture_patched, game
):  # fmt: skip
    """The attendance card: the only printed (saturated) pixels in the label's box are the
    English lines in their face, once."""
    button = tb.BUTTONS[key]
    canvas = rebuilt(texture_inventory, texture_patched, button)
    palette = canvas.palette(button.clut, button.chunk)
    x0, y0, w, h = button.box
    near = [(x, y) for x, y in paint.points((x0 - 2, y0 - 2, w + 4, h + 4))
            if 0 <= x < canvas.width and 0 <= y < canvas.height]  # fmt: skip
    # the tinted fringe of the hole punched in the card's corner stays as it was
    hole = paint.grown({p for p in near if not palette[canvas.at(p)][3]}, 2, 2, 2, 2)
    printed = {
        p for p in paint.points(button.box)
        if tb.saturation(palette[canvas.at(p)]) > tb.INK_SATURATION and p not in hole
    }  # fmt: skip
    block = tb.lines_block(face_named(button.face, game), lines_of(ENTRIES[key]), ENTRIES[key])
    placed = [
        moved for dx, dy in paint.points(button.box)
        if (moved := {(x + dx, y + dy) for x, y in block}) <= printed
    ]  # fmt: skip
    assert len(placed) == 1, "the English lines, in their face, are not on the card once"
    assert printed - placed[0] == set(), (
        f"printed besides the English: {sorted(printed - placed[0])}"
    )


@pytest.mark.parametrize(
    "key", sorted(k for k, b in tb.BUTTONS.items() if b.kind in ("plank", "plate"))
)
def test_a_board_carries_its_english_and_no_japanese(
    key, archive, texture_inventory, texture_patched, game
):  # fmt: skip
    """The Close board (bold, its punched-through Japanese transparent) and the trade plate:
    every dark or transparent pixel of the room is the English, once; a widened one's stored
    sizes follow its art."""
    button = tb.BUTTONS[key]
    canvas = rebuilt(texture_inventory, texture_patched, button)
    room = tb.text_area(button, box_of(button)) if button.kind == "plate" else button.box
    palette = canvas.palette(button.clut, button.chunk)
    colours = {p: palette[canvas.at(p)] for p in paint.points(room)}
    dark = {p for p, c in colours.items() if not c[3] or luminance(c) < tb.INK_DARK}
    ink = ink_of(game, ENTRIES[key])
    english = paint.normalised(paint.bold(ink) if button.kind == "plank" else ink)
    assert paint.normalised(dark) == english
    if button.widen:
        assert_sizes_follow(archive, texture_inventory, texture_patched, button)


STROKE = 8
"""Dark pixels in one group that make a stroke of type, not a speck of the tail's shading
(the largest measured is 4)."""


@pytest.mark.parametrize("key", sorted(k for k, b in tb.BUTTONS.items() if b.kind == "balloon"))
def test_a_balloon_carries_its_english_lines_and_no_japanese(
    key, archive, texture_inventory, texture_patched, game
):  # fmt: skip
    button = tb.BUTTONS[key]
    canvas = rebuilt(texture_inventory, texture_patched, button)
    x0, y0, w, h = box_of(button)
    palette = canvas.palette(button.clut, button.chunk)
    pale = [p for p in paint.points((x0, y0, w, h)) if luminance(palette[canvas.at(p)]) > 200]
    paper = paint.most_used(canvas.stock, canvas.width, pale)
    interior = set()
    for y in range(y0, y0 + h):
        xs = [x for x in range(x0, x0 + w) if canvas.at((x, y)) == paper]
        if xs:
            interior |= {(x, y) for x in range(min(xs), max(xs) + 1)}
    face = face_named(button.face, game)
    expected = tb.lines_block(face, lines_of(ENTRIES[key]), ENTRIES[key])
    ink = {p for p in interior if canvas.at(p) != paper}
    placed = [
        moved for dx, dy in paint.points((x0, y0, w, h))
        if (moved := {(x + dx, y + dy) for x, y in expected}) <= ink
    ]  # fmt: skip
    assert len(placed) == 1, "the English lines, in their face, are not in the balloon once"
    dark = {p for p in ink - placed[0] if luminance(palette[canvas.at(p)]) < tb.SOFT}
    left = [g for g in paint.groups(dark) if len(g) >= STROKE]
    assert left == [], f"marks of type left beside the English: {[sorted(g)[:3] for g in left]}"
    if button.widen:
        assert_sizes_follow(archive, texture_inventory, texture_patched, button)


SMALL = sorted(k for k, b in tb.BUTTONS.items() if b.face != "game")


@pytest.mark.parametrize("key", SMALL)
def test_a_button_is_set_small_only_where_the_games_glyphs_do_not_fit(
    key, archive, texture_inventory, game, monkeypatch
):  # fmt: skip
    """Jay, 2026-09-24: mixing faces in one place looks bad -- the game's glyphs wherever they
    fit. So a button in Bean or Sprout is one the recipe refuses for size in the game's glyphs."""
    monkeypatch.setitem(tb.BUTTONS, key, dataclasses.replace(tb.BUTTONS[key], face="game"))
    with pytest.raises(TextureTextError, match="nothing is cut to fit"):
        tb.buttons(archive, texture_inventory, game, [ENTRIES[key]])


def assert_sizes_follow(archive, inv, patched: bytes, button: tb.Button) -> None:
    """Every stored size of a widened sprite spans its new art: width grown by `extra`, and an
    atlas entry's position moved with the art."""
    x, y, _, _ = box_of(button)
    moved = (x - button.box[0], y - button.box[1])
    for size in button.widen.sizes:
        if isinstance(size, tb.AtlasEntry):
            first = inv.get(button.texture).occurrences[0].file_offset
            x_words, v, w_words, *_ = struct.unpack_from("<6H", patched, first + size.at)
            per = size.per_word
            assert (x_words * per, v, w_words * per) == (
                size.entry[0] * per + moved[0], size.entry[1] + moved[1],
                size.entry[2] * per + button.widen.extra,
            )  # fmt: skip
        else:
            at = archive.overlay_offset(size.overlay, size.ram + 8)
            assert struct.unpack_from("<H", patched, at)[0] == size.width + button.widen.extra


BOOT = ["--press-file", str(REPO_ROOT / "tools/libretro/boot-to-dialogue.press")]
FREE = 24000
"""A new game, left alone after its first dialogue, is free to roam by this frame; the desk's
atlas is loaded at boot (`SUB.BIN` is resident), so the desk is only seen in English from a
boot of the English image, not from a state saved on another."""


def mode(n: int, arena: str) -> list[str]:
    """`mode_set(n)` by hand after the first dialogue (`test_real_texture_text_beetle`)."""
    pokes = ["0x800237E5=05", f"0x800237E0={n:02x}", f"0x800237E4={n:02x}",
             "0x80024728=01000000", f"0x800258E0={arena}"]  # fmt: skip
    return [*BOOT, *(a for poke in pokes for a in ("--poke", f"6500:{poke}"))]


SCREENS = {
    # screen: (presses and pokes, needs a card, {shot frame: [(button, texture origin, skip)]})
    "settings": (
        ["--press", "3300:START", "--press", "3700:DOWN", "--press", "3760:DOWN",
         "--press", "3820:DOWN", "--press", "3900:CIRCLE"],
        False, {4250: [("T_CONFIG.back", (176, 150), None)]},
    ),
    "load": (
        ["--press", "3300:START", "--press", "3610:DOWN", "--press", "3680:CIRCLE"],
        True, {4160: [("M_S01001.back", (8, 0), None)]},
    ),
    "diary": (
        mode(0x0B, "f4791180"), False,
        {7000: [("NIKKI_W.back", (256, 100), None), ("NIKKI_W.good_night", (40, -48), None)]},
    ),
    "desk": (
        [*BOOT, "--press", f"{FREE + 30}:TRIANGLE", "--press", f"{FREE + 320}:RIGHT"], False,
        {FREE + 300: [("SUB.belongings", (-664, -56), None)],
         FREE + 520: [("SUB.tackle", (-260, -82), (102, 136, 6, 10))]},
    ),
    "bag": (
        [*BOOT, "--press", f"{FREE + 30}:TRIANGLE", "--press", f"{FREE + 330}:CIRCLE"], False,
        {FREE + 790: [("PK_WAL.belongings", (16, -180), None),
                      ("PK_WAL.back", (176, 110), None),
                      ("PK_ITM.title", (176, 26), "drawn"), ("PK_ITM.footer", (176, 26), "drawn")]},
    ),
    "kite_record": (
        [*BOOT, "--poke", f"{FREE}:0x80047EC0=0101", "--press", f"{FREE + 30}:TRIANGLE",
         "--press", f"{FREE + 330}:UP", "--press", f"{FREE + 460}:CIRCLE"], False,
        {FREE + 1150: [("TK_WAL.kite", (16, -180), None),
                       ("TK_WAL.back", (204, -10), (276, 193, 3, 1))]},
    ),
    "kite_book": (
        [*mode(0x0C, "f4791180"), "--poke", "7010:0x800459DC=08000000"], False,
        {7200: [("TZICON.make_this_kite", (16, 160), None), ("TZICON.back", (256, 130), None)]},
    ),
    "insect_book": (
        [*mode(0x0D, "f4791180")], False, {7290: [("MZKAN.back", (256, 202), None)]},
    ),
    "bug_sumo": (
        [*BOOT, "--poke", "5300:0x80036588=41313800", "--poke", "5300:0x80036359=01",
         "--poke", "5300:0x8003635A=b90f", "--poke", "5300:0x80035E61=02",
         "--poke", "5300:0x80035E66=01"], False,
        {7000: [("M_S01100.cage", (-296, -40), None)]},
    ),
    "insect_box": (
        [*mode(0x0A, "f43d1b80"), "--press", "7250:DOWN", "--press", "7700:DOWN",
         "--press", "7820:LEFT", "--press", "7940:LEFT"], False,
        {7200: [("MZ02.cage", (-540, 40), None)],
         7690: [("MZ02.collecting_box", (-520, 8), None), ("SAMP.back", (-80, 177), None)],
         7800: [("MZ02.remove_specimen", (-476, 48), (162, 178, 9, 20))],
         7920: [("MZ02.prev_page", (-568, 168), (71, 186, 8, 21))],
         8040: [("MZ02.next_page", (-592, 8), (46, 187, 7, 11))]},
    ),
    "cage": (
        [*BOOT, "--poke", f"{FREE}:0x80045A10=04ff00000103000000000000",
         "--press", f"{FREE + 30}:TRIANGLE", "--press", f"{FREE + 330}:RIGHT",
         "--press", f"{FREE + 400}:RIGHT", "--press", f"{FREE + 470}:UP",
         "--press", f"{FREE + 560}:CIRCLE", "--press", f"{FREE + 1000}:CIRCLE"], False,
        {FREE + 900: [("MITIM.rare", (193, 20), None)],
         FREE + 1200: [("MITIM.take_out", (192, 112), None),
                       ("MITIM.back", (240, 88), (280, 170, 16, 26))]},
    ),
}  # fmt: skip
"""Measured on the English image by matching each box's texels near where the recon put it
(`research/texture-recipes.md` § "Buttons"). A texture origin is where the texture's (0, 0)
lands on screen; `skip` is a screen rectangle the hand cursor is drawn over, or "drawn" for
a picture the game draws dithered (`check_drawn`). The diary's and
the kite book's balloons are idle hints; the kite record needs kite 0 owned (the poke);
bug sumo and the insect box are forced by the recon's pokes. The cage: a rare bug (type 4,
`0x80045B04`'s list) poked into cage slot 0, the desk's cage opened, ○ on the bug for its two
buttons; the rare starburst turns through its three frames, so the shot is checked against
each (`tb.frames_of`), and the hand cursor sits on the stone. Not compared, though seen: the
bug-sumo desk's stone, drawn through a CLUT that is not in its TIM."""
BASE = REPO_ROOT / "work" / "saves" / "newgame.ram"


@pytest.mark.parametrize("screen", sorted(SCREENS))
def test_the_buttons_on_beetle_are_the_typeset_english(
    screen, texture_image, disc_dir, texture_inventory, texture_patched, tmp_path
):  # fmt: skip
    args, card, shots = SCREENS[screen]
    command = [
        sys.executable, str(REPO_ROOT / "tools/libretro/run_core.py"), str(texture_image),
        "--core", os.environ["BOKU_LIBRETRO_CORE"], "--system", os.environ["BOKU_LIBRETRO_SYSTEM"],
        "--work", str(tmp_path), "--frames", str(max(shots) + 10), *args,
    ]  # fmt: skip
    for frame in shots:
        command += ["--shot", f"{frame}:{screen}-{frame}"]
    if card:
        if not BASE.is_file():
            pytest.skip(f"no {BASE}: `./make.sh saves` dumps it")
        mcd = tmp_path / "day05.mcd"
        subprocess.run(
            [sys.executable, "-m", "boku", "save", "--base", str(BASE), "--day", "5",
             "--out", str(mcd), "--disc", str(disc_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True,
        )  # fmt: skip
        command += ["--memcard", str(mcd)]
    subprocess.run(command, check=True, capture_output=True, timeout=600, cwd=REPO_ROOT)
    for frame, buttons in shots.items():
        shot = read_png((tmp_path / f"{screen}-{frame}.png").read_bytes())
        for key, origin, skip in buttons:
            if skip == "drawn":
                check_drawn(shot, texture_inventory, texture_patched, key, origin)
            elif tb.BUTTONS[key].frames:
                check_a_frame(shot, texture_inventory, texture_patched, key, origin)
            else:
                check_on_screen(shot, texture_inventory, texture_patched, key, origin, skip)


DITHER = 8
"""How far Beetle's dither moves each channel of the attendance card: measured, every texel
of it is its colour exactly or 8 less on all three channels."""


def check_drawn(shot, inv, patched: bytes, key: str, origin) -> None:
    """For an item picture the game draws dithered (the attendance card in the bag): every
    opaque texel of the box is on screen within `DITHER` of its rebuilt colour on each channel;
    and enough of them are ones the build changed."""
    button = tb.BUTTONS[key]
    check_texels(shot, inv, patched, button, button.clut, button.chunk,
                 paint.points(button.placed), origin, key, dither=DITHER)  # fmt: skip


def check_on_screen(shot, inv, patched: bytes, key: str, origin, skip) -> None:
    """Every opaque texel of the button's box, as rebuilt, is on screen exactly, but those
    under `skip`; and enough of them are ones the build changed."""
    button = tb.BUTTONS[key]
    check_texels(shot, inv, patched, button, button.clut, button.chunk,
                 paint.points(box_of(button)), origin, key, skip=skip)  # fmt: skip


FRAME_CHANGED = 30
"""A turning badge's frame is small: this many of its texels changed is enough to know the
English is there."""


def check_a_frame(shot, inv, patched: bytes, key: str, origin) -> None:
    """A button whose sprite turns through frames (`tb.Button.frames`): the frame on screen,
    whichever it is, passes `check_on_screen`'s test. `origin` is where the first frame's
    texture origin lands; each frame is drawn at the same screen place."""
    first = tb.BUTTONS[key]
    failures = []
    for button in tb.frames_of(first):
        at = (origin[0] - button.box[0] + first.box[0], origin[1] - button.box[1] + first.box[1])
        try:
            check_texels(shot, inv, patched, button, button.clut, button.chunk,
                         paint.points(button.box), at, key, at_least=FRAME_CHANGED)  # fmt: skip
            return
        except AssertionError as error:
            failures.append(str(error))
    raise AssertionError(f"{key}: no frame is on screen as rebuilt: {failures}")


def check_texels(shot, inv, patched: bytes, source, clut: int, chunk: int, points, origin,
                 what: str, *, skip=None, dither: int = 0, at_least: int = 60) -> None:  # fmt: skip
    """Every opaque texel at `points` of `source`'s texture (anything with `.texture` and
    `.drawn_4bpp`), as rebuilt, is on screen with `origin` at its (0, 0) -- at the colour Beetle
    shows it, or up to `dither` darker on each channel -- but those under screen box `skip`;
    and more than `at_least` of them are ones the build changed."""
    ox, oy = origin
    canvas = rebuilt(inv, patched, source)
    stock = paint.Canvas(inv.get(source.texture), drawn_4bpp=source.drawn_4bpp)
    palette = canvas.palette(clut, chunk)
    compared, changed, wrong = 0, 0, []
    for x, y in points:
        colour = palette[canvas.at((x, y))]
        sx, sy = ox + x, oy + y
        hidden = skip and skip[0] <= sx < skip[0] + skip[2] and skip[1] <= sy < skip[1] + skip[3]
        if not colour[3] or hidden:
            continue
        at = (sy * shot.width + sx) * 4
        seen = tuple(shot.rgba[at : at + 3])
        compared += 1
        changed += canvas.at((x, y)) != stock.at((x, y))
        want = [c >> 3 << 3 for c in colour[:3]]
        if not all(0 <= w - s <= dither for s, w in zip(seen, want, strict=True)):
            wrong.append((x, y, seen))
    assert changed > at_least, f"{what}: the build changed too few texels where the check looked"
    assert wrong == [], f"{what}: {len(wrong)} of {compared} texels differ, first {wrong[:5]}"


MITIM = "_DATA_MITIM.BIN__000000"
CAGE = {"MITIM.take_out": (2, "dark"), "MITIM.back": (8, "dark"), "MITIM.rare": (3, "red")}
"""The cage's buttons and badge on the `MITIM` sheet: which record of its sprite table
`KAGO_UV.BIN` each is drawn by, and how its type is told from the sprite."""


def test_every_stone_and_badge_is_checked_at_the_texture():
    cage = {k for k, b in tb.BUTTONS.items() if b.texture == MITIM}
    assert set(CAGE) == cage
    assert set(STANDARD) | cage == {
        k for k, b in tb.BUTTONS.items() if b.kind in ("stone", "badge")
    }


@pytest.fixture(scope="module")
def cage_sprites(archive) -> dict[int, paint.Box]:
    """`KAGO_UV.BIN`'s records: `u32 n`, then n of `{u16 x_words, y, w_words, h, mode, clut}`,
    x and w in 4bpp VRAM words from `MITIM`'s own place."""
    member = archive.member("KAGO_UV.BIN")
    data = archive.boku[member.offset : member.offset + member.size]
    (n,) = struct.unpack_from("<I", data)
    out = {}
    for i in range(n):
        x, y, w, h, _, _ = struct.unpack_from("<6H", data, 4 + 12 * i)
        out[i] = (x * 4, y, w * 4, h)
    return out


def cage_type(colour, how: str) -> bool:
    """The type's colours, read wider than the recipe reads them: red for the badge (its
    yellows' red and green are within 20), dark for the stone and the leaf."""
    if not colour[3]:
        return False
    if how == "red":
        return colour[0] - colour[1] > 40 or luminance(colour) < 60
    return luminance(colour) < 90


@pytest.mark.parametrize("which", ["rebuilt", "stock"])
@pytest.mark.parametrize("key", sorted(CAGE))
def test_a_cage_button_carries_its_english_and_no_japanese(
    key, which, texture_inventory, texture_patched, game, cage_sprites
):  # fmt: skip
    """In every frame of the sprite the English -- bold on the stone and the leaf, in the
    badge's red on the starburst -- is inked once; no other type-coloured pixel is left where
    the Japanese was (the button's box; a pixel below it the stone's lip has dark flecks of its
    own) but the sprite's outline (within `tb.EDGE` of transparency); and no pixel changed that
    is neither the English nor within a pixel of the Japanese (the lip, the veins and the
    burst's notches stay). Type is read wider than the recipe reads it (`cage_type`), so a
    faint tail the recipe missed is still found: the leaf's す left one, which is why the leaf
    has its own `ink_dark`."""
    record, how = CAGE[key]
    button = tb.BUTTONS[key]
    stock = paint.Canvas(texture_inventory.get(MITIM))
    canvas = stock if which == "stock" else rebuilt(texture_inventory, texture_patched, button)
    text = tb.lines_block(face_named(button.face, game), lines_of(ENTRIES[key]), ENTRIES[key])
    english = paint.normalised(paint.bold(text) if button.kind == "stone" else text)
    failing = set()
    problems = []
    for frame in tb.frames_of(button):
        dy = frame.box[1] - button.box[1]
        x, y, w, h = cage_sprites[record]
        sprite = (x, y + dy, w, h)
        palette = canvas.palette(frame.clut)
        typed = {p for p in paint.points(sprite) if cage_type(palette[canvas.at(p)], how)}
        was = {p for p in paint.points(frame.box) if cage_type(palette[stock.at(p)], how)}
        japanese = set(paint.points(frame.box))
        outline = set(paint.points(sprite)) - tb.inside_stone(stock, frame, sprite)
        placed = [moved for ox, oy in paint.points(sprite)
                  if (moved := {(x + ox, y + oy) for x, y in english}) <= typed]  # fmt: skip
        if len(placed) != 1:
            problems.append(f"frame at y {sprite[1]}: the English is inked {len(placed)} times")
            failing.add(frame.box)
            continue
        if how == "red" and not all(
            palette[canvas.at(p)][0] - palette[canvas.at(p)][1] > tb.BADGE_RED for p in placed[0]
        ):
            problems.append(f"frame at y {sprite[1]}: the English is not in the badge's red")
            failing.add(frame.box)
        kept = {p for p in typed if canvas.at(p) == stock.at(p)}
        left = (typed - kept | kept & japanese - outline) - placed[0]
        changed = {p for p in paint.points(sprite) if canvas.at(p) != stock.at(p)}
        damaged = changed - placed[0] - paint.grown(was, 1, 1, 1, 1)
        for what, pixels in (("other type pixel(s)", left), ("pixel(s) of the art changed",
                                                               damaged)):  # fmt: skip
            if pixels:
                problems.append(f"frame at y {sprite[1]}: {len(pixels)} {what}, first "
                                f"{sorted(pixels)[:3]}")  # fmt: skip
                failing.add(frame.box)
    if which == "stock":
        assert len(failing) == len(tb.frames_of(button)), problems
    else:
        assert problems == []
