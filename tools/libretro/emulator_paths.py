#!/usr/bin/env python3
"""Where the emulator verbs find Beetle PSX's core, its BIOS directory and PCSX-Redux's BIOS.

Each is named by a variable -- `BOKU_LIBRETRO_CORE`, `BOKU_LIBRETRO_SYSTEM`, `REDUX_BIOS` --
and when that is unset, found in a retro-trainer checkout (Mode One's, `$BOKU_MODE_ONE`, else
`~/Dev/retro-trainer`) under `config/`, which is where this machine keeps them
(`research/tooling-setup.md` § "Beetle PSX, as it stands on this machine"). Redux's BIOS
defaults to `scph5500.bin` in whichever system directory was chosen. A variable that is set
always wins, and one naming nothing is an error rather than a reason to look elsewhere.

    tools/libretro/emulator_paths.py --exports      # `export VAR=...` for each one found
    tools/libretro/emulator_paths.py --check core   # its path, or what to install; exit 127

`run_core.py` and `field.py` call `core()` and `system()`; `smoke.sh` and `run-headless.sh` use
`--check`; `./make.sh test` / `emu-test` evaluate `--exports`, because the tests read the
variables. Standard library only, like `run_core.py`.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shlex
import sys
from collections.abc import Mapping
from pathlib import Path

CORE_ENV, SYSTEM_ENV, BIOS_ENV = "BOKU_LIBRETRO_CORE", "BOKU_LIBRETRO_SYSTEM", "REDUX_BIOS"
# boku/mode_one.py's variable and default (a test pins that they agree); not imported,
# because this file is standard library only.
MODE_ONE_ENV = "BOKU_MODE_ONE"
DEFAULT_MODE_ONE_UNDER_HOME = Path("Dev/retro-trainer")

_SUFFIX = {"darwin": ".dylib", "win32": ".dll"}.get(sys.platform, ".so")
CORE_UNDER = Path("config/cores") / f"mednafen_psx_libretro{_SUFFIX}"
SYSTEM_UNDER = Path("config/system")
BIOS_NAME = "scph5500.bin"
"""The retail Japanese BIOS: SCPS-10088 is NTSC-J (research/tooling-setup.md § "The BIOS
question")."""

SETUP = 'research/tooling-setup.md § "Where the emulator verbs find the core and the BIOS"'


class NotFound(Exception):
    """A set variable names nothing, or none is set and the default is absent; the message says
    what to install or set."""


def retro_trainer(env: Mapping[str, str]) -> Path:
    named = env.get(MODE_ONE_ENV)
    if named:
        return Path(named).expanduser()
    return Path(env.get("HOME") or Path.home()) / DEFAULT_MODE_ONE_UNDER_HOME


_OR_MODE_ONE = f"or {MODE_ONE_ENV} to a retro-trainer checkout that has one"


def _resolve(
    env: Mapping[str, str], var: str, default, exists, what: str, instead: str = _OR_MODE_ONE
) -> Path:
    """`env[var]` if set (it must exist), else `default()` if that exists; `instead` is the
    other way to supply it, for the message."""
    named = env.get(var)
    if named:
        path = Path(named).expanduser()
        if not exists(path):
            raise NotFound(f"{var}={path} does not exist -- {SETUP}")
        return path
    path = default()
    if exists(path):
        return path
    raise NotFound(
        f"no {what}: {var} is not set and {path} does not exist. Set {var} ({instead}) -- {SETUP}"
    )


def core(env: Mapping[str, str] = os.environ) -> Path:
    """The Beetle PSX (mednafen_psx) libretro core."""
    return _resolve(
        env, CORE_ENV, lambda: retro_trainer(env) / CORE_UNDER, Path.is_file,
        f"Beetle PSX core ({CORE_UNDER.name}, a build of libretro/beetle-psx-libretro)",
    )  # fmt: skip


def system(env: Mapping[str, str] = os.environ) -> Path:
    """The libretro system directory, which holds the BIOS Beetle boots."""
    return _resolve(
        env, SYSTEM_ENV, lambda: retro_trainer(env) / SYSTEM_UNDER, Path.is_dir,
        f"libretro system directory (the one holding {BIOS_NAME}, the retail Japanese BIOS "
        "dumped from your console)",
    )  # fmt: skip


def bios(env: Mapping[str, str] = os.environ) -> Path:
    """PCSX-Redux's BIOS file: `scph5500.bin` in the system directory unless named. A named
    system directory is the only place looked, and a mistyped one is an error here too."""
    what = f"BIOS for PCSX-Redux ({BIOS_NAME}, the retail Japanese BIOS dumped from your console)"
    if env.get(SYSTEM_ENV):
        instead = f"or put {BIOS_NAME} in {SYSTEM_ENV}"
        return _resolve(env, BIOS_ENV, lambda: system(env) / BIOS_NAME, Path.is_file, what, instead)
    return _resolve(
        env, BIOS_ENV, lambda: retro_trainer(env) / SYSTEM_UNDER / BIOS_NAME, Path.is_file, what
    )


RESOLVERS = {"core": (CORE_ENV, core), "system": (SYSTEM_ENV, system), "bios": (BIOS_ENV, bios)}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    how = p.add_mutually_exclusive_group(required=True)
    how.add_argument(
        "--exports",
        action="store_true",
        help="print an `export` line for each one found; say nothing of the rest",
    )
    how.add_argument("--check", choices=RESOLVERS, help="print its path, or why not and exit 127")
    args = p.parse_args(argv)
    if args.check:
        try:
            print(RESOLVERS[args.check][1]())
        except NotFound as exc:
            print(exc, file=sys.stderr)
            return 127
        return 0
    for var, resolve in RESOLVERS.values():
        with contextlib.suppress(NotFound):
            print(f"export {var}={shlex.quote(str(resolve()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
