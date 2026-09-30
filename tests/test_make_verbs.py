"""The docs point at things that move (PLAN `DOC-01`, `DOC-02`). `./make.sh help` is the one
home of what each verb does, and the docs name verbs and point there; other files cite sections
of `README.md` (for the player) and `TECHNICAL.md` (for the contributor) by name, and
`TECHNICAL.md`'s principles by number. Three ways that goes false without anyone running a
command: a verb is added or renamed in the dispatcher and the usage text is not; a document (or
a docstring, or an error message) names a verb the dispatcher does not have; or a section is
renamed, or moved to the other document, and its citations are not. Every side is read from the
files, never retyped here."""

from __future__ import annotations

import re
import subprocess

import pytest

from boku import REPO_ROOT
from boku.packets import markdown_sections

MAKE_SH = REPO_ROOT / "make.sh"

# A plan row names verbs that are still to be built (`PLAN REL-02`'s export), so PLAN.md is the
# one tracked file allowed to cite a verb make.sh does not have yet.
NOT_YET_BUILT_MAY_BE_CITED_IN = {"PLAN.md"}

CITED_VERB = re.compile(r"\./make\.sh[`\s]+([a-z][a-z0-9-]*)")
CITABLE = ("README", "TECHNICAL")
"""The documents cited by section: `<name>.md` at the root."""
_DOCUMENT = rf"(?<![/\w])({'|'.join(CITABLE)})(?:\.md)?`?"
# `README § "Who this is for"`, `TECHNICAL § 'The import step'`, `` `TECHNICAL.md` § Layout ``;
# not `translation/README.md § Format`.
_SECTION = r"§\s*(?:\*?\"([^\"]+)\"|\*?'([^']+)'|([A-Z]\w+))"
CITED_SECTION = re.compile(_DOCUMENT + r"\s*" + _SECTION)
# `README § "Where it is played", § "How the translation is made" and § "Related work"`: the
# sections after the first are the same document's.
NEXT_SECTION = re.compile(r"(?:,|\s+and|,\s+and)\s+" + _SECTION)
# `TECHNICAL principle 2`, `TECHNICAL.md principles 2 and 3`.
CITED_PRINCIPLE = re.compile(_DOCUMENT + r"\s+principles?\s+(\d+)(?:\s+and\s+(\d+))?")
PRINCIPLES_HEADING = "Principles"


def document(name: str) -> str:
    return (REPO_ROOT / f"{name}.md").read_text(encoding="utf-8")


def headings(name: str) -> list[str]:
    return [h.strip() for h in re.findall(r"^#{2,3} (.+)$", document(name), re.M)]


def principles(name: str) -> set[str]:
    """The numbers of the list under the document's `## Principles`; none without one."""
    sections = dict(markdown_sections(document(name), 2))
    body = "\n".join(sections.get(PRINCIPLES_HEADING, []))
    return set(re.findall(r"^(\d+)\. ", body, re.M))


def cited_sections(text: str) -> list[tuple[str, str]]:
    """(document, section) for every section `text` cites, a list after one document name
    included."""
    out = []
    for first in CITED_SECTION.finditer(text):
        name, found = first[1], first
        while found:
            out.append((name, " ".join(next(filter(None, found.groups()[-3:])).split())))
            found = NEXT_SECTION.match(text, found.end())
    return out


def dispatched_verbs(script: str) -> set[str]:
    """The verbs the `case "$verb" in` dispatcher runs, from its arms (`help` included, the
    empty and `-h` spellings and the `*` fallback not)."""
    body = script.split('case "$verb" in', 1)[1].split("\nesac", 1)[0]
    arms = re.findall(r"^    (\S+)\)$", body, re.M)
    verbs = {verb for arm in arms for verb in arm.split("|")}
    return {verb for verb in verbs if re.fullmatch(r"[a-z][a-z0-9-]*", verb)}


