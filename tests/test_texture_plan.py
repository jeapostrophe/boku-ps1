"""`tools/textures/make_plan.py` — the gate on the GFX-03 decision table.

`research/data/texture-plan.tsv` is generated from the tracked census, so it gets the
same gate every other tracked `research/data/*.tsv` has: regenerate it and diff. Unlike
the rest, this one needs no disc — both its input and its output are tracked.

The two refusals are what make the tracked plan trustworthy between regenerations, and
each is tested at the narrowest input that exhibits the harm:

* a census row that a broad rule silently swallows — the rule's own row count is the only
  thing that can see it, because the rule still matches something;
* a row two rules claim, which a first-match-wins loop resolves by rule order and never
  reports.
"""

from __future__ import annotations

import importlib.util
import sys
from functools import cache
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CENSUS = REPO_ROOT / "research" / "data" / "texture-census.tsv"
PLAN = REPO_ROOT / "research" / "data" / "texture-plan.tsv"


@cache
def make_plan():
    """`tools/textures/make_plan.py` as a module, loaded from its path once."""
    path = REPO_ROOT / "tools" / "textures" / "make_plan.py"
    spec = importlib.util.spec_from_file_location("make_plan", path)
    assert spec and spec.loader, f"{path} is not importable"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def census_rows() -> list[str]:
    return CENSUS.read_text(encoding="utf-8").splitlines()


def census_row(ident: str) -> list[str]:
    """One census row by id, as fields — read from the census, never retyped here."""
    for line in census_rows()[1:]:
        if line.split("\t")[0] == ident:
            return line.split("\t")
    raise AssertionError(f"no census row {ident}")


def column(name: str) -> int:
    """A census column's index, read from the census's own header."""
    return census_rows()[0].split("\t").index(name)


# --- the tracked plan is what the tracked census generates ---------------------------------------


def test_tracked_plan_is_what_the_tracked_census_generates(tmp_path: Path) -> None:
    """The regeneration gate: byte for byte, and no disc needed to run it."""
    out = tmp_path / "texture-plan.tsv"
    make_plan().main(["--census", str(CENSUS), "--out", str(out)])
    assert out.read_bytes() == PLAN.read_bytes()


# --- a row a rule swallows -----------------------------------------------------------------------


def test_a_re_classified_row_a_broad_rule_swallows_is_refused_by_its_count() -> None:
    """The narrowest case: the census's second `T_TITLE` image flips `no` → `maybe`.

    `^_DATA_T_TITLE\\.BIN__` claims it without being written for it, and the decision it
    hands over — the four menu lines — is not that image's. The rule still matches, and
    every row still matches a rule, so neither of the older checks moves; only the count.
    """
    row = census_row("_DATA_T_TITLE.BIN__00c804")
    assert row[column("has_text")] == "no", "the census row this case needs has changed"
    row[column("has_text")] = "maybe"
    census = "\n".join([*census_rows(), "\t".join(row)]) + "\n"

    with pytest.raises(SystemExit) as refusal:
        make_plan().build(census)

    message = str(refusal.value)
    assert r"^_DATA_T_TITLE\.BIN__: 2 rows matched, 1 expected" in message, message


# --- a row two rules claim -----------------------------------------------------------------------


def test_a_row_two_rules_claim_is_refused() -> None:
    """Order cannot decide this, so the script may not silently let it: two rules, one row.

    The rule table here is the test's own two rules, because the tracked table has no
    overlapping pair — which is the property this refusal exists to keep true.
    """
    tool = make_plan()
    rules = [
        (r"^_DATA_T_TITLE\.BIN__", 1, "P", "title menu", "new", "the specific rule"),
        (r"^_DATA_T_", 1, "N", "none", "-", "the broad rule"),
    ]
    row = census_row("_DATA_T_TITLE.BIN__000014")
    assert row[column("has_text")] == "yes", "the census row this case needs has changed"
    census = "\n".join([census_rows()[0], "\t".join(row)]) + "\n"

    with pytest.raises(SystemExit) as refusal:
        tool.build(census, rules)

    message = str(refusal.value)
    assert row[0] in message
    assert r"^_DATA_T_TITLE\.BIN__" in message and r"^_DATA_T_" in message, message
