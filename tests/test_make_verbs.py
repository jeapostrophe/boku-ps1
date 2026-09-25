"""The README points at things that move (PLAN `DOC-01`). `./make.sh help` is the one home of
what each verb does, and the docs name verbs and point there; other files cite README sections
by name. Three ways that goes false without anyone running a command: a verb is added or
renamed in the dispatcher and the usage text is not; a README (or a docstring, or an error
message) names a verb the dispatcher does not have; or a README section is renamed and its
citations are not. Every side is read from the files, never retyped here."""

from __future__ import annotations

import re
import subprocess

import pytest

from boku import REPO_ROOT

MAKE_SH = REPO_ROOT / "make.sh"

# A plan row names verbs that are still to be built (`PLAN REL-02`'s export), so PLAN.md is the
# one tracked file allowed to cite a verb make.sh does not have yet.
NOT_YET_BUILT_MAY_BE_CITED_IN = {"PLAN.md"}

CITED_VERB = re.compile(r"\./make\.sh[`\s]+([a-z][a-z0-9-]*)")
# `README § "Who this is for"`, `README § 'The import step'`, `` `README.md` § Layout ``;
# not `translation/README.md § Format`.
CITED_SECTION = re.compile(
    r"(?<![/\w])README(?:\.md)?`?\s*§\s*(?:\*?\"([^\"]+)\"|\*?'([^']+)'|([A-Z]\w+))"
)


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


def tracked_texts() -> list[tuple[str, str]]:
    """Every tracked text file, as it is on disk now."""
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True)
    if listed.returncode != 0:
        pytest.skip("not a git checkout: the tracked files cannot be listed")
    texts = []
    for name in filter(None, listed.stdout.decode("utf-8").split("\0")):
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


def test_every_readme_section_a_tracked_file_cites_is_a_heading():
    """A citation names a heading or the start of one (`§ "Who this is for"`)."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    headings = [h.strip() for h in re.findall(r"^#{2,3} (.+)$", readme, re.M)]
    cited, dangling = 0, []
    for name, text in tracked_texts():
        for double, single, bare in CITED_SECTION.findall(text):
            cited += 1
            section = " ".join((double or single or bare).split())  # a quote may wrap a line
            if not any(h.startswith(section) for h in headings):
                dangling.append(f'{name}: README § "{section}"')
    assert cited, "no README § citation found in any tracked file -- the pattern is out of date"
    assert not dangling, f"{len(dangling)} citation(s) of a README section that is gone: {dangling}"
