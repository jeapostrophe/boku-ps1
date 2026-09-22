"""`research/data/movies.tsv` against the disc it was generated from. Skips without one.

The tracked table's derived columns are the gate: `./make.sh movies` regenerates them
every run, so a note edit that nobody re-ran, or a disc whose extents are not what § 1
says, has to show up here rather than in a list Jay is annotating from.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from boku.disc import DiscImage
from boku.movies import (
    MOVIES_MD,
    MOVIES_TSV,
    SECTORS_PER_FRAME,
    iki_entries,
    main_movies,
    parse_movie_ids,
)


def test_tracked_movies_tsv_is_what_this_image_and_the_notes_generate(
    real_image: Path, tmp_path: Path
) -> None:
    """Regenerate it beside the tracked copy and diff, byte for byte.

    The tracked file is copied in first, because the hand-written columns are carried
    across a regeneration and would otherwise come back blank -- which would make this
    test fail for a reason that is not drift.
    """
    out = tmp_path / MOVIES_TSV.name
    shutil.copyfile(MOVIES_TSV, out)

    status = main_movies(
        real_image, tmp_path / "unused", tsv_only=True, tsv_path=out, force=False, only=None
    )

    assert status == 0
    assert out.read_text(encoding="utf-8") == MOVIES_TSV.read_text(encoding="utf-8"), (
        f"{MOVIES_TSV.name} is not what the image and research/movies.md generate today: "
        f"run `./make.sh movies --tsv`"
    )


def test_every_movie_extent_is_a_whole_number_of_frame_slots(real_image: Path) -> None:
    """The arithmetic the `frames` column rests on, on every .IKI the disc holds.

    Asserted on `sectors` and not on `frames`, which raises rather than returning a wrong
    number -- an assertion downstream of that refusal can never be red. `decode_one`
    re-checks each file against jPSXdec's own count; this is the half that needs no Java.
    """
    with DiscImage(real_image) as image:
        movies = iki_entries(image)
        for movie in movies:
            assert movie.sectors % SECTORS_PER_FRAME == 0, (
                f"{movie.path} spans {movie.sectors} sectors, not whole frame slots"
            )
    assert len(movies) == len(
        {entry.file for entry in parse_movie_ids(MOVIES_MD.read_text(encoding="utf-8"))}
    ), "the disc holds a different set of .IKI files than research/movies.md section 1 names"
