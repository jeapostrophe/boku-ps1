"""`tools/vwf/state_poke.py`'s stack mark: the stack is what grows down from the top."""

from __future__ import annotations

import importlib.util
import sys

from boku import REPO_ROOT


def state_poke():
    path = REPO_ROOT / "tools" / "vwf" / "state_poke.py"
    spec = importlib.util.spec_from_file_location("state_poke", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_stack_mark_ignores_a_buffer_written_far_below_the_frames():
    """The item menu's shape: a buffer at the fill's floor and the frames far above it."""
    tool = state_poke()
    changed = [False] * 10_000
    for i in range(0, 2_000):
        changed[i] = True  # a buffer at the floor
    for i in (9_000, 9_004, 9_100, 9_600, 9_999):
        changed[i] = True  # frames: sparse, but never far apart
    assert tool.stack_mark(changed, gap=512) == 9_000
    assert tool.stack_mark(changed, gap=8_000) == 0, "a gap wider than the hole joins them"
    assert tool.stack_mark([False] * 10, gap=512) is None
