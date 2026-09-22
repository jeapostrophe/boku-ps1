"""`boku.movies` -- the slicer, the two note parsers, and the table merge. No disc needed.

Each case is written at the narrowest input that exhibits its harm:

* the slicer against a synthetic image whose sectors say where they are, because a slice
  that is one sector out, or cooked to 2048 bytes, still looks like a file;
* the `research/movies.md` § 1 parser against a row naming two ids and two files, because
  that is the only row shape a careless parser mis-pairs;
* the merge against a table that already has hand-written columns, because a regeneration
  that wipes them destroys the only work the file exists to collect.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from boku import disc
from boku.disc import RAW_SECTOR_SIZE, DiscImage
from boku.movies import (
    FPS,
    MOVIES_MD,
    MOVIES_TSV,
    SCENE_EDGES_TSV,
    MovieError,
    MovieFile,
    _section,
    _table_rows,
    build_tsv,
    decode_one,
    ffprobe_streams,
    iki_entries,
    java_binary,
    jpsxdec_jar,
    may_skip,
    parse_index,
    parse_issuers,
    parse_movie_ids,
    parse_skip_masks,
    read_hand_columns,
    slice_movie,
    verify_output,
)
from tests import synth

# --- the slicer ----------------------------------------------------------------------------------


# Two movies, so an off-by-one extent lands in the neighbour rather than in padding, and
# each is several sectors long. The contents differ per file and per sector.
def _movie_content(marker: int, sectors: int) -> bytes:
    return b"".join(bytes([marker, i & 0xFF]) * 1024 for i in range(sectors))


@pytest.fixture
def image_with_two_movies(tmp_path: Path) -> Path:
    tree = [
        synth.File("SYSTEM.CNF", b"BOOT=cdrom:\\SCPS_100.88;1\n"),
        synth.Directory(
            "__STR",
            [
                synth.File("M00.IKI", _movie_content(0xA0, 3), form=1, interleaved=True),
                synth.File("M01.IKI", _movie_content(0xB0, 2), form=1, interleaved=True),
            ],
        ),
    ]
    path = tmp_path / "test.img"
    path.write_bytes(synth.build_image(tree))
    return path


def test_the_slice_is_the_raw_sectors_of_that_extent_and_no_neighbour(
    tmp_path: Path, image_with_two_movies: Path
) -> None:
    """The one thing a decoder needs: sector 0 of the slice is the file's first sector.

    Checked through the sectors' own MSF headers, which `test_disc.py` pins independently,
    so neither an off-by-one LBA nor a 2048-byte cooked read can pass: the first and last
    headers must decode to the extent's first and last addresses, and the user data must
    be the bytes this test laid out for the *second* movie, not the first.
    """
    out = tmp_path / "M01"
    with DiscImage(image_with_two_movies) as image:
        entry = next(e for e in image.walk() if e.path == "/__STR/M01.IKI")
        movie = next(m for m in iki_entries(image) if m.name == "M01")
        written = slice_movie(image, movie, out)

    raw = out.read_bytes()
    assert written == entry.sector_count
    assert len(raw) == RAW_SECTOR_SIZE * entry.sector_count, "a cooked slice is not a movie"
    first = disc.parse_sector(raw[:RAW_SECTOR_SIZE], 0)
    last = disc.parse_sector(raw[-RAW_SECTOR_SIZE:], 0)
    assert first.header_lba == entry.lba
    assert last.header_lba == entry.lba + entry.sector_count - 1
    assert first.data[:2] == bytes([0xB0, 0]), "the slice starts inside the wrong file"


def test_a_frame_count_is_refused_when_the_extent_is_not_whole_frames() -> None:
    """The narrowest bad extent: one sector over a frame slot.

    Silently flooring it would put a wrong `frames` in the tracked table and hide a movie
    this tool cannot read.
    """
    odd = MovieFile(name="M99", path="/__STR/M99.IKI", lba=100, sectors=821)
    with pytest.raises(MovieError) as refusal:
        odd.frames  # noqa: B018 -- the property is what raises
    assert "821 sectors" in str(refusal.value) and "10-sector frame slots" in str(refusal.value)


def test_iki_entries_finds_only_the_movies(image_with_two_movies: Path) -> None:
    with DiscImage(image_with_two_movies) as image:
        names = [movie.name for movie in iki_entries(image)]
    assert names == ["M00", "M01"]


# --- research/movies.md section 1 --------------------------------------------------------------

TWO_ID_ROW = """\
## 1. Which movie is which