def usage_verbs(script: str) -> set[str]:
    """The verbs `usage` lists: its lines indented two spaces, a verb first."""
    text = script.split("usage() {", 1)[1].split("\nEOF", 1)[0]
    return set(re.findall(r"^  ([a-z][a-z0-9-]*)\b", text, re.M))


def tracked_files() -> list[str]:
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True)
    if listed.returncode != 0:
        pytest.skip("not a git checkout: the tracked files cannot be listed")
    return [name for name in listed.stdout.decode("utf-8").split("\0") if name]


def tracked_texts() -> list[tuple[str, str]]:
    """Every tracked text file, as it is on disk now."""
    texts = []
    for name in tracked_files():
        try:
            texts.append((name, (REPO_ROOT / name).read_text(encoding="utf-8")))
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
    return texts


def test_every_dispatched_verb_is_in_the_usage_and_no_other():
    script = MAKE_SH.read_text(encoding="utf-8")
    dispatched, listed = dispatched_verbs(script) - {"help"}, usage_verbs(script)
    assert dispatched, "no verbs found in make.sh's dispatcher -- the parser is out of date"
    assert not dispatched - listed, (
        f"make.sh runs {sorted(dispatched - listed)} but `./make.sh help` does not list them"
    )
    assert not listed - dispatched, (
        f"`./make.sh help` lists {sorted(listed - dispatched)} but make.sh does not run them"
    )


def test_every_verb_a_tracked_file_names_is_one_make_sh_runs():
    verbs = dispatched_verbs(MAKE_SH.read_text(encoding="utf-8"))
    cited, unknown = 0, []
    for name, text in tracked_texts():
        if name in NOT_YET_BUILT_MAY_BE_CITED_IN:
            continue
        for verb in CITED_VERB.findall(text):
            cited += 1
            if verb not in verbs:
                unknown.append(f"{name}: ./make.sh {verb}")
    assert cited, "no `./make.sh <verb>` found in any tracked file -- the pattern is out of date"
    assert not unknown, f"{len(unknown)} citation(s) of a verb make.sh does not run: {unknown[:10]}"


def test_every_section_a_tracked_file_cites_is_a_heading_of_the_document_it_names():
    """A citation names a heading or the start of one (`§ "Who this is for"`), in the document
    that has it."""
    found = {name: headings(name) for name in CITABLE}
    cited, dangling = dict.fromkeys(CITABLE, 0), []
    for file, text in tracked_texts():
        for name, section in cited_sections(text):
            cited[name] += 1
            if not any(h.startswith(section) for h in found[name]):
                moved = [d for d in CITABLE if any(h.startswith(section) for h in found[d])]
                where = f" (it is in {moved[0]}.md)" if moved else ""
                dangling.append(f"{file}: {name} § {section!r}{where}")
    assert all(cited.values()), f"a document nobody cites by section, of {cited}: the pattern?"
    assert not dangling, f"{len(dangling)} citation(s) of a section that is gone: {dangling}"


SAMPLE = """
the charter (README § "Who this
      is for"), then TECHNICAL.md § Layout; and README § 'Where it is played', § "How the
translation is made" and § "Related work"; not translation/README.md § Format, nor a bare
§ "Using it".
"""


def test_a_citation_is_read_across_a_line_break_and_down_a_list():
    assert cited_sections(SAMPLE) == [
        ("README", "Who this is for"),
        ("TECHNICAL", "Layout"),
        ("README", "Where it is played"),
        ("README", "How the translation is made"),
        ("README", "Related work"),
    ]


def test_every_principle_a_tracked_file_cites_is_one_the_document_numbers():
    numbered = {name: principles(name) for name in CITABLE}
    cited, dangling = 0, []
    for file, text in tracked_texts():
        for name, *numbers in CITED_PRINCIPLE.findall(text):
            for number in filter(None, numbers):
                cited += 1
                if number not in numbered[name]:
                    dangling.append(f"{file}: {name} principle {number}")
    assert cited, "no principle is cited in any tracked file -- the pattern is out of date"
    assert not dangling, (
        f"{len(dangling)} citation(s) of a principle its document does not number: {dangling}"
    )
