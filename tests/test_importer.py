"""The import step, on images the test builds -- verification, refusal, and what it writes.

`import_disc` pins the real dump's size and sha1, so these tests repoint those two
constants at the synthetic image they just built (computed, never typed). The constants
themselves are checked against the real dump in `test_real_disc.py`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from boku import importer
from boku.cli import main
from boku.importer import DestinationSet, ImportRefused, import_disc, resolve_source
from tests import synth


def build_source(tmp_path: Path, children: list, name: str = "source.img") -> Path:
    path = tmp_path / name
    path.write_bytes(synth.build_image(children))
    return path


def pin(monkeypatch: pytest.MonkeyPatch, image: Path) -> str:
    """Make the importer expect exactly this image; returns its sha1."""
    digest = hashlib.sha1(image.read_bytes()).hexdigest()
    monkeypatch.setattr(importer, "IMAGE_SIZE", image.stat().st_size)
    monkeypatch.setattr(importer, "IMAGE_SHA1", digest)
    return digest


@pytest.fixture
def tree() -> list:
    return [
        synth.File("SYSTEM.CNF", b"BOOT = cdrom:\\SCPS_100.88;1\r\n"),
        synth.File("SCPS_100.88", b"PS-X EXE" + bytes(3000)),
        synth.Directory(
            "__STR",
            [
                synth.File("BOKU_XA.XAM", b"\x55" * 9000, form=2, interleaved=True),
                synth.File("M27.IKI", b"\x66" * 5000, form=2),
            ],
        ),
    ]


def test_import_writes_the_image_the_files_and_a_manifest(tmp_path, tree, monkeypatch):
    """The whole step: every Form 1 file cooked, byte for byte, and nothing else claimed."""
    source = build_source(tmp_path, tree)
    expected_sha1 = pin(monkeypatch, source)
    out = tmp_path / "out"

    result = import_disc(source, out, progress=lambda _message: None)

    assert (out / "image.img").read_bytes() == source.read_bytes()
    assert result.image_sha1 == expected_sha1
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["image"]["sha1"] == expected_sha1
    by_path = {entry["path"]: entry for entry in manifest["entries"]}
    assert set(by_path) == {
        "/SYSTEM.CNF",
        "/SCPS_100.88",
        "/__STR",
        "/__STR/BOKU_XA.XAM",
        "/__STR/M27.IKI",
    }
    for source_file in (tree[0], tree[1]):
        record = by_path[f"/{source_file.name}"]
        written = out / record["extracted"]
        assert written.read_bytes() == source_file.content, source_file.name
        assert record["size"] == len(source_file.content)
        assert record["sha1"] == hashlib.sha1(source_file.content).hexdigest()


def test_every_extracted_file_is_exactly_the_size_its_directory_record_claims(
    tmp_path, tree, monkeypatch
):
    """The manifest's own numbers must describe the bytes on disk, not the other way round."""
    source = build_source(tmp_path, tree)
    pin(monkeypatch, source)
    out = tmp_path / "out"
    result = import_disc(source, out, progress=lambda _message: None)
    extracted = [entry for entry in result.manifest["entries"] if entry["extracted"]]
    assert extracted, "nothing was extracted"
    for entry in extracted:
        written = out / entry["extracted"]
        assert written.stat().st_size == entry["size"], entry["path"]
        assert hashlib.sha1(written.read_bytes()).hexdigest() == entry["sha1"], entry["path"]


def test_form2_files_are_recorded_but_not_extracted(tmp_path, tree, monkeypatch):
    """A 2048-byte read of XA/STR data is garbage; the manifest keeps LBA and size instead."""
    source = build_source(tmp_path, tree)
    pin(monkeypatch, source)
    out = tmp_path / "out"
    result = import_disc(source, out, progress=lambda _message: None)

    for path in ("/__STR/BOKU_XA.XAM", "/__STR/M27.IKI"):
        entry = next(e for e in result.manifest["entries"] if e["path"] == path)
        assert entry["extracted"] is None
        assert entry["xa"]["form"] == 2
        assert entry["lba"] > 0 and entry["size"] > 0
        assert entry["not_extracted"]
    assert not (out / "files" / "__STR" / "BOKU_XA.XAM").exists()
    assert (out / "files" / "__STR").is_dir()
    assert result.extracted_count == 2


