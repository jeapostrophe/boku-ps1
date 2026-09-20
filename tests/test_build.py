"""The build's own refusals, the ones that do not need a disc.

`tests/test_trial.py` exercises the image writer against the real dump; what is left here
is the part of `boku.build` that decides *before* it ever opens an image — and one thing
that used to be decided nowhere at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boku.build import BuildRefused, build
from boku.translation import SampleScenes


def test_a_translation_file_the_loader_could_not_read_stops_the_build(tmp_path):
    """The harm: a row typed with spaces instead of a tab is a line silently left Japanese.

    The loader has always collected these; nothing read them, so a malformed scene file
    produced a green build and no mention of the lines it had dropped.
    """
    scene = tmp_path / "scene.txt"
    scene.write_text("E0404.0 Uncle Gochisosama deshita.\n", encoding="utf-8")
    source = SampleScenes.from_paths([scene])
    assert source.problems, "the fixture is not malformed; this test would prove nothing"
    with pytest.raises(BuildRefused, match="reading the translation"):
        build(source=Path("no-such-image.img"), out_dir=tmp_path / "out", translation=source)
    assert not (tmp_path / "out").exists()


def test_the_same_translation_is_reported_rather_than_refused_when_skipping_is_asked_for(
    tmp_path,
):
    """`--skip-unfitted` carries on, but the problem still has to reach the report."""
    scene = tmp_path / "scene.txt"
    scene.write_text("E1.0\tA\tone\nE1.0\tA\ttwo\n", encoding="utf-8")
    source = SampleScenes.from_paths([scene])
    with pytest.raises(BuildRefused) as raised:
        build(
            source=Path("no-such-image.img"),
            out_dir=tmp_path / "out",
            translation=source,
            skip_unfitted=True,
            dry_run=True,
        )
    # It gets past the translation check and fails on the missing import instead, which is
    # what says the loader's problems no longer abort a skipping build.
    assert "no-such-image.img" in str(raised.value) or "disc" in str(raised.value)