| id | file | stop frame | issued by |
|---|---|---|---|
| 0 | `M27` | 58 | nothing |
| 1, 2 | `M031`, `M032` | 47 | `E4015` |
| 3, 4 | `M21`, `M22` | 527, 512 | nothing |

## 2. The player

1. `movie_skip_mask_for` → `movie_set_skip_mask`:
   ids 1\u20132 → `0x0860`; 4 → 0; every other id → `0x0800` (the pad word).
"""


def test_a_row_naming_two_ids_pairs_each_id_with_its_own_file_and_stop_frame() -> None:
    """The row shape that mis-pairs: two ids, two files, and two *different* stop frames."""
    ids = {entry.id: (entry.file, entry.stop_frame) for entry in parse_movie_ids(TWO_ID_ROW)}
    assert ids == {
        0: ("M27", 58),
        1: ("M031", 47),
        2: ("M032", 47),
        3: ("M21", 527),
        4: ("M22", 512),
    }


def test_a_row_whose_ids_and_files_do_not_pair_is_refused() -> None:
    """Three ids and two files: which file the third id plays is not stated, so do not guess."""
    broken = TWO_ID_ROW.replace("| 1, 2 | `M031`, `M032` |", "| 1, 2, 5 | `M031`, `M032` |")
    with pytest.raises(MovieError) as refusal:
        parse_movie_ids(broken)
    assert "3 ids and 2 file values" in str(refusal.value)


def test_a_table_with_a_gap_in_its_ids_is_refused() -> None:
    """`MOVIE n` indexes the table, so a missing id means a row of the list points nowhere."""
    with pytest.raises(MovieError) as refusal:
        parse_movie_ids(TWO_ID_ROW.replace("| 3, 4 |", "| 7, 8 |"))
    assert "no gaps" in str(refusal.value)


def test_the_tracked_note_still_parses_into_a_contiguous_table() -> None:
    """The real § 1, checked for the shape `MOVIE n` needs -- not for values typed here."""
    entries = parse_movie_ids(MOVIES_MD.read_text(encoding="utf-8"))
    assert [entry.id for entry in entries] == list(range(len(entries)))
    assert len({entry.file for entry in entries}) < len(entries), (
        "§ 1 no longer has an id sharing a file with another; the shares_file_with column "
        "was written for that case"
    )


def test_only_the_first_table_of_a_section_is_read_as_the_movie_table() -> None:
    """§ 1 gaining a second table must not feed its rows in as `g_movie_table` entries.

    The second table here has a numeric first column, so nothing downstream would refuse
    it: its rows would simply become ids 5 and 6 of a table that has none.
    """
    two_tables = TWO_ID_ROW.replace(
        "\n## 2. The player",
        "\nSome prose between them.\n\n| n | bytes |\n|---|---|\n| 5 | 16128 |\n| 6 | 16020 |\n"
        "\n## 2. The player",
    )
    assert [entry.id for entry in parse_movie_ids(two_tables)] == [0, 1, 2, 3, 4]


# --- research/movies.md section 2.1: the skip masks ---------------------------------------------


def test_a_zero_skip_mask_is_the_only_thing_that_makes_a_movie_unskippable() -> None:
    """Parsed from § 2.1's own sentence, so the table cannot drift from the measurement."""
    masks = parse_skip_masks(MOVIES_MD.read_text(encoding="utf-8"), range(27))
    unskippable = sorted(movie for movie, mask in masks.items() if mask == 0)
    assert unskippable == [24], "§ 2.1 named a different set of unskippable movies"
    assert masks[1] == 0x0860 and masks[0] == 0x0800


