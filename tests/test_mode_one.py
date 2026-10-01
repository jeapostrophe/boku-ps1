"""`PLAN REL-02`: `./make.sh export-to-mode-one` -- the built image, packed the way Mode One
loads a PS1 disc, and the checksum it pins.

Synthetic throughout: a few random raw sectors stand in for `build/days/`, and a directory
holding `one/index/boku.sha1` stands in for the retro-trainer checkout. The hash the pin
must hold is always recomputed from the file the export wrote, never typed.
"""

from __future__ import annotations

import hashlib
import random
import shutil

import pytest

from boku.build import CUE_NAME, CUE_TEXT, IMAGE_NAME
from boku.mode_one import PIN_FILE, ROM_FILE, ModeOneError, export_to_mode_one
from boku.reader import BUILD_ID_NAME

needs_chdman = pytest.mark.skipif(
    shutil.which("chdman") is None, reason="chdman is not on PATH (brew install rom-tools)"
)

SECTOR = 2352
OLD_PIN = "0" * 40 + "\n"


def sha1_of(path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


@pytest.fixture
def build(tmp_path):
    """A `build/days/` as `./make.sh build-days` leaves it: the image, its cue, its id."""
    days = tmp_path / "build" / "days"
    days.mkdir(parents=True)
    (days / IMAGE_NAME).write_bytes(random.Random(11).randbytes(SECTOR * 24))
    (days / CUE_NAME).write_text(CUE_TEXT)
    (days / BUILD_ID_NAME).write_text("20260925T1200Z-abcdef12\n")
    return days


@pytest.fixture
def mode_one(tmp_path):
    """A Mode One checkout that already carries the Boku entry and an older pin."""
    root = tmp_path / "retro-trainer"
    (root / PIN_FILE).parent.mkdir(parents=True)
    (root / PIN_FILE).write_text(OLD_PIN)
    return root


@needs_chdman
def test_the_pin_is_the_sha1_of_the_disc_it_wrote(build, mode_one):
    result = export_to_mode_one(build, mode_one)

    chd = mode_one / ROM_FILE
    assert chd.read_bytes()[:8] == b"MComprHD", "Mode One loads a PS1 disc as a .chd"
    assert (mode_one / PIN_FILE).read_text() == sha1_of(chd) + "\n"
    assert result.sha1 == sha1_of(chd)
    assert result.build_id == "20260925T1200Z-abcdef12"
    assert sorted(p.name for p in chd.parent.iterdir()) == [chd.name], "no partial left behind"


@needs_chdman
def test_a_rebuilt_image_re_pins(build, mode_one):
    first = export_to_mode_one(build, mode_one).sha1
    (build / IMAGE_NAME).write_bytes(random.Random(12).randbytes(SECTOR * 24))
    second = export_to_mode_one(build, mode_one).sha1

    assert first != second
    assert (mode_one / PIN_FILE).read_text() == second + "\n"
    assert sha1_of(mode_one / ROM_FILE) == second


def test_refuses_a_directory_that_is_not_mode_one_with_boku(build, tmp_path):
    elsewhere = tmp_path / "not-mode-one"
    elsewhere.mkdir()
    with pytest.raises(ModeOneError, match=r"one/index/boku\.sha1"):
        export_to_mode_one(build, elsewhere)
    assert list(elsewhere.iterdir()) == [], "nothing is written into it"


def test_refuses_without_a_build_and_names_the_verb(tmp_path, mode_one):
    with pytest.raises(ModeOneError, match="build-days"):
        export_to_mode_one(tmp_path / "build" / "days", mode_one)
    assert (mode_one / PIN_FILE).read_text() == OLD_PIN
    assert not (mode_one / ROM_FILE).exists()


@needs_chdman
def test_a_failed_pack_keeps_the_old_disc_and_the_old_pin(build, mode_one, tmp_path, monkeypatch):
    """The pin and the disc move together or not at all: a pack that fails must leave the
    previous export -- a disc and the pin that matches it -- exactly as it was. The stand-in
    chdman writes half a file to its `-o` and then fails, as a real one killed mid-pack
    would; a real one refusing a bad cue exits before it opens `-o`, which proves nothing."""
    export_to_mode_one(build, mode_one)
    disc, pin = (mode_one / ROM_FILE).read_bytes(), (mode_one / PIN_FILE).read_text()

    dies = tmp_path / "chdman-dies"
    dies.write_text('#!/bin/sh\nwhile [ "$1" != -o ]; do shift; done\necho half > "$2"\nexit 1\n')
    dies.chmod(0o755)
    monkeypatch.setattr("boku.chd.CHDMAN", str(dies))
    with pytest.raises(ModeOneError, match="createcd failed"):
        export_to_mode_one(build, mode_one)

    assert (mode_one / ROM_FILE).read_bytes() == disc
    assert (mode_one / PIN_FILE).read_text() == pin
    assert sorted(p.name for p in (mode_one / ROM_FILE).parent.iterdir()) == [ROM_FILE.name]
