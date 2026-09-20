"""`boku.textures` without a disc: enumeration, propagation and every refusal.

The synthetic archive here is `tests/synth_archive.py`'s, and the TIMs inside it are
`tests/synth_tim.py`'s — both built from the format rather than by the code under test.
The real corpus is in `tests/test_real_textures.py`, which is where the identity gates
live; what is here is the behaviour 2,607 well-formed images cannot show.
"""

from __future__ import annotations

import json

import pytest

from boku import png
from boku.archive import Archive
from boku.cli import build_parser
from boku.reinsert import ByteEdit
from boku.textures import (
    TextureError,
    export,
    import_edits,
    inventory,
    main_export,
    main_import,
    text_bearing_ids,
    texture_id,
)
from tests import synth_archive as synth_arc
from tests import synth_tim as synth

SECTOR = synth_arc.SECTOR


def little_tim(seed: int = 0, *, width: int = 8, height: int = 4, colours: int = 16) -> bytes:
    """A 4bpp TIM whose pixels depend on `seed`, so two of them are distinct images."""
    indices = [(x + y + seed) % colours for y in range(height) for x in range(width)]
    return synth.tim(
        0,
        synth.pixel_block(width // 4, height, synth.image_4bpp(width, height, indices)),
        clut=synth.clut_block(colours, 1, synth.ramp(colours), x=320, y=500),
    )


def wide_tim(seed: int = 0, *, width: int = 6, height: int = 3) -> bytes:
    """An 8bpp TIM, so a test can tell a whole-byte edit from a nibble one."""
    indices = [(x * 5 + y + seed) % 256 for y in range(height) for x in range(width)]
    return synth.tim(
        1,
        synth.pixel_block(width // 2, height, bytes(indices)),
        clut=synth.clut_block(256, 1, synth.ramp(256)),
    )


def build_disc(tmp_path, members, exe_extra=b""):
    """Write a synthetic import to `tmp_path` and open it as an `Archive`."""
    blob, entries = synth_arc.archive_of(members)
    builder = synth_arc.ExeBuilder()
    builder.directory(entries)
    if exe_extra:
        builder.put(0x80020000, exe_extra)
    files = tmp_path / "files"
    files.mkdir(parents=True)
    (files / "SCPS_100.88").write_bytes(builder.build())
    (files / "BOKU.BIN").write_bytes(blob)
    return Archive(tmp_path)


def three_copies(tmp_path, body=None):
    """One image stored in three members plus a second image, the way the disc does it."""
    body = body if body is not None else little_tim(1)
    padding = bytes(16)
    return build_disc(
        tmp_path,
        [
            ("\\_DATA\\A.BIN", padding + body + padding),
            ("\\_DATA\\B.BIN", body + little_tim(2)),
            ("\\_DATA\\C.BIN", bytes(64) + body),
        ],
    )


# --- enumeration ---------------------------------------------------------------------------


def test_inventory_groups_identical_images_and_names_them_after_the_first(tmp_path):
    archive = three_copies(tmp_path)
    inv = inventory(archive)
    assert [t.id for t in inv.textures] == [
        "_DATA_A.BIN__000010",
        "_DATA_B.BIN__000050",
    ]
    shared = inv.get("_DATA_A.BIN__000010")
    assert shared.copies == 3
    assert [(o.member, o.offset) for o in shared.occurrences] == [
        ("\\_DATA\\A.BIN", 0x10),
        ("\\_DATA\\B.BIN", 0),
        ("\\_DATA\\C.BIN", 0x40),
    ]
    assert inv.occurrences == 4


def test_an_occurrence_points_at_the_bytes_it_says_it_does(tmp_path):
    archive = three_copies(tmp_path)
    texture = inventory(archive).get("_DATA_A.BIN__000010")
    raw = texture.tim.serialise()
    for place in texture.occurrences:
        assert archive.boku[place.file_offset : place.file_offset + place.length] == raw
        assert place.file == "BOKU.BIN"


def test_a_tim_in_the_executable_is_found_and_addressed_to_its_own_file(tmp_path):
    archive = build_disc(tmp_path, [("\\_DATA\\A.BIN", bytes(SECTOR))], exe_extra=wide_tim())
    texture = inventory(archive).textures[0]
    assert texture.occurrences[0].file == "SCPS_100.88"
    assert texture.occurrences[0].member == "\\SCPS_100.88"
    off = texture.occurrences[0].file_offset
    assert archive.exe[off : off + texture.occurrences[0].length] == texture.tim.serialise()


def test_the_scan_does_not_manufacture_a_tim_inside_a_tim(tmp_path):
    """A whole second TIM sitting in an accepted image's pixels is pixels, not a texture.

    The pixel bytes here *are* a valid 8x1 4bpp TIM, 4-aligned, so a scan that resumed
    anywhere inside the outer image would report two textures and patch overlapping byte
    ranges. Nothing weaker than a parseable inner TIM can fail this way — a stray magic
    word on its own is rejected by the header checks whatever the scan does.
    """
    inner = synth.tim(
        0,
        synth.pixel_block(2, 1, synth.image_4bpp(8, 1, [1, 2, 3, 4, 5, 6, 7, 8])),
        clut=synth.clut_block(16, 1, synth.ramp(16)),
    )
    assert len(inner) % 2 == 0
    body = synth.tim(
        1,
        synth.pixel_block(len(inner) // 2, 1, inner),
        clut=synth.clut_block(256, 1, synth.ramp(256)),
    )
    assert body.index(inner) % 4 == 0
    archive = build_disc(tmp_path, [("\\_DATA\\A.BIN", body)])
    found = inventory(archive).textures
    assert [t.id for t in found] == ["_DATA_A.BIN__000000"]
    assert found[0].tim.serialise() == body


def test_texture_id_is_the_census_scheme():
    assert texture_id("\\_DATA\\NIKKI.BIN\\NIKKI_001", 0) == "_DATA_NIKKI.BIN_NIKKI_001__000000"
    assert texture_id("\\_DATA\\T_TITLE.BIN", 0xC804) == "_DATA_T_TITLE.BIN__00c804"


# --- export ---------------------------------------------------------------------------------


def test_export_writes_one_png_per_distinct_image_and_an_index_of_every_occurrence(tmp_path):
    archive = three_copies(tmp_path / "disc")
    out = tmp_path / "out"
    summary = export(archive, out)
    assert (summary.textures, summary.occurrences) == (2, 4)
    assert sorted(p.name for p in out.glob("*.png")) == [
        "_DATA_A.BIN__000010.png",
        "_DATA_B.BIN__000050.png",
    ]
    index = json.loads((out / "index.json").read_text())
    shared = next(t for t in index["textures"] if t["id"] == "_DATA_A.BIN__000010")
    assert shared["copies"] == 3
    assert shared["clut_origin"] == [320, 500]
    assert [(o["member"], o["offset"], o["size"]) for o in shared["occurrences"]] == [
        ("\\_DATA\\A.BIN", 0x10, shared["occurrences"][0]["size"]),
        ("\\_DATA\\B.BIN", 0, shared["occurrences"][0]["size"]),
        ("\\_DATA\\C.BIN", 0x40, shared["occurrences"][0]["size"]),
    ]


def test_an_exported_png_is_indexed_at_the_tims_own_depth(tmp_path):
    archive = three_copies(tmp_path / "disc")
    out = tmp_path / "out"
    export(archive, out)
    page = png.read((out / "_DATA_A.BIN__000010.png").read_bytes())
    assert (page.colour_type, page.bit_depth) == (3, 4)
    assert page.alpha[0] == 0  # CLUT entry 0 is 0x0000, the transparent colour


def test_only_text_keeps_the_census_rows_that_carry_japanese(tmp_path):
    archive = three_copies(tmp_path / "disc")
    census = tmp_path / "census.tsv"
    census.write_text(
        "id\tcopies\thas_text\n_DATA_A.BIN__000010\t3\tyes\n_DATA_B.BIN__000050\t1\tno\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    summary = export(archive, out, only_text=True, census=census)
    assert (summary.textures, summary.skipped) == (1, 1)
    assert [p.name for p in out.glob("*.png")] == ["_DATA_A.BIN__000010.png"]


def test_only_text_keeps_maybe_as_well(tmp_path):
    census = tmp_path / "census.tsv"
    census.write_text(
        "id\thas_text\na\tyes\nb\tmaybe\nc\tno\n",
        encoding="utf-8",
    )
    assert text_bearing_ids(census) == {"a", "b"}


def test_export_refuses_a_directory_that_is_not_a_previous_export(tmp_path):
    archive = three_copies(tmp_path / "disc")
    out = tmp_path / "out"
    out.mkdir()
    (out / "someones-thesis.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(Exception, match="not a previous texture export"):
        export(archive, out)
    assert (out / "someones-thesis.txt").is_file()


# --- propagation -----------------------------------------------------------------------------


def edit_one_pixel(path, index):
    """Rewrite a PNG with pixel 0 set to `index`, keeping the palette exactly."""
    page = png.read(path.read_bytes())
    pixels = bytearray(page.indices)
    pixels[0] = index
    path.write_bytes(
        png.write_indexed(
            page.width,
            page.height,
            bytes(pixels),
            list(page.palette),
            list(page.alpha),
            page.bit_depth,
        )
    )


def test_an_untouched_export_re_imports_to_no_patches_at_all(tmp_path):
    archive = three_copies(tmp_path / "disc")
    out = tmp_path / "out"
    export(archive, out)
    result = import_edits(archive, out)
    assert result.patches == ()
    assert set(result.unchanged) == {"_DATA_A.BIN__000010", "_DATA_B.BIN__000050"}


def test_one_changed_8bpp_pixel_is_one_changed_byte_at_every_occurrence(tmp_path):
    archive = three_copies(tmp_path / "disc", body=wide_tim(1))
    out = tmp_path / "out"
    export(archive, out)
    target = "_DATA_A.BIN__000010"
    edit_one_pixel(out / f"{target}.png", 200)
    result = import_edits(archive, out)
    assert result.changed == (target,)
    assert len(result.patches) == 3
    assert {len(p.new) for p in result.patches} == {1}
    texture = inventory(archive).get(target)
    pixel_byte = texture.tim.length - len(texture.tim.data)
    assert sorted(p.offset for p in result.patches) == sorted(
        o.file_offset + pixel_byte for o in texture.occurrences
    )
    for patch in result.patches:
        assert archive.boku[patch.offset : patch.offset + 1] == patch.old
        assert patch.new == bytes([200])


def test_one_changed_4bpp_pixel_is_one_changed_byte_whose_other_nibble_survives(tmp_path):
    archive = three_copies(tmp_path / "disc")
    out = tmp_path / "out"
    export(archive, out)
    target = "_DATA_A.BIN__000010"
    before = png.read((out / f"{target}.png").read_bytes()).indices
    edit_one_pixel(out / f"{target}.png", 9)
    result = import_edits(archive, out)
    assert len(result.patches) == 3
    patch = result.patches[0]
    assert len(patch.new) == 1
    assert patch.new[0] & 0xF == 9
    assert patch.new[0] >> 4 == before[1]  # the neighbouring pixel is untouched


def test_a_patch_addresses_the_file_and_names_the_texture_and_member(tmp_path):
    """The patches are `reinsert.ByteEdit`s: the build's own type, verified unadapted.

    `tests/test_real_textures.py` feeds them to `build.check_before_writing`; what is
    pinned here is the `reason`, which is all a `verify_edits` failure over 2,607
    occurrences has to say which copy of which image it was about.
    """
    archive = three_copies(tmp_path / "disc", body=wide_tim(1))
    out = tmp_path / "out"
    export(archive, out)
    edit_one_pixel(out / "_DATA_A.BIN__000010.png", 7)
    patches = import_edits(archive, out).patches
    assert {p.file for p in patches} == {"BOKU.BIN"}
    assert all(isinstance(p, ByteEdit) for p in patches)
    assert {p.reason for p in patches} == {
        f"texture _DATA_A.BIN__000010 in {member}"
        for member in ("\\_DATA\\A.BIN", "\\_DATA\\B.BIN", "\\_DATA\\C.BIN")
    }
    assert all(p.end == p.offset + len(p.old) and p.changes for p in patches)


def test_two_separated_edits_are_two_runs_not_one_span(tmp_path):
    archive = three_copies(tmp_path / "disc", body=wide_tim(1))
    out = tmp_path / "out"
    export(archive, out)
    path = out / "_DATA_A.BIN__000010.png"
    page = png.read(path.read_bytes())
    pixels = bytearray(page.indices)
    pixels[0] = 11
    pixels[-1] = 12
    path.write_bytes(
        png.write_indexed(
            page.width,
            page.height,
            bytes(pixels),
            list(page.palette),
            list(page.alpha),
            page.bit_depth,
        )
    )
    patches = import_edits(archive, out).patches
    assert len(patches) == 6  # two runs x three occurrences
    assert {len(p.new) for p in patches} == {1}


def test_an_edit_leaves_the_clut_and_the_header_alone(tmp_path):
    archive = three_copies(tmp_path / "disc", body=wide_tim(1))
    out = tmp_path / "out"
    export(archive, out)
    edit_one_pixel(out / "_DATA_A.BIN__000010.png", 7)
    texture = inventory(archive).get("_DATA_A.BIN__000010")
    header_and_clut = texture.tim.length - len(texture.tim.data)
    for patch in import_edits(archive, out).patches:
        place = next(
            o
            for o in texture.occurrences
            if o.file_offset <= patch.offset < o.file_offset + o.length
        )
        assert patch.offset - place.file_offset >= header_and_clut


# --- refusals ---------------------------------------------------------------------------------


def test_import_refuses_a_png_of_the_wrong_size(tmp_path):
    archive = three_copies(tmp_path / "disc")
    out = tmp_path / "out"
    export(archive, out)
    path = out / "_DATA_A.BIN__000010.png"
    page = png.read(path.read_bytes())
    path.write_bytes(
        png.write_indexed(
            page.width,
            page.height - 1,
            page.indices[: page.width * (page.height - 1)],
            list(page.palette),
            list(page.alpha),
            page.bit_depth,
        )
    )
    with pytest.raises(TextureError, match=r"is 8x4 on the disc and the PNG is 8x3"):
        import_edits(archive, out)


def test_import_refuses_a_colour_that_is_not_in_the_clut(tmp_path):
    archive = three_copies(tmp_path / "disc")
    out = tmp_path / "out"
    export(archive, out)
    path = out / "_DATA_A.BIN__000010.png"
    page = png.read(path.read_bytes())
    palette = list(page.palette)
    palette[3] = (7, 11, 13)  # a colour the CLUT does not hold, so indices cannot be trusted
    path.write_bytes(
        png.write_indexed(
            page.width, page.height, page.indices, palette, list(page.alpha), page.bit_depth
        )
    )
    with pytest.raises(TextureError, match=r"not in CLUT 0.*#070b0dff"):
        import_edits(archive, out)


def test_a_16_colour_image_re_saved_with_a_padded_palette_still_imports(tmp_path):
    """What Aseprite and Photoshop hand back: 8-bit indexed, 256 entries, 16 of them ours.

    The artist edited the file we gave them; the padding is their tool's, not their work.
    Refusing it told them to re-export and edit *that* file — which is the file they were
    already editing — so the edit had nowhere to go.
    """
    archive = three_copies(tmp_path / "disc")  # 4bpp, a 16-colour CLUT
    out = tmp_path / "out"
    export(archive, out)
    path = out / "_DATA_A.BIN__000010.png"
    page = png.read(path.read_bytes())
    assert (page.bit_depth, len(page.palette)) == (4, 16), "the export is not the 4bpp one"
    padded = list(page.palette) + [(i, i, i) for i in range(256 - len(page.palette))]
    alpha = list(page.alpha) + [255] * (256 - len(page.alpha))
    pixels = bytearray(page.indices)
    pixels[0] = 5
    path.write_bytes(png.write_indexed(page.width, page.height, bytes(pixels), padded, alpha, 8))
    result = import_edits(archive, out)
    assert result.changed == ("_DATA_A.BIN__000010",)
    assert len(result.patches) == 3  # one byte at each of the three occurrences
    assert {p.new[0] & 0xF for p in result.patches} == {5}
    assert {p.new[0] >> 4 for p in result.patches} == {page.indices[1]}


def test_a_padded_palette_whose_own_colours_disagree_is_still_matched_by_colour(tmp_path):
    """The prefix has to *be* the CLUT; a padded palette is not trusted on its length."""
    archive = three_copies(tmp_path / "disc")
    out = tmp_path / "out"
    export(archive, out)
    path = out / "_DATA_A.BIN__000010.png"
    page = png.read(path.read_bytes())
    palette = list(page.palette)
    palette[3] = (7, 11, 13)  # not a colour the CLUT holds, so the indices cannot be trusted
    palette += [(i, i, i) for i in range(256 - len(palette))]
    path.write_bytes(png.write_indexed(page.width, page.height, page.indices, palette, None, 8))
    with pytest.raises(TextureError, match=r"not in CLUT 0.*#070b0dff"):
        import_edits(archive, out)


def test_import_refuses_a_png_whose_name_is_not_a_texture_id(tmp_path):
    archive = three_copies(tmp_path / "disc")
    out = tmp_path / "out"
    export(archive, out)
    (out / "_DATA_A.BIN__000010.png").rename(out / "my-edit.png")
    with pytest.raises(TextureError, match="names no texture on this disc"):
        import_edits(archive, out)


def test_import_refuses_something_that_is_not_a_png(tmp_path):
    archive = three_copies(tmp_path / "disc")
    out = tmp_path / "out"
    export(archive, out)
    (out / "_DATA_A.BIN__000010.png").write_bytes(b"not a png at all")
    with pytest.raises(TextureError, match="signature is missing"):
        import_edits(archive, out)


# --- the explicit approximation ----------------------------------------------------------------


def test_nearest_maps_an_off_palette_colour_and_says_what_it_cost(tmp_path):
    archive = three_copies(tmp_path / "disc")
    out = tmp_path / "out"
    export(archive, out)
    path = out / "_DATA_A.BIN__000010.png"
    page = png.read(path.read_bytes())
    rgba = bytearray(page.rgba)
    rgba[0:4] = bytes([200, 210, 220, 255])
    path.write_bytes(png.write_rgba(page.width, page.height, bytes(rgba)))
    with pytest.raises(TextureError, match="not in CLUT 0"):
        import_edits(archive, out)
    result = import_edits(archive, out, nearest=True)
    report = result.quantisation["_DATA_A.BIN__000010"]
    assert report.approximated == 1
    assert report.worst > 0
    assert "approximated" in report.describe()
    assert len(result.patches) == 3


# --- the command line, which reports rather than tracebacks -------------------------------


def test_export_of_an_import_that_is_not_there_is_a_message_not_a_traceback(tmp_path, capsys):
    """A contributor's first run of either verb is the one before `./make.sh import`."""
    assert main_export(tmp_path / "nowhere", tmp_path / "out", False, 0) == 1
    assert "boku textures export:" in capsys.readouterr().out
    assert not (tmp_path / "out").exists()


def test_import_of_a_directory_that_is_not_there_is_a_message_not_a_traceback(tmp_path, capsys):
    archive = three_copies(tmp_path / "disc")
    assert main_import(archive.disc_dir, tmp_path / "nowhere", False) == 1
    out = capsys.readouterr().out
    assert "boku textures import:" in out and "not a directory" in out


def test_import_of_something_that_is_not_a_png_is_a_message_not_a_traceback(tmp_path, capsys):
    archive = three_copies(tmp_path / "disc")
    out_dir = tmp_path / "out"
    export(archive, out_dir)
    (out_dir / "_DATA_A.BIN__000010.png").write_bytes(b"not a png at all")
    assert main_import(archive.disc_dir, out_dir, False) == 1
    assert "signature is missing" in capsys.readouterr().out


def test_a_negative_clut_is_refused_by_the_parser_before_anything_is_read(capsys):
    """`--clut -1` used to reach `Clut.palette` and traceback out of a 824-image export."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["textures", "export", "--clut", "-1"])
    assert "palette" in capsys.readouterr().err