def test_an_interleaved_file_is_not_cooked_even_though_its_first_sector_is_form1(
    tmp_path, monkeypatch
):
    """The `.IKI` shape, measured on the disc: STR video sectors are Mode 2 Form 1 and
    carry no form bit in the directory record, with Form 2 audio interleaved through them.
    Deciding by the first sector alone would cook 86 MB of nonsense."""
    tree = [
        synth.File("SCPS_100.88", b"PS-X EXE" + bytes(100)),
        synth.Directory(
            "__STR",
            [synth.File("M27.IKI", b"\x77" * 5000, form=1, interleaved=True, declare_form=False)],
        ),
    ]
    source = build_source(tmp_path, tree)
    pin(monkeypatch, source)
    out = tmp_path / "out"

    result = import_disc(source, out, progress=lambda _message: None)

    entry = next(e for e in result.manifest["entries"] if e["path"] == "/__STR/M27.IKI")
    assert entry["first_sector_form"] == 1, "fixture no longer reproduces the .IKI shape"
    assert entry["xa"]["form"] is None
    assert entry["extracted"] is None
    assert "interleaved" in entry["not_extracted"]
    assert not (out / "files" / "__STR" / "M27.IKI").exists()
    assert result.extracted_count == 1


def test_a_wrong_image_is_refused_with_both_hashes_and_writes_nothing(tmp_path, tree, monkeypatch):
    source = build_source(tmp_path, tree)
    actual = pin(monkeypatch, source)
    wrong = "0" * 40
    monkeypatch.setattr(importer, "IMAGE_SHA1", wrong)
    out = tmp_path / "out"

    with pytest.raises(ImportRefused) as refusal:
        import_disc(source, out, progress=lambda _message: None)

    message = str(refusal.value)
    assert wrong in message and actual in message
    assert not out.exists(), "a refused import must leave no partial output"
    assert list(tmp_path.glob(".out*")) == [], "staging directory was left behind"


def test_a_refusal_names_the_dump_the_contributor_pointed_at(tmp_path, tree, monkeypatch):
    """Not the staging copy: that path is deleted before the message reaches the terminal."""
    source = build_source(tmp_path, tree, name="my-dump.bin")
    pin(monkeypatch, source)
    monkeypatch.setattr(importer, "IMAGE_SHA1", "0" * 40)

    with pytest.raises(ImportRefused) as refusal:
        import_disc(source, tmp_path / "out", progress=lambda _message: None)

    message = str(refusal.value)
    assert str(source) in message
    assert "importing" not in message, "the refusal names a staging path the user never had"


def test_an_image_of_the_wrong_size_is_refused_before_it_is_hashed(tmp_path, tree, monkeypatch):
    """Hashing 659 MB to learn what the size already said is a slow way to say no."""
    source = build_source(tmp_path, tree)
    pin(monkeypatch, source)
    monkeypatch.setattr(importer, "IMAGE_SIZE", source.stat().st_size + 2352)

    def refuse_to_hash(_path):
        raise AssertionError("sha1 was computed although the size was already wrong")

    monkeypatch.setattr(importer, "sha1_of", refuse_to_hash)
    out = tmp_path / "out"
    with pytest.raises(ImportRefused, match=r"bytes; the expected dump is"):
        import_disc(source, out, progress=lambda _message: None)
    assert not out.exists()


def test_two_names_differing_only_in_case_are_refused(tmp_path, monkeypatch):
    """macOS would silently let the second overwrite the first (research/disc-recon.md)."""
    tree = [synth.File("BOKU.BIN", b"a" * 100), synth.File("boku.bin", b"b" * 100)]
    source = build_source(tmp_path, tree)
    pin(monkeypatch, source)
    out = tmp_path / "out"
    with pytest.raises(ImportRefused, match=r"case-insensitive"):
        import_disc(source, out, progress=lambda _message: None)
    assert not out.exists()


def test_the_image_and_manifest_names_are_reserved_before_any_disc_entry():
    """So a later row that writes an output beside the image cannot reintroduce the trap."""
    destinations = DestinationSet()
    destinations.reserve("image.img")
    with pytest.raises(ImportRefused, match=r"case-insensitive"):
        destinations.reserve("IMAGE.IMG")


