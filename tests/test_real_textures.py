"""The `GFX-01` gates, against a contributor's own import. Skips without one.

Three things are proved here and nowhere else, because only the real corpus has them:

* **decode → encode is byte-identical over every TIM on the disc** — all 2,607 occurrences,
  not the 824 distinct images, because a duplicate that parses differently is a duplicate
  that would be patched wrong;
* **TIM → indexed PNG → TIM is byte-identical** for every distinct image at CLUT 0, and
  for every CLUT of the most multi-palette images;
* **an edit propagates to every copy** — checked on the 98x79 minimap that the census
  counts 287 of.

The fixtures are the disc's own bytes and are never written anywhere (CLAUDE.md § "This
repo is public"); the counts are read back from `research/data/texture-census.tsv`, which
is tracked, rather than typed here.
"""

from __future__ import annotations

import struct

import pytest

from boku import png
from boku.build import check_before_writing
from boku.textures import (
    CENSUS_TSV,
    Inventory,
    export,
    import_edits,
    indices_for,
    inventory,
    patches_for,
    to_png,
)
from boku.tim import indices_from_rgba, parse_exact


@pytest.fixture(scope="module")
def inv(archive):
    return inventory(archive)


@pytest.fixture(scope="module")
def census_rows():
    """The tracked census, as `id -> row`. The expected counts come from here, not from me."""
    lines = CENSUS_TSV.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    return {
        row[0]: dict(zip(header, row, strict=True))
        for row in (line.split("\t") for line in lines[1:])
    }


# --- gate 1: the parse loses nothing ------------------------------------------------------


def test_every_tim_on_the_disc_serialises_back_to_its_own_bytes(archive, inv, census_rows):
    """`GFX-01`'s headline gate, over occurrences rather than distinct images."""
    blobs = {"BOKU.BIN": archive.boku, "SCPS_100.88": archive.exe}
    checked = 0
    for texture in inv.textures:
        for place in texture.occurrences:
            raw = blobs[place.file][place.file_offset : place.file_offset + place.length]
            assert parse_exact(raw).serialise() == raw, f"{texture.id} at {place.member}"
            checked += 1
    assert checked == sum(int(row["copies"]) for row in census_rows.values())
    assert len(inv.textures) == len(census_rows)


def test_the_enumeration_is_the_one_the_census_was_built_from(inv, census_rows):
    """Same ids, same copy counts, same shapes — so `--only-text` joins onto the census."""
    assert {t.id for t in inv.textures} == set(census_rows)
    for texture in inv.textures:
        row = census_rows[texture.id]
        assert texture.copies == int(row["copies"])
        assert (texture.tim.bpp, texture.width, texture.height) == (
            int(row["bpp"]),
            int(row["w"]),
            int(row["h"]),
        )
        assert texture.tim.clut is not None
        assert texture.tim.clut.count == int(row["cluts"])


def test_the_clut_vram_origin_is_carried_for_the_textures_that_have_one(archive, inv):
    """A placed CLUT is read back as the halfwords the file holds, not as 0,0.

    The count of them was a literal retyped from research prose and the census has no
    column to derive it from, so what is pinned instead is the thing that matters and
    that a wrong count would not have caught: the origin of *every* placed CLUT, read
    straight out of the disc's bytes with `struct` rather than through the parser under
    test. A codec that dropped the field would read 0,0 everywhere and fail here.
    """
    blobs = {"BOKU.BIN": archive.boku, "SCPS_100.88": archive.exe}
    placed = 0
    for texture in inv.textures:
        if texture.tim.clut is None or not (texture.tim.clut.x or texture.tim.clut.y):
            continue
        for place in texture.occurrences:
            # The CLUT block's own header: 8 bytes of TIM header, then block bytes, x, y.
            x, y = struct.unpack_from("<HH", blobs[place.file], place.file_offset + 12)
            assert (x, y) == (texture.tim.clut.x, texture.tim.clut.y), texture.id
            placed += 1
    assert placed, "no texture on this disc places its CLUT; the gate proves nothing"


# --- gate 2: the PNG round trip -------------------------------------------------------------


def test_every_distinct_image_round_trips_through_an_indexed_png(inv, census_rows):
    checked = 0
    for texture in inv.textures:
        page = png.read(to_png(texture.tim, 0))
        indices, report = indices_for(texture, page, 0)
        assert report is None, f"{texture.id} needed colour matching"
        assert texture.tim.with_indices(indices).serialise() == texture.tim.serialise(), texture.id
        checked += 1
    assert checked == len(census_rows)  # every image in the tracked census, not just some


def test_the_most_multi_clut_images_round_trip_through_every_one_of_their_palettes(inv):
    """488 images carry several CLUTs, up to 21; the palette must not leak into the pixels."""
    busiest = sorted(inv.textures, key=lambda t: -t.tim.clut.count)[:10]
    assert busiest[0].tim.clut.count == 21
    pairs = 0
    for texture in busiest:
        for clut in range(texture.tim.clut.count):
            page = png.read(to_png(texture.tim, clut))
            indices, _ = indices_for(texture, page, clut)
            assert texture.tim.with_indices(indices).serialise() == texture.tim.serialise()
            pairs += 1
    assert pairs == sum(t.tim.clut.count for t in busiest)


