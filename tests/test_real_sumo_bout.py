"""`ENV-08` on Beetle PSX: a generated cage enters a bug-sumo bout, and the fighter the game builds
from its record is the one `boku.sumo` predicts.

`boku save --bug` writes the card from the new-game base `./make.sh saves` dumps;
`tools/libretro/sumo_bout.py` drives it to the bout and compares the game's fighter with
`boku.sumo`'s prediction -- that tool's exit code is the assertion here.

Skips without the import, the new-game base, the Beetle core and BIOS, and unless
`BOKU_EMU_TESTS=1`: a run is ~40 s.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku import save as S

BASE = REPO_ROOT / "work" / "saves" / "newgame.ram"
BOUT = REPO_ROOT / "tools" / "libretro" / "sumo_bout.py"


def _card(disc_dir: Path, tmp_path: Path, name: str, edits: list[str]) -> Path:
    """A card from `boku save` over the new-game base: the corpus's `name` with `--corpus`,
    else one card called `name` with these edits. Skips without Beetle or the base."""
    for var in ("BOKU_LIBRETRO_CORE", "BOKU_LIBRETRO_SYSTEM"):
        if not os.environ.get(var):
            pytest.skip(f"{var} is not set (research/tooling-setup.md § Beetle PSX, headless)")
    if not BASE.is_file():
        pytest.skip(f"no {BASE}: `./make.sh saves` dumps it")
    corpus = "--corpus" in edits
    card = tmp_path / "corpus" / f"{name}.mcd" if corpus else tmp_path / f"{name}.mcd"
    made = subprocess.run(
        [sys.executable, "-m", "boku", "save", "--base", str(BASE), *edits,
         "--out", str(card.parent if corpus else card), "--disc", str(disc_dir)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )  # fmt: skip
    assert made.returncode == 0 and card.is_file(), made.stdout + made.stderr
    return card


@pytest.mark.skipif(os.environ.get("BOKU_EMU_TESTS") != "1", reason="set BOKU_EMU_TESTS=1")
@pytest.mark.parametrize("bug", [None, "saw:40"])
def test_a_generated_cage_fights_with_the_predicted_stats(disc_dir: Path, tmp_path: Path, bug):
    """The corpus's sumo save (a maxed bug: above its typical size, trained) and a small bug,
    below its typical size."""
    if bug is None:
        card = _card(disc_dir, tmp_path, "sumo-maxed-cage", ["--corpus"])
    else:
        flags = [a for n, v in S.SUMO_FLAGS for a in ("--flag", f"{n}={v}")]
        card = _card(disc_dir, tmp_path, "sumo", ["--day", str(S.SUMO_DAY), *flags, "--bug", bug])
    fought = subprocess.run(
        [sys.executable, str(BOUT), str(card), "--work", str(tmp_path / "bout"),
         "--disc", str(disc_dir)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=900,
    )  # fmt: skip
    assert fought.returncode == 0, fought.stdout + fought.stderr


@pytest.mark.skipif(os.environ.get("BOKU_EMU_TESTS") != "1", reason="set BOKU_EMU_TESTS=1")
def test_the_mantis_save_wins_the_mantis_and_reaches_the_shortcut(disc_dir: Path, tmp_path):
    card = _card(disc_dir, tmp_path, "sumo-mantis-ready", ["--corpus"])
    fought = subprocess.run(
        [sys.executable, str(BOUT), str(card), "--mantis", "--work", str(tmp_path / "bout"),
         "--disc", str(disc_dir)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=900,
    )  # fmt: skip
    assert fought.returncode == 0, fought.stdout + fought.stderr
    assert "g_flags[69] = 1" in fought.stdout, fought.stdout
    assert "g_flags[70] = 1" in fought.stdout and "E02" in fought.stdout


@pytest.mark.skipif(os.environ.get("BOKU_EMU_TESTS") != "1", reason="set BOKU_EMU_TESTS=1")
def test_the_second_look_into_the_shortcut_well_plays_the_narrators_line(disc_dir: Path, tmp_path):
    """The well on the shortcut (`E08`, `E2405`): the first ○ shows its close-up, the second the
    narrator -- the clip the game plays must be the disc's key of `E2405.0`."""
    card = _card(disc_dir, tmp_path, "shortcut-open", ["--corpus"])
    looked = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "libretro" / "examine.py"), str(card), "E08",
         "2405", "--work", str(tmp_path / "well"), "--disc", str(disc_dir)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=900,
    )  # fmt: skip
    assert looked.returncode == 0, looked.stdout + looked.stderr
    assert "voices E2405.0" in looked.stdout, looked.stdout
