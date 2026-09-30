"""`tools/libretro/` is scripts, not a package (`boku/` is the only one), so a test loads one
by path, as it runs: with its own directory on `sys.path` for the modules beside it."""

from __future__ import annotations

import importlib.util
import sys
from functools import cache
from types import ModuleType

from boku import REPO_ROOT

LIBRETRO = REPO_ROOT / "tools" / "libretro"


@cache
def libretro_tool(name: str) -> ModuleType:
    if str(LIBRETRO) not in sys.path:
        sys.path.insert(0, str(LIBRETRO))
    spec = importlib.util.spec_from_file_location(name, LIBRETRO / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
