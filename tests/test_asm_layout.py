"""Every `.org` / `.area` site in `asm/*.asm` covers its own bytes and nobody else's.

The gate that could not catch the trap of round 3: a site placed by its own `.org` inside
another block's `.area` — both arms restate the stock word, so `ORIGINAL=1` reproduces the
retail file and stays green, while in the patch pass whichever block armips assembles last
silently wins. This reads the sources as text (macros expanded by substitution, `equ`
names and the build's `-equ` layout values evaluated) and asserts the intervals are
pairwise disjoint within each opened file. The parse is deliberately small: a construct it
cannot evaluate is a failure, not a skip, so a new way of writing a site has to be taught
here rather than slip past.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_vwf_prototype import REPO_ROOT, vwf_layout, vwf_prototype

ASM = REPO_ROOT / "asm"
ENTRY = ASM / "vwf.asm"

NAME = r"[A-Za-z_][A-Za-z0-9_]*"


def _build_equates() -> dict[str, int]:
    """What `build_prototype.run_armips` passes as `-equ`, with the build's defaults."""
    layout = vwf_layout()
    values = {name.upper(): getattr(layout, name) for name in layout.ARMIPS_EQUATES}
    values["TABLE_IDS"] = 812
    values["ORIGINAL"] = 0
    values.update(vwf_prototype().movie_equates(bytes(4 * 2048)))
    values.update(vwf_prototype().ROUTINES_EQUATES)
    return values


def _evaluate(expression: str, names: dict[str, int]) -> int:
    text = expression.strip()
    if not re.fullmatch(r"[\w\s()+\-*/]+", text):
        raise ValueError(f"cannot evaluate {expression!r}")
    for word in re.findall(NAME, re.sub(r"0[xX][0-9A-Fa-f]+", "0", text)):
        if word not in names:
            raise ValueError(f"{expression!r} uses {word!r}, which nothing defines")
    return int(eval(text, {"__builtins__": {}}, dict(names)))


def _expand(
    lines: list[tuple[int, str]], macros: dict[str, tuple[list[str], list[str]]]
) -> list[tuple[int, str]]:
    """Macro invocations replaced by their bodies with the arguments substituted; every
    expanded line keeps the invocation's line number, which is where the site is."""
    out: list[tuple[int, str]] = []
    for number, line in lines:
        stripped = line.strip()
        head = stripped.split(None, 1)
        if head and head[0] in macros:
            params, body = macros[head[0]]
            args = [a.strip() for a in head[1].split(",")] if len(head) > 1 else []
            if len(args) != len(params):
                raise ValueError(f"{head[0]} takes {len(params)} argument(s): {stripped!r}")
            for body_line in body:
                for param, arg in zip(params, args, strict=True):
                    body_line = re.sub(rf"\b{param}\b", f"({arg})", body_line)
                out.append((number, body_line))
        else:
            out.append((number, line))
    return out


def sites(entry: Path = ENTRY) -> list[tuple[str, int, int, str]]:
    """`(file image, start, end, where)` for every `.org` followed by `.area`."""
    names = _build_equates()
    macros: dict[str, tuple[list[str], list[str]]] = {}
    found: list[tuple[str, int, int, str]] = []

    def read(path: Path) -> list[tuple[int, str]]:
        lines: list[tuple[int, str]] = []
        current: tuple[str, list[str], list[str]] | None = None
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.split(";", 1)[0].rstrip()
            if match := re.match(rf"\s*\.macro\s+({NAME})\s*(?:,\s*(.*))?$", code):
                params = [p.strip() for p in match.group(2).split(",")] if match.group(2) else []
                current = (match.group(1), params, [])
                continue
            if re.match(r"\s*\.endmacro", code):
                assert current is not None, f"{path}: .endmacro without .macro"
                macros[current[0]] = (current[1], current[2])
                current = None
                continue
            if current is not None:
                current[2].append(code)
            else:
                lines.append((number, code))
        return lines

    def walk(path: Path, image: str) -> str:
        pending: tuple[int, str] | None = None
        for number, code in _expand(read(path), macros):
            where = f"{path.name}:{number}"
            if match := re.match(rf"\s*({NAME})\s+equ\s+(.*)$", code):
                names[match.group(1)] = _evaluate(match.group(2), names)
            elif match := re.match(r"\s*\.open\s+(\S+)\s*,", code):
                image = match.group(1).rstrip(",")
            elif match := re.match(r"\s*\.include\s+\"([^\"]+)\"", code):
                image = walk(path.parent / match.group(1), image)
            elif match := re.match(r"\s*\.org\s+(.*)$", code):
                pending = (_evaluate(match.group(1), names), where)
            elif match := re.match(r"\s*\.area\s+(.*)$", code):
                assert pending is not None, f"{where}: .area with no .org before it"
                start, at = pending
                found.append((image, start, start + _evaluate(match.group(1), names), at))
                pending = None
        return image

    walk(entry, "")
    return found


def overlaps(found: list[tuple[str, int, int, str]]) -> list[str]:
    """Human-readable pairs of sites that share a byte in the same file image."""
    out = []
    ordered = sorted(found)
    for index, (image, start, end, where) in enumerate(ordered):
        for other_image, other_start, other_end, other_where in ordered[index + 1 :]:
            if other_image != image or other_start >= end:
                break
            out.append(
                f"{where} [0x{start:08X}, 0x{end:08X}) overlaps "
                f"{other_where} [0x{other_start:08X}, 0x{other_end:08X}) in {image}"
            )
    return out


def test_every_patched_site_is_its_own_bytes():
    found = sites()
    assert len(found) > 20, f"only {len(found)} sites parsed; the parser lost the sources"
    assert overlaps(found) == []


def test_the_overlap_check_sees_a_site_inside_another_blocks_area(tmp_path):
    """Red on purpose: the round-3 shape, one word restated inside a six-word block."""
    (tmp_path / "vwf.asm").write_text(
        ".open EXE_PATH, 0x8000F800\n"
        ".org 0x8002EA34\n.area 6*4\n    nop\n.endarea\n"
        ".macro site, address\n.org address\n.area 4\n    nop\n.endarea\n.endmacro\n"
        "site 0x8002EA40\n"
        ".org 0x8002EB00\n.area 4\n    nop\n.endarea\n.close\n",
        encoding="utf-8",
    )
    found = sites(tmp_path / "vwf.asm")
    assert len(found) == 3
    assert overlaps(found) == [
        "vwf.asm:2 [0x8002EA34, 0x8002EA4C) overlaps vwf.asm:12 [0x8002EA40, 0x8002EA44) "
        "in EXE_PATH"
    ]


def test_a_site_the_parser_cannot_evaluate_is_a_failure_not_a_skip(tmp_path):
    (tmp_path / "vwf.asm").write_text(
        ".open EXE_PATH, 0x8000F800\n.org SOMEWHERE\n.area 4\n    nop\n.endarea\n.close\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="SOMEWHERE"):
        sites(tmp_path / "vwf.asm")
