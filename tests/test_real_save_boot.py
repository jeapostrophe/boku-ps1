"""`ENV-06` on Beetle PSX: a generated save loads and wakes on the morning it names.

`boku save` writes a card from the new-game base `./make.sh saves` dumps, and
`tools/libretro/boot_save.py` boots it; that tool's clock gate is the assertion here.

Skips without the import, the new-game base (`./make.sh saves`), the Beetle core and BIOS, and
unless `BOKU_EMU_TESTS=1`: a boot is ~20 s.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from boku import REPO_ROOT

BASE = REPO_ROOT / "work" / "saves" / "newgame.ram"
BOOT = REPO_ROOT / "tools" / "libretro" / "boot_save.py"


@pytest.mark.skipif(os.environ.get("BOKU_EMU_TESTS") != "1", reason="set BOKU_EMU_TESTS=1")
def test_a_generated_day_five_save_wakes_on_august_five(disc_dir: Path, tmp_path: Path):
    for var in ("BOKU_LIBRETRO_CORE", "BOKU_LIBRETRO_SYSTEM"):
        if not os.environ.get(var):
            pytest.skip(f"{var} is not set (research/tooling-setup.md § Beetle PSX, headless)")
    if not BASE.is_file():
        pytest.skip(f"no {BASE}: `./make.sh saves` dumps it")
    card = tmp_path / "day05.mcd"
    made = subprocess.run(
        [sys.executable, "-m", "boku", "save", "--base", str(BASE), "--day", "5",
         "--out", str(card), "--disc", str(disc_dir)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )  # fmt: skip
    assert made.returncode == 0, made.stdout + made.stderr
    booted = subprocess.run(
        [sys.executable, str(BOOT), str(card), "--work", str(tmp_path / "boot"),
         "--disc", str(disc_dir)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=600,
    )  # fmt: skip
    assert booted.returncode == 0, booted.stdout + booted.stderr
    assert "August 5 07:00" in booted.stdout
