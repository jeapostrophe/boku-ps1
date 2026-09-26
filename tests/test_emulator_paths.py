"""Where the emulator verbs find Beetle PSX and the BIOS when no variable says (PLAN `ENV-09`).

A fake retro-trainer checkout under `tmp_path` stands in for `~/Dev/retro-trainer`; its layout
is built from `emulator_paths`' own relative paths, and the default checkout is pinned to the
one `boku.mode_one` already names, so the two cannot drift apart unseen.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from boku import REPO_ROOT, mode_one

LIBRETRO = REPO_ROOT / "tools" / "libretro"
SCRIPT = LIBRETRO / "emulator_paths.py"
VARS = ("BOKU_LIBRETRO_CORE", "BOKU_LIBRETRO_SYSTEM", "REDUX_BIOS", "BOKU_MODE_ONE")


def _load(name: str):
    sys.path.insert(0, str(LIBRETRO))
    try:
        spec = importlib.util.spec_from_file_location(f"{name}_under_test", LIBRETRO / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(LIBRETRO))


paths = _load("emulator_paths")
run_core = _load("run_core")


def fake_retro_trainer(root: Path) -> Path:
    """A checkout holding a core file and a system directory with the BIOS in it."""
    (root / paths.CORE_UNDER).parent.mkdir(parents=True)
    (root / paths.CORE_UNDER).write_bytes(b"not really a dylib")
    (root / paths.SYSTEM_UNDER).mkdir(parents=True)
    (root / paths.SYSTEM_UNDER / paths.BIOS_NAME).write_bytes(b"not really a BIOS")
    return root


def test_the_default_checkout_is_the_one_mode_one_names():
    assert Path.home() / paths.DEFAULT_MODE_ONE_UNDER_HOME == mode_one.DEFAULT_MODE_ONE
    assert paths.MODE_ONE_ENV == mode_one.MODE_ONE_ENV


def test_unset_variables_fall_back_to_the_retro_trainer_checkout_under_home(tmp_path):
    home = tmp_path / "home"
    root = fake_retro_trainer(home / paths.DEFAULT_MODE_ONE_UNDER_HOME)
    env = {"HOME": str(home)}
    assert paths.core(env) == root / paths.CORE_UNDER
    assert paths.system(env) == root / paths.SYSTEM_UNDER
    assert paths.bios(env) == root / paths.SYSTEM_UNDER / paths.BIOS_NAME


def test_mode_one_variable_moves_the_checkout(tmp_path):
    root = fake_retro_trainer(tmp_path / "elsewhere")
    env = {"HOME": str(tmp_path / "empty-home"), "BOKU_MODE_ONE": str(root)}
    assert paths.core(env) == root / paths.CORE_UNDER
    assert paths.system(env) == root / paths.SYSTEM_UNDER


def test_a_set_variable_wins_over_a_present_default(tmp_path):
    home = tmp_path / "home"
    fake_retro_trainer(home / paths.DEFAULT_MODE_ONE_UNDER_HOME)
    mine = fake_retro_trainer(tmp_path / "mine")
    env = {
        "HOME": str(home),
        "BOKU_LIBRETRO_CORE": str(mine / paths.CORE_UNDER),
        "BOKU_LIBRETRO_SYSTEM": str(mine / paths.SYSTEM_UNDER),
    }
    assert paths.core(env) == mine / paths.CORE_UNDER
    assert paths.system(env) == mine / paths.SYSTEM_UNDER
    # The Redux BIOS follows the system directory that was chosen...
    assert paths.bios(env) == mine / paths.SYSTEM_UNDER / paths.BIOS_NAME
    # ...unless it is named itself.
    named = tmp_path / "my-bios.bin"
    named.write_bytes(b"")
    assert paths.bios(env | {"REDUX_BIOS": str(named)}) == named


@pytest.mark.parametrize(
    "resolve,var",
    [("core", "BOKU_LIBRETRO_CORE"), ("system", "BOKU_LIBRETRO_SYSTEM"), ("bios", "REDUX_BIOS")],
)
def test_nothing_anywhere_says_what_to_set_and_where_the_setup_is(tmp_path, resolve, var):
    home = tmp_path / "home"
    looked = home / paths.DEFAULT_MODE_ONE_UNDER_HOME
    with pytest.raises(paths.NotFound) as caught:
        getattr(paths, resolve)({"HOME": str(home)})
    message = str(caught.value)
    assert var in message
    assert "BOKU_MODE_ONE" in message
    assert str(looked) in message
    assert "research/tooling-setup.md § " in message
    section = message.split("research/tooling-setup.md § ", 1)[1].strip('"')
    assert f"\n## {section}\n" in (REPO_ROOT / "research/tooling-setup.md").read_text()


def test_a_set_variable_naming_nothing_is_an_error_not_a_fallback(tmp_path):
    home = tmp_path / "home"
    fake_retro_trainer(home / paths.DEFAULT_MODE_ONE_UNDER_HOME)
    wrong = tmp_path / "typo.dylib"
    with pytest.raises(paths.NotFound, match=f"BOKU_LIBRETRO_CORE={wrong}"):
        paths.core({"HOME": str(home), "BOKU_LIBRETRO_CORE": str(wrong)})


def test_a_mistyped_system_directory_does_not_hand_redux_retro_trainers_bios(tmp_path):
    home = tmp_path / "home"
    fake_retro_trainer(home / paths.DEFAULT_MODE_ONE_UNDER_HOME)
    typo = tmp_path / "typo"
    with pytest.raises(paths.NotFound, match=f"BOKU_LIBRETRO_SYSTEM={typo}"):
        paths.bios({"HOME": str(home), "BOKU_LIBRETRO_SYSTEM": str(typo)})


def test_a_named_system_directory_without_the_bios_says_to_put_it_there(tmp_path):
    mine = tmp_path / "mine"
    mine.mkdir()
    with pytest.raises(paths.NotFound) as caught:
        paths.bios({"HOME": str(tmp_path / "home"), "BOKU_LIBRETRO_SYSTEM": str(mine)})
    # BOKU_MODE_ONE would change nothing here: the named system directory wins over it.
    assert "BOKU_MODE_ONE" not in str(caught.value)
    assert str(mine / paths.BIOS_NAME) in str(caught.value)


# --- run_core, the tool Jay's `./make.sh duckstation-cards` stopped in ----------------------


def resolve_args(tmp_path: Path, core=None, system=None):
    content = tmp_path / "image.cue"
    content.write_text("")
    return types.SimpleNamespace(core=core, system=system, content=content)


def test_run_core_finds_the_default_core_with_no_variable_set(tmp_path, monkeypatch):
    for var in VARS:
        monkeypatch.delenv(var, raising=False)
    home = tmp_path / "home"
    root = fake_retro_trainer(home / paths.DEFAULT_MODE_ONE_UNDER_HOME)
    monkeypatch.setenv("HOME", str(home))
    core, system, _ = run_core.resolve_paths(resolve_args(tmp_path))
    assert (core, system) == (root / paths.CORE_UNDER, root / paths.SYSTEM_UNDER)


def test_run_core_says_what_to_install_when_there_is_no_core(tmp_path, monkeypatch):
    for var in VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    with pytest.raises(run_core.UsageError) as caught:
        run_core.resolve_paths(resolve_args(tmp_path))
    assert "research/tooling-setup.md" in str(caught.value)
    assert "--core" in str(caught.value)


def test_run_core_explicit_core_wins_over_the_variable_and_the_default(tmp_path, monkeypatch):
    home = tmp_path / "home"
    fake_retro_trainer(home / paths.DEFAULT_MODE_ONE_UNDER_HOME)
    via_env = fake_retro_trainer(tmp_path / "env")
    explicit = fake_retro_trainer(tmp_path / "explicit")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("BOKU_LIBRETRO_CORE", str(via_env / paths.CORE_UNDER))
    monkeypatch.setenv("BOKU_LIBRETRO_SYSTEM", str(via_env / paths.SYSTEM_UNDER))
    args = resolve_args(tmp_path, explicit / paths.CORE_UNDER, explicit / paths.SYSTEM_UNDER)
    core, system, _ = run_core.resolve_paths(args)
    assert (core, system) == (explicit / paths.CORE_UNDER, explicit / paths.SYSTEM_UNDER)
    # and with no flag, the variable beats the default
    core, system, _ = run_core.resolve_paths(resolve_args(tmp_path))
    assert (core, system) == (via_env / paths.CORE_UNDER, via_env / paths.SYSTEM_UNDER)


# --- the shell side: what make.sh evaluates before an emulator verb -------------------------


def shell(script: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    clean = {k: v for k, v in os.environ.items() if k not in VARS} | env
    return subprocess.run(
        ["bash", "-c", script], env=clean, capture_output=True, text=True, cwd=REPO_ROOT
    )


def test_exports_fill_every_unset_variable_a_shell_script_reads(tmp_path):
    home = tmp_path / "home"
    root = fake_retro_trainer(home / paths.DEFAULT_MODE_ONE_UNDER_HOME)
    done = shell(
        f'eval "$({sys.executable} {SCRIPT} --exports)"; '
        'printf "%s\\n" "$BOKU_LIBRETRO_CORE" "$BOKU_LIBRETRO_SYSTEM" "$REDUX_BIOS"',
        {"HOME": str(home)},
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == [
        str(root / paths.CORE_UNDER),
        str(root / paths.SYSTEM_UNDER),
        str(root / paths.SYSTEM_UNDER / paths.BIOS_NAME),
    ]


def test_exports_leave_a_variable_alone_when_nothing_is_found(tmp_path):
    done = shell(
        f'eval "$({sys.executable} {SCRIPT} --exports)"; echo "[${{BOKU_LIBRETRO_CORE-unset}}]"',
        {"HOME": str(tmp_path / "home")},
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout == "[unset]\n"


def test_check_prints_the_path_or_the_message(tmp_path):
    home = tmp_path / "home"
    missing = shell(f"{sys.executable} {SCRIPT} --check core", {"HOME": str(home)})
    assert missing.returncode == 127
    assert "research/tooling-setup.md" in missing.stderr
    root = fake_retro_trainer(home / paths.DEFAULT_MODE_ONE_UNDER_HOME)
    ok = shell(f"{sys.executable} {SCRIPT} --check core", {"HOME": str(home)})
    assert ok.returncode == 0, ok.stderr
    assert ok.stdout.strip() == str(root / paths.CORE_UNDER)
