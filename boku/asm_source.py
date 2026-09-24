"""Values read from the armips source in `asm/`, for the Python that must agree with it.

A test or tool that needs a number the assembly defines reads it here rather than retyping
it, so the two cannot drift apart (a hand-typed copy passes exactly when both drift).
"""

from __future__ import annotations

import re

from boku import REPO_ROOT

ASM_DIR = REPO_ROOT / "asm"


def asm_equate(name: str, source: str) -> int:
    """`name`'s literal value where `asm/<source>` defines it (`NAME equ 0x1234`)."""
    text = (ASM_DIR / source).read_text(encoding="utf-8")
    found = re.search(rf"^{re.escape(name)}\s+equ\s+(0[xX][0-9A-Fa-f]+|\d+)\b", text, re.M)
    if found is None:
        raise KeyError(f"asm/{source} defines no literal equate {name}")
    return int(found[1], 0)