def test_a_mask_clause_added_after_the_default_one_is_still_read() -> None:
    """English grows by appending, and the default clause reads like the last word.

    A parser that stopped at `every other id -> <mask>` would silently report the appended
    id as skippable -- a wrong bit in the tracked table, with the gate still green, on the
    column a skip-aware subtitle path would branch on.
    """
    note = MOVIES_MD.read_text(encoding="utf-8")
    appended = note.replace(
        "every other id \u2192 `0x0800`", "every other id \u2192 `0x0800`; 26 \u2192 0"
    )
    assert appended != note, "section 2.1 no longer has the clause this case appends to"

    masks = parse_skip_masks(appended, range(27))

    assert sorted(movie for movie, mask in masks.items() if mask == 0) == [24, 26]


def test_the_masks_are_read_whichever_arrow_the_note_uses() -> None:
    """`->` for `\u2192` is a plain rewording, and must not refuse the whole run."""
    note = MOVIES_MD.read_text(encoding="utf-8")
    assert parse_skip_masks(note.replace("\u2192", "->"), range(27)) == parse_skip_masks(
        note, range(27)
    )


def test_a_section_that_no_longer_states_the_masks_is_refused() -> None:
    """Silently defaulting every movie to skippable would put a wrong column in the table."""
    note = MOVIES_MD.read_text(encoding="utf-8").replace("every other id", "some other id")
    with pytest.raises(MovieError) as refusal:
        parse_skip_masks(note, range(27))
    assert "no longer states the skip masks" in str(refusal.value)


# --- research/data/scene-edges.tsv: the issuers -------------------------------------------------


def test_the_issuers_are_the_events_whose_movie_node_names_the_id() -> None:
    edges = "event\tfrom\tto\tcondition\n" + "\n".join(
        [
            "E0009\tE0009.1@10A\tE0009.MOVIE20:G02@12E\t",
            "E0009\tE0009.MOVIE20:G02@12E\tEND\t",
            "E0103\tE0103.2@146\tE0103.MOVIE20:G02@16E\t",
            "E3182\tE3182.0@58\tE3182.MOVIE24:H02@9E\t",
        ]
    )
    assert parse_issuers(edges) == {20: ["E0009", "E0103"], 24: ["E3182"]}


def test_movie_2_is_not_read_out_of_movie_20() -> None:
    """The colon is what ends the id; without it `MOVIE20` also answers for movie 2."""
    edges = "event\tfrom\tto\n" + "E0009\tA\tE0009.MOVIE20:G02@12E"
    assert 2 not in parse_issuers(edges)