def test_a_previous_import_is_replaced_whole(tmp_path, tree, monkeypatch):
    source = build_source(tmp_path, tree)
    pin(monkeypatch, source)
    out = tmp_path / "out"
    out.mkdir()
    (out / "manifest.json").write_text("{}")
    (out / "stale.txt").write_text("from an older import")

    import_disc(source, out, progress=lambda _message: None)

    assert not (out / "stale.txt").exists()
    assert json.loads((out / "manifest.json").read_text())["entries"]
    assert [p for p in tmp_path.iterdir() if p.name.startswith(".out")] == []


def test_an_out_directory_that_is_not_a_previous_import_is_refused(tmp_path, tree, monkeypatch):
    """A successful import deletes `--out` whole, so `--out ~/Downloads` must not run."""
    source = build_source(tmp_path, tree)
    pin(monkeypatch, source)
    out = tmp_path / "downloads"
    out.mkdir()
    (out / "tax-return.pdf").write_bytes(b"%PDF-1.4 not yours to delete")

    with pytest.raises(ImportRefused, match=r"not a previous import"):
        import_disc(source, out, progress=lambda _message: None)

    assert (out / "tax-return.pdf").is_file()


def test_the_cue_the_import_writes_is_one_this_tool_can_read_back(tmp_path, tree, monkeypatch):
    """`image.cue` is generated here and parsed here; the two must not drift apart."""
    source = build_source(tmp_path, tree)
    pin(monkeypatch, source)
    out = tmp_path / "out"
    import_disc(source, out, progress=lambda _message: None)
    assert importer.image_from_cue(out / "image.cue") == (out / "image.img").resolve()


def test_a_cue_sheet_resolves_to_the_binary_beside_it(tmp_path, tree, monkeypatch):
    binary = build_source(tmp_path, tree, name="disc.bin")
    pin(monkeypatch, binary)
    cue = tmp_path / "disc.cue"
    cue.write_text('FILE "disc.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
    out = tmp_path / "out"
    import_disc(cue, out, progress=lambda _message: None)
    assert (out / "image.img").read_bytes() == binary.read_bytes()


def test_a_cue_that_is_not_one_mode2_2352_track_is_refused(tmp_path):
    """Two failures, separately: more than one FILE, and a single track of the wrong mode.

    The second is checked on its own cue so that the FILE count cannot stand in for it --
    this disc is one MODE2/2352 track, and a MODE1 image read as Mode 2 is silent nonsense.
    """
    two_files = tmp_path / "two.cue"
    two_files.write_text(
        'FILE "a.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n'
        'FILE "b.bin" BINARY\n  TRACK 02 AUDIO\n    INDEX 01 00:00:00\n'
    )
    with pytest.raises(ImportRefused, match=r"2 FILE entries"):
        importer.image_from_cue(two_files)

    wrong_mode = tmp_path / "mode1.cue"
    (tmp_path / "a.bin").write_bytes(b"not this disc")
    wrong_mode.write_text('FILE "a.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n')
    with pytest.raises(ImportRefused, match=r"expected exactly one MODE2/2352 track"):
        importer.image_from_cue(wrong_mode)


def test_source_comes_from_the_argument_or_the_environment(tmp_path, monkeypatch):
    dump = tmp_path / "mine.img"
    dump.write_bytes(b"x")
    monkeypatch.delenv(importer.SOURCE_ENV_VAR, raising=False)
    assert resolve_source(str(dump)) == dump
    with pytest.raises(ImportRefused, match=importer.SOURCE_ENV_VAR):
        resolve_source(None)
    monkeypatch.setenv(importer.SOURCE_ENV_VAR, str(dump))
    assert resolve_source(None) == dump
    with pytest.raises(ImportRefused, match=r"does not exist"):
        resolve_source(str(tmp_path / "nope.img"))


def test_cli_import_reports_a_refusal_on_stderr(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv(importer.SOURCE_ENV_VAR, raising=False)
    status = main(["import", str(tmp_path / "missing.chd"), "--out", str(tmp_path / "out")])
    assert status == 2
    assert "refused" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()
