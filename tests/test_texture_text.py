"""`boku.texture_text` without a disc: the string files, the refusals, and the title recipe.

The atlas here is invented (`tests/synth_tim.py`) in the title atlas's shape: an outlined
line of "type" in each of four 16-row bands within x < 84, a sprite at x >= 128 and more
artwork under the menu. The face is a stand-in whose glyphs are solid blocks, so what a
test asserts about pixels is derived from the face it hands in, not typed out twice. The
real atlas and the real glyphs are `tests/test_real_texture_text.py`'s.
"""

from __future__ import annotations

import struct
from types import SimpleNamespace

import pytest

from boku import texture_paint as paint
from boku import texture_text as tt
from boku.archive import ARCHIVE_NAME, OVERLAY_LOAD_ADDRESS
from boku.textures import Occurrence, Texture
from boku.tim import parse_exact
from boku.typeset import TypesetError
from tests import synth_tim as synth

WIDTH, HEIGHT = 160, 80
TRANSPARENT, OUTLINE, FILL, SPRITE, ART = 0, 1, 14, 5, 7
OVERLAY_OFFSET = 0x4000
ATLAS_OFFSET = 0x100000


class BlockFace:
    """Every character a block on cell rows 2-7 with one column of air after it: `i` one
    column wide, anything else four; `-` has no drawing."""

    @staticmethod
    def wide(ch: str) -> int:
        return 1 if ch == "i" else 4

    def measure(self, text: str) -> int:
        return max(0, sum(self.wide(ch) + 1 for ch in text) - 1)

    def ink(self, text: str) -> set[tuple[int, int]]:
        if "-" in text:
            raise TypesetError(f"no drawing for '-' in {text!r}")
        out, x = set(), 0
        for ch in text:
            if ch != " ":
                out |= {(x + dx, dy) for dx in range(self.wide(ch)) for dy in range(2, 8)}
            x += self.wide(ch) + 1
        return out