def tracked_rows() -> list[dict[str, str]]:
    """The tracked table as named fields -- never by column position, which moves."""
    rows = [
        line.split("\t")
        for line in MOVIES_TSV.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    return [dict(zip(rows[0], row, strict=True)) for row in rows[1:]]


def test_the_tracked_table_and_the_tracked_edges_name_the_same_issuers() -> None:
    """§ 1's "issued by" column is this derivation written out, so the two must agree.

    Both sides are tracked, so it needs no disc -- and it is the check that catches a note
    edited by hand without re-running the walk, which is how the two drift apart.
    """
    issuers = parse_issuers(SCENE_EDGES_TSV.read_text(encoding="utf-8"))
    tracked = {int(row["id"]): row["issued_by"] for row in tracked_rows()}
    for movie, column in tracked.items():
        expected = ",".join(issuers.get(movie, [])) or "none found"
        assert column == expected, (
            f"movie {movie}: the table says {column!r}, the edges {expected!r}"
        )


def test_section_1_and_the_scene_graph_name_the_same_issuers_for_each_id() -> None:
    """The pairing, not just the presence: § 1's column against the graph, id by id.

    `E4015` appearing *somewhere* in § 1 says nothing about which movie it issues, and the
    column is hand-written -- so the row's own cell is what has to be parsed and compared.
    """
    note = MOVIES_MD.read_text(encoding="utf-8")
    from_graph = {
        movie: set(events)
        for movie, events in parse_issuers(SCENE_EDGES_TSV.read_text(encoding="utf-8")).items()
    }
    for cells in _table_rows(_section(note, "1.")):
        ids = [int(part) for part in cells[0].split(",")]
        in_note = set(re.findall(r"\bE\d{4}\b", cells[3]))
        for movie in ids:
            assert in_note == from_graph.get(movie, set()), (
                f"movie {movie}: § 1 names {sorted(in_note)}, scene-edges.tsv "
                f"{sorted(from_graph.get(movie, set()))}"
            )


# --- the table ----------------------------------------------------------------------------------

FRAMES = {"M27": 4244, "M031": 52, "M032": 52, "M21": 532, "M22": 517}
EDGES = "event\tfrom\tto\n" + "E4015\tA\tE4015.MOVIE1:G18@10\n"


def test_a_regeneration_keeps_the_hand_written_columns_and_refreshes_the_rest() -> None:
    """The harm this exists to stop: `./make.sh movies` wiping what Jay wrote from watching.

    The previous table is built with a stale derived column (`frames`) beside the hand
    columns, so one assertion cannot pass by the whole row being copied: the derived
    column must change and the hand columns must not.
    """
    first = build_tsv(TWO_ID_ROW, EDGES, FRAMES)
    edited = first.replace(
        "\t\t\n", "\tThe opening: a car on a country road at dusk\tnarration over the credits\n", 1
    ).replace("4244", "9999", 1)
    assert "9999" in edited, "the fixture no longer holds a derived column to make stale"

    again = build_tsv(TWO_ID_ROW, EDGES, FRAMES, previous=edited)

    rows = [line.split("\t") for line in again.splitlines() if line and not line.startswith("#")]
    header, body = rows[0], rows[1:]
    row0 = dict(zip(header, body[0], strict=True))
    assert row0["what_it_shows"] == "The opening: a car on a country road at dusk"
    assert row0["notes"] == "narration over the credits"
    assert row0["frames"] == "4244", "the derived column was carried over instead of regenerated"


def test_a_tab_typed_into_a_hand_column_is_refused_rather_than_shifting_the_rest() -> None:
    """The narrowest editing slip, and the one that costs the most.

    A tab inside `what_it_shows` gives the row one column too many; zipping it against the
    header would drop `notes` off the end, and the next `./make.sh movies` would write the
    loss back over the tracked file with nothing to say about it.
    """
    with pytest.raises(MovieError) as refusal:
        read_hand_columns("id\twhat_it_shows\tnotes\n3\tsaw it\tand then\tmine\n")
    assert "4 columns and the header has 3" in str(refusal.value)


def test_a_hand_column_is_kept_even_when_the_columns_move() -> None:
    """The merge is by column name, not position, so adding a column cannot shuffle notes."""
    kept = read_hand_columns("# comment\nnotes\tid\twhat_it_shows\nmine\t3\tsaw it\n")
    assert kept == {3: {"what_it_shows": "saw it", "notes": "mine"}}


def test_seconds_is_the_stop_frame_not_the_whole_file() -> None:
    """An id that stops early plays less than its file holds -- ids 0 and 15 are that case."""
    rows = [
        line.split("\t")
        for line in build_tsv(TWO_ID_ROW, EDGES, FRAMES).splitlines()
        if line and not line.startswith("#")
    ]
    row0 = dict(zip(rows[0], rows[1], strict=True))
    assert row0["stop_frame"] == "58"
    assert row0["frames"] == "4244"
    assert row0["seconds"] == f"{58 / FPS:.1f}"


def test_an_id_whose_file_is_not_on_the_image_is_refused() -> None:
    with pytest.raises(MovieError) as refusal:
        build_tsv(TWO_ID_ROW, EDGES, {name: 1 for name in FRAMES if name != "M27"})
    assert "M27" in str(refusal.value)


# --- jPSXdec's index and the output check --------------------------------------------------------


def test_the_index_line_is_read_as_its_own_fields() -> None:
    index = (
        "[jPSXdec v2.1 (beta)]\n"
        "; a comment\n"
        "Filename:M70|Sector size:2352|Sector count:820|First sector offset:0\n"
        "#:0|ID:?[0]|Sectors:0-811|Type:Video|Dimensions:320x240|Frame Count:82|"
        "Sectors/Frame:10/1|Disc Speed:2\n"
        "#:1|ID:?[0.0]|Sectors:7-815|Type:XA|File:1|Channel:7\n"
    )
    items = parse_index(index)
    assert [item.number for item in items] == [0, 1]
    assert items[0].type == "Video"
    assert items[0].fields["Frame Count"] == "82"
    assert items[0].fields["Sectors/Frame"] == "10/1"


def test_a_container_whose_frame_count_ffprobe_cannot_read_is_refused(tmp_path: Path) -> None:
    """`nb_frames=N/A` must refuse, not raise: a traceback ends the whole batch.

    `main_movies` catches `MovieError`, nothing else, so an unhandled `ValueError` here
    leaves every movie after this one in the run undecoded and exits with a stack trace
    instead of a sentence.
    """
    # Matroska records no frame count, so ffprobe answers `N/A` rather than a number.
    unknown = _ffmpeg(tmp_path / "unknown.mkv", ONE_SECOND_VIDEO + ONE_SECOND_AUDIO)
    if (ffprobe_streams(unknown)[0].get("nb_frames") or "").isdigit():
        pytest.skip("this ffmpeg records a frame count in .mkv, so the case cannot be built")

    with pytest.raises(MovieError) as refusal:
        verify_output(unknown, 15)
    assert "nb_frames" in str(refusal.value)


def test_a_decode_that_lost_the_narration_is_refused(tmp_path: Path) -> None:
    """A silent movie is a failed decode: the narration is the reason for watching these.

    ffmpeg writes the fixture, so the file under test is a real container, not a mock --
    and the video-only case is the one a `-noaud` slip or a muxing failure produces.
    """
    silent = _ffmpeg(tmp_path / "silent.avi", ONE_SECOND_VIDEO)

    with pytest.raises(MovieError) as refusal:
        verify_output(silent, 15)
    assert "no audio stream" in str(refusal.value)


def test_a_decode_that_stopped_early_is_refused(tmp_path: Path) -> None:
    """Fewer frames than the extent has slots is a truncated movie, and it looks fine in VLC."""
    short = _ffmpeg(tmp_path / "short.avi", ONE_SECOND_VIDEO + ONE_SECOND_AUDIO)

    verify_output(short, 15)  # the same file, at a length it does reach
    with pytest.raises(MovieError) as refusal:
        verify_output(short, 1000)
    assert "fewer than the 1000 frame slots" in str(refusal.value)


ONE_SECOND_VIDEO = ["-f", "lavfi", "-i", "testsrc=size=64x48:rate=15:duration=1"]
ONE_SECOND_AUDIO = ["-f", "lavfi", "-i", "sine=frequency=440:duration=1"]


def _ffmpeg(out: Path, inputs: list[str]) -> Path:
    """Build a real container to test against, rather than mocking ffprobe."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("no ffmpeg on this machine to synthesise a container with")
    subprocess.run(
        [ffmpeg, "-v", "error", "-y", *inputs, "-c:v", "mjpeg", "-c:a", "pcm_s16le", str(out)],
        check=True,
        capture_output=True,
    )
    return out


# --- the decode, with a stand-in for jPSXdec -------------------------------------------------


@pytest.fixture
def one_whole_movie(tmp_path: Path) -> Path:
    """An image holding one `.IKI` of exactly one frame slot, so `frames` is well defined."""
    tree = [
        synth.Directory(
            "__STR",
            [synth.File("M00.IKI", _movie_content(0xC0, 10), form=1, interleaved=True)],
        )
    ]
    path = tmp_path / "one.img"
    path.write_bytes(synth.build_image(tree))
    return path


def test_a_decode_that_fails_its_check_leaves_no_file_behind(
    tmp_path: Path, one_whole_movie: Path
) -> None:
    """The file must never reach work/movies/ unverified.

    If it did, the next `./make.sh movies` would report it as "already there", `write_tsv`
    would run, the command would exit 0, and a truncated or silent movie would be
    indistinguishable from a good one -- while being the thing Jay annotates from. jPSXdec
    is stood in for by a script that produces a *silent* AVI, which is what a muxing
    failure looks like.
    """
    out_dir = tmp_path / "out"
    silent = _ffmpeg(tmp_path / "silent.avi", ONE_SECOND_VIDEO)
    fake_java = _fake_jpsxdec(tmp_path, avi=silent, frames=1)

    with DiscImage(one_whole_movie) as image:
        movie = iki_entries(image)[0]
        with pytest.raises(MovieError) as refusal:
            decode_one(
                image,
                movie,
                out_dir,
                java=str(fake_java),
                jar=fake_java,
                scratch=tmp_path / "scratch",
            )

    assert "no audio stream" in str(refusal.value)
    assert not (out_dir / "M00.avi").exists(), "a movie that failed its check was published"


def test_an_output_already_there_is_checked_before_it_is_trusted(
    tmp_path: Path, one_whole_movie: Path
) -> None:
    """The other half: a bad file that is already in place must not be skipped past."""
    out = _ffmpeg(tmp_path / "M00.avi", ONE_SECOND_VIDEO)
    with DiscImage(one_whole_movie) as image:
        movie = iki_entries(image)[0]

    with pytest.raises(MovieError) as refusal:
        may_skip(out, movie, force=False)
    assert "no audio stream" in str(refusal.value)
    assert not may_skip(tmp_path / "absent.avi", movie, force=False)


def _fake_jpsxdec(tmp_path: Path, *, avi: Path, frames: int) -> Path:
    """A stand-in for `java -jar jpsxdec.jar`: writes an index, then copies `avi` as output.

    It is passed as both the java binary and the jar, which the real invocations tolerate
    because the jar path is only ever an argument to the binary.
    """
    index_line = (
        f"#:0|ID:?[0]|Sectors:0-9|Type:Video|Dimensions:320x240|Frame Count:{frames}|"
        f"Sectors/Frame:10/1|Disc Speed:2"
    )
    script = tmp_path / "fake-jpsxdec"
    script.write_text(
        "#!/bin/sh\n"
        'case " $* " in\n'
        f"  *' -f '*) printf '%s\\n' '{index_line}' > \"$6\" ;;\n"
        f"  *) cp '{avi}' \"M00[0].avi\" ;;\n"
        "esac\n"
    )
    script.chmod(0o755)
    return script


# --- the two escape hatches the refusals promise --------------------------------------------------


def test_the_java_environment_variable_is_what_the_refusal_says_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`$BOKU_JAVA` has to be read, not just named: the message sends people to it.

    A machine whose only JDK is somewhere else has no other way in, and a variable that
    is documented and ignored costs that person the run they were told would work.
    """
    fake = tmp_path / "my-java"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setenv("BOKU_JAVA", str(fake))
    assert java_binary() == str(fake)

    monkeypatch.setenv("BOKU_JAVA", str(tmp_path / "not-there"))
    with pytest.raises(MovieError) as refusal:
        java_binary()
    assert "BOKU_JAVA" in str(refusal.value)


def test_the_jpsxdec_environment_variable_is_what_the_refusal_says_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jar = tmp_path / "jpsxdec.jar"
    jar.write_bytes(b"PK\x03\x04")
    monkeypatch.setenv("BOKU_JPSXDEC_JAR", str(jar))
    assert jpsxdec_jar() == jar