def test_a_colour_matched_round_trip_of_every_image_rewrites_no_pixel(inv, census_rows):
    """The gate on the *colour* path, which the indexed gate above cannot see.

    2,473 of this disc's (texture, CLUT) pairs hold duplicate RGBA colours — STP variants
    and repeated entries — so a lookup keyed on colour alone answers a pixel that was
    never touched with some *other* entry holding the same colour. The harm is not
    theoretical: an artist whose tool saves RGBA (or reorders the palette) gets patches
    over pixels they never edited, and where the two entries differ in their STP bit the
    console stops blending them. So: decode every image to RGBA, map it straight back,
    and require the bytes — and therefore the emitted patches and every STP bit — to be
    the ones that were already there.
    """
    offenders = []
    for texture in inv.textures:
        tim = texture.tim
        edited = tim.with_indices(indices_from_rgba(tim, tim.decode_rgba(0), 0))
        patches = patches_for(texture, edited)
        if patches:
            before, after = tim.indices(), edited.indices()
            flips = sum(
                a != b for a, b in zip(tim.decode_stp(0), edited.decode_stp(0), strict=True)
            )
            moved = sum(a != b for a, b in zip(before, after, strict=True))
            offenders.append((texture.id, moved, len(patches), flips))
    assert not offenders, (
        f"{len(offenders)} of {len(inv.textures)} images re-point pixels a colour-matched "
        f"round trip never touched: "
        f"{sum(o[1] for o in offenders)} indices, {sum(o[2] for o in offenders)} patches, "
        f"{sum(o[3] for o in offenders)} STP bits flipped; worst "
        f"{sorted(offenders, key=lambda o: -o[1])[:3]}"
    )
    assert len(inv.textures) == len(census_rows)


def test_a_different_clut_is_a_different_picture_but_the_same_pixels(inv):
    texture = max(inv.textures, key=lambda t: t.tim.clut.count)
    first = png.read(to_png(texture.tim, 0))
    last = png.read(to_png(texture.tim, texture.tim.clut.count - 1))
    assert first.indices == last.indices
    assert first.palette != last.palette


# --- gate 3: an edit reaches every copy --------------------------------------------------------


@pytest.fixture(scope="module")
def most_copied(inv):
    return max(inv.textures, key=lambda t: t.copies)


def test_exporting_and_re_importing_the_most_copied_image_changes_nothing(
    archive, inv, most_copied, tmp_path_factory
):
    out = tmp_path_factory.mktemp("export")
    export(archive, out, inv=_only(inv, most_copied.id))
    result = import_edits(archive, out, inv=inv)
    assert result.patches == ()
    assert result.unchanged == (most_copied.id,)  # a directory of no PNGs also has no patches


def test_one_changed_pixel_reaches_every_copy_of_the_most_copied_image(
    archive, inv, most_copied, census_rows, tmp_path_factory
):
    """A redraw that missed one copy would flicker between two versions as the map loads.

    How many copies that is comes from the tracked census — `max(copies)` — rather than
    from research prose retyped here, so the two can't drift apart silently.
    """
    assert most_copied.copies == max(int(row["copies"]) for row in census_rows.values())
    out = tmp_path_factory.mktemp("edit")
    export(archive, out, inv=_only(inv, most_copied.id))
    path = out / f"{most_copied.id}.png"
    page = png.read(path.read_bytes())
    pixels = bytearray(page.indices)
    pixels[0] ^= 1  # still a palette entry this image already uses
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
    result = import_edits(archive, out, inv=inv)
    assert result.changed == (most_copied.id,)
    assert len(result.patches) == most_copied.copies
    assert {len(p.new) for p in result.patches} == {1}
    assert {p.offset for p in result.patches} == {
        o.file_offset + (most_copied.tim.length - len(most_copied.tim.data))
        for o in most_copied.occurrences
    }
    for patch in result.patches:
        assert archive.boku[patch.offset : patch.offset + len(patch.old)] == patch.old


def test_a_diary_page_is_the_shape_the_census_says_it_is(inv, census_rows):
    """`NIKKI_001` is the sample `GFX-02` weighs the redraw path on."""
    texture = inv.get("_DATA_NIKKI.BIN_NIKKI_001__000000")
    assert (texture.width, texture.height, texture.tim.bpp) == (240, 192, 8)
    assert census_rows[texture.id]["category"] == "picture-diary page"
    page = png.read(to_png(texture.tim, 0))
    assert (page.colour_type, page.bit_depth) == (3, 8)
    assert len(page.palette) == 256


def test_the_patches_an_edit_implies_are_what_the_image_build_takes(
    archive, inv, most_copied, real_image, tmp_path_factory
):
    """`import_edits` hands its patches straight to the build's pre-write gate.

    The harm this pins is a pipeline that cannot be connected: the build verifies and
    writes `reinsert.ByteEdit`s, reading `.reason` and `.end` off each one, so a texture
    patch of any other shape fails at the moment someone tries to use it — after the
    export, the redraw and the import. Passing the gate also means every `old` in the
    list is the bytes that are in the image right now, at all 287 places.
    """
    out = tmp_path_factory.mktemp("build-edit")
    export(archive, out, inv=_only(inv, most_copied.id))
    path = out / f"{most_copied.id}.png"
    page = png.read(path.read_bytes())
    pixels = bytearray(page.indices)
    pixels[0] ^= 1
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
    patches = import_edits(archive, out, inv=inv).patches
    assert patches, "the edit produced nothing to verify"
    entries = check_before_writing(
        real_image, tmp_path_factory.mktemp("build-out"), patches, what="texture build"
    )
    assert {p.file for p in patches} <= set(entries)
    assert all(p.reason.startswith(f"texture {most_copied.id} in ") for p in patches)


def _only(inv: Inventory, *ids: str) -> Inventory:
    """An inventory narrowed to a few textures, so a test exports two PNGs and not 824."""
    return Inventory(tuple(t for t in inv.textures if t.id in ids))