def atlas_pixels() -> list[int]:
    px = [TRANSPARENT] * (WIDTH * HEIGHT)
    for band in range(4):
        for y in range(16 * band + 1, 16 * band + 14):
            for x in range(0, 83):
                inner = 16 * band + 2 <= y <= 16 * band + 12 and 1 <= x <= 81
                px[y * WIDTH + x] = FILL if inner and (x // 3) % 2 else OUTLINE
    for y in range(17, 50):
        for x in range(128, 152):
            px[y * WIDTH + x] = SPRITE
    for y in range(64, HEIGHT):
        for x in range(WIDTH):
            px[y * WIDTH + x] = ART
    return px


def make_texture(px: list[int]) -> Texture:
    palette = synth.ramp(256)
    palette[OUTLINE] = 31 | 31 << 5 | 31 << 10  # pale, as the real outline is
    palette[FILL] = 0 | 6 << 5 | 17 << 10  # dark blue, as the real fill is
    raw = synth.tim(
        1,
        synth.pixel_block(WIDTH // 2, HEIGHT, bytes(px)),
        clut=synth.clut_block(256, 1, palette),
    )
    tim = parse_exact(raw)
    place = Occurrence(ARCHIVE_NAME, "\\_DATA\\T_TITLE.BIN", 20, ATLAS_OFFSET, tim.length)
    return Texture(tt.TITLE_ATLAS, "0" * 40, tim, (place,))


class FakeArchive:
    """Just `TITLE.OVL`, stored at `OVERLAY_OFFSET` of `BOKU.BIN`."""

    def overlay_offset(self, short_name, ram):
        assert short_name == tt.TITLE_OVERLAY
        return OVERLAY_OFFSET + ram - OVERLAY_LOAD_ADDRESS


def run_title(texts, px=None):
    texture = make_texture(px or atlas_pixels())
    inv = SimpleNamespace(get=lambda _id: texture)
    archive = FakeArchive()
    entries = [tt.Entry(f"tex@T_TITLE.{i}", text, f"ui.txt:{i}") for i, text in enumerate(texts)]
    return texture, tt.title_menu(archive, inv, BlockFace(), entries)


def applied(texture: Texture, edits) -> list[int]:
    blob = bytearray(texture.tim.serialise())
    for edit in edits:
        at = edit.offset - ATLAS_OFFSET
        if 0 <= at < len(blob):
            assert blob[at : at + len(edit.old)] == edit.old
            blob[at : at + len(edit.new)] = edit.new
    return list(parse_exact(bytes(blob)).indices())


# --- the string files ----------------------------------------------------------------------


def write(tmp_path, text: str, name: str = "ui.txt"):
    (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_rows_are_read_by_id_and_notes_are_skipped(tmp_path):
    entries = tt.read_entries(write(tmp_path, "# a note\n\ntex@T_TITLE.0\tNew Game \n"))
    assert list(entries) == ["tex@T_TITLE.0"]
    assert entries["tex@T_TITLE.0"].text == "New Game"
    assert entries["tex@T_TITLE.0"].where == "ui.txt:3"
    assert entries["tex@T_TITLE.0"].family == "tex@T_TITLE"


def test_an_id_given_twice_is_refused_naming_both_places(tmp_path):
    write(tmp_path, "tex@A.0\tOne\n", "a.txt")
    write(tmp_path, "tex@A.0\tTwo\n", "b.txt")
    with pytest.raises(
        tt.TextureTextError, match=r"b\.txt:1: tex@A\.0 is already given at a\.txt:1"
    ):
        tt.read_entries(tmp_path)


@pytest.mark.parametrize("row", ["tex@A.0 New Game", "tex@A.0\t  ", "\tNew Game"])
def test_a_row_that_is_not_id_tab_english_is_refused(tmp_path, row):
    with pytest.raises(tt.TextureTextError, match=r"ui\.txt:1"):
        tt.read_entries(write(tmp_path, row + "\n"))


def test_a_string_no_recipe_builds_is_refused_rather_than_ignored(tmp_path):
    write(tmp_path, "tex@T_TITEL.0\tNew Game\n")
    with pytest.raises(tt.TextureTextError, match=r"no texture recipe builds tex@T_TITEL"):
        tt.build_edits(SimpleNamespace(), tmp_path, inv=SimpleNamespace())


def test_no_strings_is_no_edits_and_reads_nothing_from_the_import(tmp_path):
    result = tt.build_edits(SimpleNamespace(), write(tmp_path, "# nothing yet\n"))
    assert result.edits == () and result.families == ()


# --- outlined --------------------------------------------------------------------------------


def test_the_outline_rings_the_ink_on_eight_sides_and_stays_in_its_box():
    width = 10
    pixels = bytearray(width * 6)
    tt.outlined(pixels, width, (2, 1, 5, 4), {(0, 0), (2, 1)}, fill=9, outline=3)
    got = {(i % width, i // width): v for i, v in enumerate(pixels) if v}
    # (0,0) sits on the box's corner: its ring is clipped to the box, never written outside.
    assert got[(2, 1)] == 9 and got[(4, 2)] == 9
    assert {p for p, v in got.items() if v == 3} == {
        (3, 1), (2, 2), (3, 2), (4, 1), (5, 1), (5, 2), (5, 3), (4, 3), (3, 3),
    }  # fmt: skip
    assert all(2 <= x < 7 and 1 <= y < 5 for x, y in got)


# --- the title menu ---------------------------------------------------------------------------


TEXTS = ("New Game", "Continue", "Summer Memories", "Settings")


def expected_band(text: str) -> dict[tuple[int, int], int]:
    ink = {(x + 1, y + tt.MENU_INK_TOP) for x, y in BlockFace().ink(text)}
    ring = {(x + dx, y + dy) for x, y in ink for dx in (-1, 0, 1) for dy in (-1, 0, 1)} - ink
    return {**{p: OUTLINE for p in ring}, **{p: FILL for p in ink}}


def test_each_band_holds_exactly_its_english_in_the_atlas_own_fill_and_outline():
    texture, edits = run_title(TEXTS)
    after = applied(texture, edits)
    for band, text in enumerate(TEXTS):
        want = expected_band(text)
        got = {
            (x, y): after[(16 * band + y) * WIDTH + x]
            for y in range(16)
            for x in range(tt.MENU_WIDTH)
            if after[(16 * band + y) * WIDTH + x] != TRANSPARENT
        }
        assert got == want, f"band {band}"


def test_nothing_outside_the_four_bands_and_their_widened_width_changes():
    texture, edits = run_title(TEXTS)
    before, after = atlas_pixels(), applied(texture, edits)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if y < 16 * tt.MENU_LINES and x < tt.MENU_WIDTH:
                continue
            assert after[y * WIDTH + x] == before[y * WIDTH + x], (x, y)


def test_the_sprites_and_the_highlight_are_widened_from_the_retail_width():
    _, edits = run_title(TEXTS)
    overlay = {
        e.offset - OVERLAY_OFFSET + OVERLAY_LOAD_ADDRESS: e
        for e in edits
        if e.offset < ATLAS_OFFSET
    }
    records = {ram - tt.TITLE_RECORD_WIDTH for ram in overlay if ram != tt.TITLE_HIGHLIGHT_WIDTH}
    assert records == set(tt.TITLE_MENU_RECORDS)
    for record in tt.TITLE_MENU_RECORDS:
        edit = overlay[record + tt.TITLE_RECORD_WIDTH]
        assert struct.unpack("<H", edit.old)[0] == tt.RETAIL_MENU_WIDTH
        assert struct.unpack("<H", edit.new)[0] == tt.MENU_WIDTH
    highlight = overlay[tt.TITLE_HIGHLIGHT_WIDTH]
    assert struct.unpack("<I", highlight.new)[0] & 0xFFFF == tt.MENU_WIDTH
    assert struct.unpack("<I", highlight.old)[0] ^ struct.unpack("<I", highlight.new)[0] == (
        tt.RETAIL_MENU_WIDTH ^ tt.MENU_WIDTH
    ), "only the immediate changes"


def test_a_line_one_pixel_too_wide_with_its_outline_is_refused_with_its_numbers():
    face = BlockFace()
    exact, over = "x" * 25 + "i", "x" * 24 + "iiii"
    assert face.measure(exact) + 2 == tt.MENU_WIDTH
    assert face.measure(over) + 2 == tt.MENU_WIDTH + 1
    run_title((exact, *TEXTS[1:]))
    with pytest.raises(tt.TextureTextError, match=r"ui.txt:0: .* needs 129x14 px .* holds 128x16"):
        run_title((over, *TEXTS[1:]))


def test_a_character_the_face_cannot_draw_is_refused_not_skipped():
    with pytest.raises(tt.TextureTextError, match=r"ui.txt:3: no drawing for '-'"):
        run_title((*TEXTS[:3], "Set-tings"))


@pytest.mark.parametrize(
    "ids",
    [(0, 1, 2), (0, 1, 2, 3, 4), (0, 1, 2, "x"), (0, 1, 2, "²")],
    ids=["three", "five", "not-a-number", "superscript-two"],
)
def test_the_menu_takes_all_four_lines_or_none(ids):
    texture = make_texture(atlas_pixels())
    entries = [tt.Entry(f"tex@T_TITLE.{i}", "Go", "ui.txt:1") for i in ids]
    with pytest.raises(tt.TextureTextError, match=r"exactly \.0, \.1, \.2, \.3"):
        tt.title_menu(
            FakeArchive(),
            SimpleNamespace(get=lambda _id: texture),
            BlockFace(),
            entries,
        )


def test_an_atlas_whose_most_used_entry_is_the_darker_one_is_refused():
    """Fill and outline are told apart by pixel count; the palette says which is which.
    Swap the two roles in the pixels and the recipe must refuse, not draw them inverted."""
    swap = {OUTLINE: FILL, FILL: OUTLINE}
    px = [swap.get(v, v) if i < 64 * WIDTH else v for i, v in enumerate(atlas_pixels())]
    with pytest.raises(tt.TextureTextError, match="paler than its fill"):
        run_title(TEXTS, px)


@pytest.mark.parametrize("space", ["\u3000", "\u00a0", "\t"])
def test_whitespace_other_than_a_space_is_refused_not_set_at_zero_width(space):
    from boku.typeset import Face, Glyph

    class Inked(Face):
        """Draws every character that is not whitespace; so only the face's own space
        rule decides what happens to `space`."""

        def glyph(self, ch):
            return None if ch.isspace() else Glyph(1, ((0,),))

    assert Inked().missing(f"New Game{space}Now") == [space]


def test_an_atlas_with_artwork_where_the_widened_lines_go_is_refused():
    px = atlas_pixels()
    px[40 * WIDTH + 100] = ART  # band 2, x 100: inside the widened line, outside the retail one
    with pytest.raises(tt.TextureTextError, match="not the atlas this recipe was measured on"):
        run_title(TEXTS, px)


# --- the image build -------------------------------------------------------------------------


def test_boku_build_textures_hands_the_typeset_edits_to_the_image_build(monkeypatch, tmp_path):
    from boku import build as build_module
    from boku.cli import build_parser
    from boku.reinsert import ByteEdit

    edit = ByteEdit(ARCHIVE_NAME, 0x10, b"\x00", b"\x01", "typeset")
    seen = {}
    monkeypatch.setattr(build_module, "Archive", lambda disc: SimpleNamespace(disc=disc))
    monkeypatch.setattr(
        build_module,
        "build_texture_edits",
        lambda archive, directory: (
            seen.setdefault("dir", directory) and tt.TextureEdits((edit,), ("tex@T_TITLE",))
        ),
    )

    def fake_build(**kwargs):
        seen["patches"] = list(kwargs["binary_patches"])
        raise build_module.BuildRefused("stop here")

    monkeypatch.setattr(build_module, "build", fake_build)
    args = build_parser().parse_args(
        ["build", "--no-renderer-patch", "--textures", str(tmp_path), "--disc", str(tmp_path)]
    )
    assert args.run(args) == 1
    assert seen["dir"] == tmp_path
    assert edit in seen["patches"]


def test_a_texture_the_import_lacks_is_one_sentence_from_boku_build(monkeypatch, tmp_path, capsys):
    from boku import build as build_module
    from boku.cli import build_parser
    from boku.textures import TextureError

    def lacking(archive, directory):
        raise TextureError("no texture _DATA_T_TITLE.BIN__000014 on this disc")

    monkeypatch.setattr(build_module, "Archive", lambda disc: None)
    monkeypatch.setattr(build_module, "build_texture_edits", lacking)
    args = build_parser().parse_args(
        ["build", "--no-renderer-patch", "--textures", str(tmp_path), "--disc", str(tmp_path)]
    )
    assert args.run(args) == 1
    assert "boku build: no texture _DATA_T_TITLE" in capsys.readouterr().out


# --- shared refusals (review 2026-09-22, T_CONFIG unit) -----------------------------------------


def test_a_line_break_in_a_one_line_slot_is_refused_not_drawn_as_slashes():
    with pytest.raises(tt.TextureTextError, match=r"ui.txt:0: tex@T_TITLE.0 is set on one line"):
        run_title(("New // Game", *TEXTS[1:]))


def test_type_missing_where_it_was_measured_is_refused_by_name():
    with pytest.raises(tt.TextureTextError, match="the heading: no type where the recipe"):
        tt.found(set(), "the heading")


def test_japanese_with_nothing_to_paint_it_out_from_is_refused():
    canvas = SimpleNamespace(paint_out=lambda box, mask, avoid: sorted(mask))
    with pytest.raises(tt.TextureTextError, match=r"the chart: 1 pixel"):
        tt.painted_out(canvas, (0, 0, 7, 1), {(3, 0)}, what="the chart")


def plate(rows_of_type: list[int], width: int = 60, height: int = 40):
    """An 8bpp plate: a saturated ground (entry 2) with pale type (entry 1) on the given rows."""
    palette = synth.ramp(256)
    palette[1] = 31 | 31 << 5 | 31 << 10  # white type
    palette[2] = 20 | 2 << 5 | 4 << 10  # dark red ground
    px = [2] * (width * height)
    for y in rows_of_type:
        for x in range(10, 30):
            px[y * width + x] = 1
    raw = synth.tim(
        1, synth.pixel_block(width // 2, height, bytes(px)), clut=synth.clut_block(256, 1, palette)
    )
    tim = parse_exact(raw)
    return paint.Canvas(Texture("plate", "0" * 40, tim, ()))


def test_small_labels_that_would_run_into_each_other_are_refused():
    """Two Japanese lines 4 rows apart: the first English line (9+ rows of ink) would overlap
    the second, so the recipe refuses rather than overprinting."""
    canvas = plate([2, 3, 4, 8, 9, 30, 31])
    one, two, three = (tt.Entry(f"tex@T_CONFIG.{k}", "Hello", f"ui.txt:{n}")
                       for n, k in enumerate(("a", "b", "c")))  # fmt: skip
    with pytest.raises(tt.TextureTextError, match=r"ui.txt:1: .* would run into tex@T_CONFIG.a"):
        tt._small_labels(
            canvas, 0, (0, 0, 60, 40), ([one, two], [three]), GlyphFace(), "the plate",
        )  # fmt: skip


def test_a_small_label_that_would_run_off_the_plate_is_refused():
    canvas = plate([2, 3, 36, 37])
    one, two = (tt.Entry(f"tex@T_CONFIG.{k}", "Hello", f"ui.txt:{n}") for n, k in enumerate("ab"))
    with pytest.raises(tt.TextureTextError, match=r"ui.txt:1: .* would run into its edge"):
        tt._small_labels(
            canvas, 0, (0, 0, 60, 40), ([one], [two]), GlyphFace(), "the plate",
        )  # fmt: skip


class GlyphFace(BlockFace):
    """Blocks nine rows tall, like the game's capitals with a descender."""

    def ink(self, text):
        out, x = set(), 0
        for ch in text:
            out |= {(x + dx, dy) for dx in range(self.wide(ch)) for dy in range(9)}
            x += self.wide(ch) + 1
        return out


def test_a_beach_line_taller_than_its_painted_rows_is_refused_not_stamped_above_them():
    """A line may run off the board to the right, as the Japanese does, but it may not leave
    the rows that were painted out -- above them is wood nobody cleaned."""
    width, height = 490, 90
    px = [2] * (width * height)
    for x0, y0, w, _ in tt.BEACH_LINES:
        for y in range(y0 + 4, y0 + 20):  # a 16-row line of "type", well inside its box
            for x in range(x0 + 2, x0 + w - 2, 3):
                px[y * width + x] = 1
    palette = synth.ramp(256)
    palette[1] = 31 | 31 << 5 | 31 << 10  # white type
    palette[2] = 6 | 3 << 5 | 2 << 10  # dark wood
    raw = synth.tim(
        1, synth.pixel_block(width // 2, height, bytes(px)),
        clut=synth.clut_block(256, tt.BEACH_CLUT + 1, palette * (tt.BEACH_CLUT + 1)),
    )  # fmt: skip
    board = Texture("board", "0" * 40, parse_exact(raw), ())

    class TallFace(BlockFace):
        def ink(self, text):  # 16 rows: doubled, 32 -- taller than a 30-row line box
            return {(x, y) for x in range(4) for y in range(16)}

    entries = [tt.Entry(f"tex@M_C15.{n}", "Go", f"signs.txt:{n}") for n in range(2)]
    with pytest.raises(tt.TextureTextError, match=r"signs.txt:0: 'Go' is 32 px tall"):
        tt.beach_notice(SimpleNamespace(), SimpleNamespace(get=lambda _id: board), TallFace(),
                        entries)  # fmt: skip
