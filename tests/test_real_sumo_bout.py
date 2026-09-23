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


@pytest.mark.skipif(os.environ.get("BOKU_EMU_TESTS") != "1", reason="set BOKU_EMU_TESTS=1")
@pytest.mark.parametrize("bug", [None, "saw:40"])
def test_a_generated_cage_fights_with_the_predicted_stats(disc_dir: Path, tmp_path: Path, bug):
    """The corpus's sumo save (a maxed bug: above its typical size, trained) and a small bug,
    below its typical size."""
    for var in ("BOKU_LIBRETRO_CORE", "BOKU_LIBRETRO_SYSTEM"):
        if not os.environ.get(var):
            pytest.skip(f"{var} is not set (research/tooling-setup.md § Beetle PSX, headless)")
    if not BASE.is_file():
        pytest.skip(f"no {BASE}: `./make.sh saves` dumps it")
    if bug is None:
        card, edits = tmp_path / "corpus" / "sumo-maxed-cage.mcd", ["--corpus"]
        out = card.parent
    else:
        flags = [a for n, v in S.SUMO_FLAGS for a in ("--flag", f"{n}={v}")]
        card, edits = tmp_path / "sumo.mcd", ["--day", str(S.SUMO_DAY), *flags, "--bug", bug]
        out = card
    made = subprocess.run(
        [sys.executable, "-m", "boku", "save", "--base", str(BASE), *edits, "--out", str(out),
         "--disc", str(disc_dir)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )  # fmt: skip
    assert made.returncode == 0 and card.is_file(), made.stdout + made.stderr
    fought = subprocess.run(
        [sys.executable, str(BOUT), str(card), "--work", str(tmp_path / "bout"),
         "--disc", str(disc_dir)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=900,
    )  # fmt: skip
    assert fought.returncode == 0, fought.stdout + fought.stderr
