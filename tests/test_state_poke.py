"""`tools/vwf/state_poke.py --scan`: the stack's low-water mark in a sentinel fill."""

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


def test_a_deep_frame_s_unwritten_middle_does_not_hide_its_bottom(tmp_path, capsys):
    """The item menu's shape: one 0x3CA8-byte frame whose locals are written only at its
    bottom (here from the `sp` Redux saw under it), its saved registers at its top,
    thousands of untouched bytes between. The low-water mark is the bottom, not the top."""
    tool = state_poke()
    low, high, sentinel = 0x801F0000, 0x801FFFF0, 0xEE
    data = bytearray(tool.RAM_OFFSET + tool.RAM_SIZE)
    fill = tool.ram_offset(low, high - low)
    data[fill : fill + high - low] = bytes([sentinel]) * (high - low)
    bottom = 0x801FC288
    for address in (*range(bottom, bottom + 0x2000), *range(0x801FFF20, high)):
        data[tool.ram_offset(address)] = 0
    state = tmp_path / "s.state"
    state.write_bytes(bytes(data))
    tool.main([str(state), "--scan", hex(low), hex(high), hex(sentinel)])
    assert f"stack: low-water 0x{bottom:08X}" in capsys.readouterr().out
