"""`REL-04`: cutting a release from a clean commit, and posting it with `gh`.

Synthetic images and throwaway git repositories throughout; the notes are rendered from
copies of the real `README.md`, notes template and `translation/status.tsv`, so a heading
DOC work renames is caught here rather than at release time. `gh` is never the real one:
a stub on PATH records what it was asked to do.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku.build import CUE_NAME, CUE_TEXT, IMAGE_NAME, cue_text
from boku.build import MANIFEST_NAME as BUILD_MANIFEST
from boku.coverage import (
    BUILD_ID_NAME,
    REFUSED_FIELD,
    RESULT_SHA1_FIELD,
    SOURCE_SHA1_FIELD,
    WRITTEN_FIELD,
)
from boku.patchfile import (
    _CONVERT,
    _CONVERT_PPF,
    MANIFEST_NAME,
    apply_patch,
    hashes_of,
    patch_stem,
)
from boku.release import (
    BASE_NAME,
    BUILD_ARGS_NAME,
    CREDITS_HEADING,
    HOW_MADE_HEADING,
    MAIN,
    NOTES_PATH,
    NOTES_TEMPLATE,
    PPF,
    PPF_NOTES_TEMPLATE,
    RELEASE_FORMAT,
    RELEASE_MANIFEST,
    STATUS_PATH,
    ReleaseRefused,
    assemble_release,
    github_repo,
    main_publish,
    publish_command,
    readme_section,
    require_clean_tree,
    revision,
)
from tests.test_patchfile import IMAGE_SIZE, needs_xdelta3

TRACKED_INPUTS = ("README.md", NOTES_TEMPLATE, PPF_NOTES_TEMPLATE, STATUS_PATH)
#: The bare repository standing in for GitHub, beside `repo` in the test's tmp_path.
REMOTE_NAME = "github.git"


def git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *arguments], capture_output=True, text=True, check=True
    ).stdout.strip()


def commit_more(repo: Path) -> None:
    (repo / "later.txt").write_text("x")
    git(repo, "add", "later.txt")
    git(repo, "commit", "-q", "-m", "later")


def stub_on_path(tmp_path: Path, monkeypatch, name: str, log: Path) -> None:
    """A `name` first on PATH that appends its arguments, one per line, to `log`."""
    bin_dir = tmp_path / "stub-bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / name
    stub.write_text(f'#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done >> "{log}"\n')
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


@pytest.fixture
def repo(tmp_path) -> Path:
    """A committed repository holding the real notes inputs, and a .gitignore like ours.

    A throwaway fixture: signing and the machine's hook path are switched off in *its*
    local config, since a test commit is not a commit of anyone's work.
    """
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "master")
    for key, value in (
        ("user.name", "Test"),
        ("user.email", "test@example.invalid"),
        ("commit.gpgsign", "false"),
        ("tag.gpgsign", "false"),
        ("core.hooksPath", str(tmp_path / "no-hooks")),
    ):
        git(root, "config", key, value)
    for relative in TRACKED_INPUTS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, target)
    shutil.copyfile(REPO_ROOT / ".gitignore", root / ".gitignore")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "fixture")
    return root


@pytest.fixture
def images(tmp_path) -> tuple[Path, Path]:
    """A base and a built image of equal length, differing in two places."""
    original = random.Random(11).randbytes(IMAGE_SIZE)
    modified = bytearray(original)
    for offset, length in ((0x1200, 4), (0x9800, 300)):
        modified[offset : offset + length] = bytes(
            b ^ 0xFF for b in original[offset : offset + length]
        )
    base = tmp_path / "base.img"
    built = tmp_path / "built.img"
    base.write_bytes(original)
    built.write_bytes(bytes(modified))
    return base, built


def make_build(repo: Path, base: Path, built: Path, *, dirty: bool = False, args: str = "") -> Path:
    """A days build directory as `./make.sh build-days` leaves it, of `repo`'s HEAD."""
    build = repo / "build" / "days"
    build.mkdir(parents=True)
    shutil.copyfile(built, build / IMAGE_NAME)
    (build / CUE_NAME).write_text(CUE_TEXT)
    (build / BUILD_MANIFEST).write_text(
        json.dumps(
            {
                SOURCE_SHA1_FIELD: hashes_of(base).sha1,
                RESULT_SHA1_FIELD: hashes_of(built).sha1,
                WRITTEN_FIELD: ["E0001.0", "E0001.1", "E0002.0"],
                REFUSED_FIELD: {"E0003.0": ["over the band"]},
            }
        )
    )
    head = git(repo, "rev-parse", "--short=8", "HEAD")
    (build / BUILD_ID_NAME).write_text(f"20260925T1200Z-{head}{'-dirty' if dirty else ''}\n")
    (build / BUILD_ARGS_NAME).write_text(f"{args}\n")
    return build


def assemble(
    repo: Path, base: Path, build: Path, base_sha1: str | None = None, *, ppf: bool = True
) -> Path:
    return assemble_release(
        repo=repo,
        base=base,
        build_dir=build,
        out_root=repo / "release",
        base_sha1=base_sha1 or hashes_of(base).sha1,
        ppf=ppf,
    )


# ---------------------------------------------------------------------------
# Version and tree


def test_a_tagged_commit_releases_as_its_tag(repo):
    git(repo, "tag", "v0.2.0")
    made = revision(repo)
    assert (made.version, made.tag) == ("0.2.0", "v0.2.0")
    assert made.commit == git(repo, "rev-parse", "HEAD")


def test_an_untagged_commit_is_a_snapshot_named_by_describe(repo):
    git(repo, "tag", "v0.2.0")
    commit_more(repo)
    made = revision(repo)
    assert made.tag is None
    assert made.version == f"0.2.0-1-g{git(repo, 'rev-parse', '--short=8', 'HEAD')}"


def test_a_repository_with_no_version_tag_is_a_snapshot_of_its_commit(repo):
    git(repo, "tag", "first-draft")  # the repo's own non-version tags are not versions
    made = revision(repo)
    assert made.tag is None
    assert made.version == f"0-g{git(repo, 'rev-parse', '--short=8', 'HEAD')}"


def test_two_version_tags_on_one_commit_are_refused(repo):
    git(repo, "tag", "v0.2.0")
    git(repo, "tag", "v0.3.0")
    with pytest.raises(ReleaseRefused, match=r"v0\.2\.0, v0\.3\.0"):
        revision(repo)


def test_a_version_too_long_for_the_ppf_fingerprint_is_refused(repo):
    """The version rides in the PPF's 50-byte description; a tag that overflows it would
    only fail after the whole image had been built."""
    git(repo, "tag", "v1.0.0-release-candidate-one")
    with pytest.raises(ReleaseRefused, match="PPF"):
        revision(repo)


def test_a_clean_tree_passes(repo):
    require_clean_tree(repo)


def test_a_modified_tracked_file_is_refused(repo):
    (repo / "README.md").write_text("edited\n")
    with pytest.raises(ReleaseRefused, match=r"README\.md"):
        require_clean_tree(repo)


def test_an_untracked_file_is_refused(repo):
    """`git describe --dirty`, which stamps the build id, does not see untracked files --
    and an untracked day file is read by the build all the same."""
    (repo / "translation" / "day99.txt").write_text("E9999.0\tHello\n")
    with pytest.raises(ReleaseRefused, match=r"day99\.txt"):
        require_clean_tree(repo)


def test_ignored_outputs_do_not_make_the_tree_dirty(repo):
    for ignored in ("build/days/image.img", "release/v0/RELEASE.json", "work/x"):
        (repo / ignored).parent.mkdir(parents=True, exist_ok=True)
        (repo / ignored).write_text("x")
    require_clean_tree(repo)


# ---------------------------------------------------------------------------
# README sections


def test_the_notes_quote_the_readme_sections_they_name():
    """The real README, so a renamed heading fails here and not on release day."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for heading in (HOW_MADE_HEADING, CREDITS_HEADING):
        body = readme_section(readme, heading)
        assert body.strip()


def test_relative_links_become_paths_and_web_links_survive():
    readme = (
        "## Credit\n\nSee [the survey](research/p.md), [research/q.md](research/q.md) and "
        "[pleonex](https://github.com/pleonex/x).\n\n## Next\n\nnot this\n"
    )
    body = readme_section(readme, "Credit")
    assert "the survey (`research/p.md`)" in body
    assert "`research/q.md`" in body and "[research/q.md]" not in body
    assert "[pleonex](https://github.com/pleonex/x)" in body
    assert "not this" not in body


def test_a_missing_readme_section_is_refused():
    with pytest.raises(ReleaseRefused, match="Related work"):
        readme_section("## Something else\n", "Related work")


# ---------------------------------------------------------------------------
# Assembling


def unzip(bundle: Path) -> tuple[str, dict[str, bytes]]:
    """A zip's one top-level folder, and its members by file name."""
    with zipfile.ZipFile(bundle) as archive:
        (folder,) = {str(Path(name).parent) for name in archive.namelist()}
        return folder, {Path(name).name: archive.read(name) for name in archive.namelist()}


def contract(directory: Path) -> dict:
    return json.loads((directory / MANIFEST_NAME).read_text())


@needs_xdelta3
def test_the_main_download_holds_the_xdelta_the_cue_and_the_notes(repo, images):
    base, built = images
    git(repo, "tag", "v0.2.0")
    out = assemble(repo, base, make_build(repo, base, built))

    assert out == (repo / "release" / "v0.2.0").resolve()
    main = out / MAIN.directory
    patch = contract(main)
    stem = patch_stem("0.2.0")
    assert [entry["file"] for entry in patch["patches"]] == [f"{stem}.xdelta"]
    assert patch["original"]["name"] == BASE_NAME
    assert patch["original"]["sha1"] == hashes_of(base).sha1
    assert patch["result"]["sha1"] == hashes_of(built).sha1

    cue = (main / f"{stem}.cue").read_text()
    assert cue == cue_text(patch["result"]["name"])

    notes = (out / NOTES_PATH).read_text()
    for side in ("original", "result"):
        for key in ("crc32", "md5", "sha1"):
            assert patch[side][key] in notes
        assert f"{patch[side]['size']:,}" in notes
    readme = (repo / "README.md").read_text()
    for heading in (HOW_MADE_HEADING, CREDITS_HEADING):
        first_line = readme_section(readme, heading).strip().splitlines()[0]
        assert first_line in notes
    assert git(repo, "rev-parse", "HEAD") in notes


@needs_xdelta3
def test_the_ppf_is_not_in_the_main_download_and_its_contract_does_not_describe_it(repo, images):
    """Jay, 2026-09-25: the PPF is a different download, so that it can be withdrawn."""
    base, built = images
    git(repo, "tag", "v0.2.0")
    out = assemble(repo, base, make_build(repo, base, built))
    manifest = json.loads((out / RELEASE_MANIFEST).read_text())
    _, main = unzip(out / manifest["assets"][0]["file"])
    assert not [name for name in main if name.endswith(".ppf")]
    for name in (MANIFEST_NAME, "README.txt"):
        assert b"ppf" not in main[name].lower(), f"{name} describes a PPF it does not carry"


@needs_xdelta3
def test_the_ppf_download_stands_alone(repo, images, tmp_path):
    """Its own PATCH.json, README and cue: extracted by itself, `boku apply-patch` checks
    it against full SHA-1s (not the PPF's 8-digit fingerprint) and gives the build."""
    base, built = images
    git(repo, "tag", "v0.2.0")
    out = assemble(repo, base, make_build(repo, base, built))
    manifest = json.loads((out / RELEASE_MANIFEST).read_text())
    assert [asset["file"] for asset in manifest["assets"]] == [
        MAIN.asset("0.2.0"),
        PPF.asset("0.2.0"),
    ]
    folder, members = unzip(out / manifest["assets"][1]["file"])
    stem = patch_stem("0.2.0")
    assert set(members) == {f"{stem}.ppf", MANIFEST_NAME, "README.txt", f"{stem}.cue"}
    # Extracted side by side, the two downloads must not overwrite each other's PATCH.json.
    assert folder != unzip(out / manifest["assets"][0]["file"])[0]
    assert b"DuckStation" in members["README.txt"]
    alone = tmp_path / "alone"
    alone.mkdir()
    for name, data in members.items():
        (alone / name).write_bytes(data)
    # The contract must name the file itself: apply_patch honours a PATCH.json only for a
    # patch it lists, and otherwise falls back to the 8-digit fingerprint.
    assert [entry["file"] for entry in contract(alone)["patches"]] == [f"{stem}.ppf"]
    readme = members["README.txt"].decode()
    assert _CONVERT_PPF in readme and _CONVERT not in readme  # a .chd works for DuckStation
    result = apply_patch(base, alone / f"{stem}.ppf", tmp_path / "patched.img")
    assert result.sha1 == hashes_of(built).sha1


@needs_xdelta3
def test_every_download_is_its_directory_under_its_real_names(repo, images):
    """GitHub renames an uploaded asset whose name has spaces or brackets, and PATCH.json,
    README.txt and the .cue name the files -- so they travel inside archives."""
    base, built = images
    git(repo, "tag", "v0.2.0")
    out = assemble(repo, base, make_build(repo, base, built))
    manifest = json.loads((out / RELEASE_MANIFEST).read_text())
    for asset, directory in zip(manifest["assets"], (MAIN.directory, PPF.directory), strict=True):
        assert all(c.isalnum() or c in "-._" for c in asset["file"])
        assert asset["sha1"] == hashes_of(out / asset["file"]).sha1
        _, members = unzip(out / asset["file"])
        assert members == {p.name: p.read_bytes() for p in (out / directory).iterdir()}
        assert not any(name.endswith((".img", ".bin", ".iso", ".chd")) for name in members)


@needs_xdelta3
def test_no_ppf_releases_the_main_download_alone_and_never_builds_a_ppf(repo, images, monkeypatch):
    """The mode that ships without the PPF cannot be stopped by the PPF writer."""

    def refuse(*args, **kwargs):
        raise AssertionError("make_ppf ran for a --no-ppf release")

    monkeypatch.setattr("boku.patchfile.make_ppf", refuse)
    base, built = images
    git(repo, "tag", "v0.2.0")
    out = assemble(repo, base, make_build(repo, base, built), ppf=False)
    manifest = json.loads((out / RELEASE_MANIFEST).read_text())
    assert [asset["file"] for asset in manifest["assets"]] == [MAIN.asset("0.2.0")]
    assert not (out / PPF.directory).exists()
    assert ".ppf" not in (out / NOTES_PATH).read_text()


@needs_xdelta3
def test_the_notes_offer_the_ppf_when_it_ships(repo, images):
    base, built = images
    git(repo, "tag", "v0.2.0")
    notes = (assemble(repo, base, make_build(repo, base, built)) / NOTES_PATH).read_text()
    assert PPF.asset("0.2.0") in notes
    assert f"{patch_stem('0.2.0')}.ppf" in notes


@needs_xdelta3
def test_the_same_commit_gives_the_same_release_bytes(repo, images):
    base, built = images
    git(repo, "tag", "v0.2.0")
    build = make_build(repo, base, built)

    def contents(out: Path) -> dict[str, bytes]:
        return {str(p.relative_to(out)): p.read_bytes() for p in out.rglob("*") if p.is_file()}

    before = contents(assemble(repo, base, build))
    assert contents(assemble(repo, base, build)) == before


@needs_xdelta3
def test_a_snapshot_is_built_under_its_describe_name(repo, images):
    base, built = images
    out = assemble(repo, base, make_build(repo, base, built))
    manifest = json.loads((out / RELEASE_MANIFEST).read_text())
    assert manifest["tag"] is None
    assert out.name == f"v{manifest['version']}"


def test_a_build_of_another_commit_is_refused(repo, images):
    base, built = images
    build = make_build(repo, base, built)
    commit_more(repo)
    with pytest.raises(ReleaseRefused, match="is of"):
        assemble(repo, base, build)


def test_a_build_made_from_edits_is_refused(repo, images):
    base, built = images
    with pytest.raises(ReleaseRefused, match="uncommitted"):
        assemble(repo, base, make_build(repo, base, built, dirty=True))


def test_an_image_changed_since_its_build_is_refused(repo, images):
    base, built = images
    build = make_build(repo, base, built)
    with (build / "image.img").open("r+b") as image:
        image.write(b"\0\0\0\0")
    with pytest.raises(ReleaseRefused, match="changed since"):
        assemble(repo, base, build)


def test_a_base_that_is_not_the_redump_dump_is_refused(repo, images):
    base, built = images
    with pytest.raises(ReleaseRefused, match="Redump"):
        assemble(repo, base, make_build(repo, base, built), base_sha1="0" * 40)


def test_a_dirty_tree_builds_nothing(repo, images):
    base, built = images
    build = make_build(repo, base, built)
    (repo / "README.md").write_text("edited\n")
    with pytest.raises(ReleaseRefused, match=r"README\.md"):
        assemble(repo, base, build)
    assert not (repo / "release").exists()


@needs_xdelta3
def test_a_patch_that_does_not_reproduce_the_build_is_not_released(repo, images, monkeypatch):
    """The last gate applies every patch through `boku apply-patch`'s own path. Here the
    PPF writer is made to emit a patch for a different target, with a manifest that agrees
    with it -- the round trip through `apply_patch` passes, and only the comparison with
    the built image can catch it."""
    import boku.patchfile as patchfile

    base, built = images
    git(repo, "tag", "v0.2.0")
    build = make_build(repo, base, built)
    other = built.parent / "other.img"
    data = bytearray(built.read_bytes())
    data[0x2000] ^= 0xFF
    other.write_bytes(bytes(data))
    real = patchfile.build_patches

    def wrong_target(original, modified, out_dir, **kwargs):
        return real(original, other, out_dir, **kwargs)

    monkeypatch.setattr("boku.release.build_patches", wrong_target)
    with pytest.raises(ReleaseRefused, match="does not reproduce"):
        assemble(repo, base, build)
    assert not (repo / "release" / "v0.2.0").exists()


@needs_xdelta3
def test_a_ppf_that_does_not_reproduce_the_build_is_not_released(repo, images, monkeypatch):
    """The xdelta is right and the PPF alone is wrong: the check must run on the PPF's own
    download too, not only on the main one."""
    import boku.patchfile as patchfile

    base, built = images
    git(repo, "tag", "v0.2.0")
    build = make_build(repo, base, built)
    real = patchfile.build_patches

    def broken_ppf(original, modified, out_dir, **kwargs):
        made = real(original, modified, out_dir, **kwargs)
        data = bytearray(made.ppf_path.read_bytes())
        data[-1] ^= 0xFF  # the last byte of the last record's data
        made.ppf_path.write_bytes(bytes(data))
        return made

    monkeypatch.setattr("boku.release.build_patches", broken_ppf)
    with pytest.raises(ReleaseRefused, match=r"\.ppf does not"):
        assemble(repo, base, build)
    assert not (repo / "release" / "v0.2.0").exists()


# ---------------------------------------------------------------------------
# Publishing


@pytest.fixture
def gh_stub(tmp_path, monkeypatch) -> Path:
    """A `gh` on PATH that records its arguments, one per line."""
    log = tmp_path / "gh-called.txt"
    stub_on_path(tmp_path, monkeypatch, "gh", log)
    return log


@pytest.fixture
def github_remote(tmp_path) -> Path:
    """A bare repository standing in for GitHub, where `publish-release` looks up the tag."""
    remote = tmp_path / REMOTE_NAME
    git(tmp_path, "init", "-q", "--bare", str(remote))
    return remote


@pytest.fixture
def tagged_release(repo, images, github_remote) -> Path:
    """A release of tag v0.2.0, the tag pushed (annotated, so the lookup must peel it)."""
    if needs_xdelta3.args[0]:  # a mark on a fixture does nothing
        pytest.skip(needs_xdelta3.kwargs["reason"])
    base, built = images
    git(repo, "tag", "-a", "-m", "v0.2.0", "v0.2.0")
    git(repo, "push", "-q", str(github_remote), "v0.2.0")
    return assemble(repo, base, make_build(repo, base, built))


def publish(release: Path, repo: Path, **kwargs) -> int:
    options = {
        "yes": False,
        "draft": False,
        "prerelease": False,
        "github": "owner/boku-ps1",
        "remote": str(repo.parent / REMOTE_NAME),
    }
    options.update(kwargs)
    return main_publish(release, git_repo=repo, **options)


def test_without_yes_nothing_is_posted(tagged_release, repo, gh_stub, capsys):
    assert publish(tagged_release, repo) == 0
    assert not gh_stub.exists()
    said = capsys.readouterr().out
    assert "gh release create v0.2.0" in said
    assert "nothing was changed on GitHub" in said


def test_with_yes_gh_is_given_the_tag_the_bundle_and_the_notes(tagged_release, repo, gh_stub):
    assert publish(tagged_release, repo, yes=True, draft=True) == 0
    called = gh_stub.read_text().splitlines()
    manifest = json.loads((tagged_release / RELEASE_MANIFEST).read_text())
    expected = publish_command(
        tagged_release, manifest, "owner/boku-ps1", draft=True, prerelease=False
    )
    assert called == expected[1:]
    assert called[:3] == ["release", "create", "v0.2.0"]
    for asset in manifest["assets"]:
        assert str(tagged_release / asset["file"]) in called
    assert len(manifest["assets"]) == 2
    assert "--verify-tag" in called and "--draft" in called
    assert called[called.index("--notes-file") + 1] == str(tagged_release / NOTES_PATH)
    assert called[called.index("--repo") + 1] == "owner/boku-ps1"


def test_only_the_bundles_are_uploaded_whatever_else_is_in_the_directory(
    tagged_release, repo, gh_stub
):
    (tagged_release / "stray.img").write_bytes(b"\0" * 2352)
    assert publish(tagged_release, repo, yes=True) == 0
    called = gh_stub.read_text().splitlines()
    assert not any("stray.img" in argument for argument in called)
    assert not any(argument.endswith((".ppf", ".xdelta")) for argument in called)


@needs_xdelta3
def test_a_snapshot_is_not_published(repo, images, gh_stub):
    base, built = images
    out = assemble(repo, base, make_build(repo, base, built))
    assert publish(out, repo, yes=True) == 1
    assert not gh_stub.exists()


@pytest.mark.parametrize("which", [0, 1])
def test_a_bundle_changed_after_the_build_is_not_published(tagged_release, repo, gh_stub, which):
    manifest = json.loads((tagged_release / RELEASE_MANIFEST).read_text())
    with (tagged_release / manifest["assets"][which]["file"]).open("ab") as bundle:
        bundle.write(b"!")
    assert publish(tagged_release, repo, yes=True) == 1
    assert not gh_stub.exists()


def test_a_tag_moved_since_the_build_is_not_published(tagged_release, repo, gh_stub):
    commit_more(repo)
    git(repo, "tag", "-f", "v0.2.0")
    assert publish(tagged_release, repo, yes=True) == 1
    assert not gh_stub.exists()


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("git@github.com:jay/boku-ps1.git", "jay/boku-ps1"),
        ("https://github.com/jay/boku-ps1.git", "jay/boku-ps1"),
        ("https://github.com/jay/boku-ps1", "jay/boku-ps1"),
        ("ssh://git@github.com/jay/boku-ps1.git", "jay/boku-ps1"),
        ("https://gitlab.com/jay/boku-ps1.git", None),
    ],
)
def test_the_github_repository_comes_from_origin(repo, url, expected):
    git(repo, "remote", "add", "origin", url)
    assert github_repo(repo) == expected


def test_no_origin_and_no_repo_is_refused(tagged_release, repo, gh_stub, capsys):
    assert publish(tagged_release, repo, yes=True, github=None) == 1
    assert "--repo" in capsys.readouterr().out
    assert not gh_stub.exists()


def test_a_build_given_arguments_is_refused(repo, images):
    """build-days passes its arguments to `boku build`; `--no-renderer-patch` or another
    translation directory makes an image of HEAD that is not the release."""
    base, built = images
    with pytest.raises(ReleaseRefused, match="--no-renderer-patch"):
        assemble(repo, base, make_build(repo, base, built, args="--no-renderer-patch"))


def test_a_build_that_did_not_record_its_arguments_is_refused(repo, images):
    base, built = images
    build = make_build(repo, base, built)
    (build / BUILD_ARGS_NAME).unlink()
    with pytest.raises(ReleaseRefused, match=BUILD_ARGS_NAME):
        assemble(repo, base, build)


def test_a_tag_on_github_naming_another_commit_is_not_published(
    tagged_release, repo, github_remote, gh_stub, capsys
):
    """The local tag is right; GitHub's is not. `gh --verify-tag` only asks whether a tag of
    that name exists there, so it would attach this patch to the other commit's source."""
    commit_more(repo)
    git(repo, "push", "-q", "-f", str(github_remote), "HEAD:refs/tags/v0.2.0")
    assert publish(tagged_release, repo, yes=True) == 1
    assert "names" in capsys.readouterr().out
    assert not gh_stub.exists()


@needs_xdelta3
def test_a_tag_not_yet_pushed_is_a_warning_in_a_dry_run_and_a_refusal_with_yes(
    repo, images, github_remote, gh_stub, capsys
):
    base, built = images
    git(repo, "tag", "v0.2.0")
    release = assemble(repo, base, make_build(repo, base, built))
    assert publish(release, repo) == 0
    assert "not on owner/boku-ps1 yet" in capsys.readouterr().out
    assert publish(release, repo, yes=True) == 1
    assert "git push origin v0.2.0" in capsys.readouterr().out
    assert not gh_stub.exists()


def test_a_release_manifest_missing_a_field_is_refused_not_a_traceback(
    tagged_release, repo, gh_stub, capsys
):
    path = tagged_release / RELEASE_MANIFEST
    manifest = json.loads(path.read_text())
    del manifest["commit"]
    path.write_text(json.dumps(manifest))
    assert publish(tagged_release, repo, yes=True) == 1
    assert "commit" in capsys.readouterr().out
    assert not gh_stub.exists()


def test_release_preflight_through_make_sh_builds_nothing(tmp_path, monkeypatch):
    """`./make.sh release --preflight` is the cheap check; it must not run build-days first.
    `uv` is stubbed, so every command make.sh would run is recorded instead of run."""
    log = tmp_path / "uv-called.txt"
    stub_on_path(tmp_path, monkeypatch, "uv", log)
    done = subprocess.run(
        [str(REPO_ROOT / "make.sh"), "release", "--preflight"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert log.read_text().splitlines() == ["run", "boku", "release", "--preflight"]


def test_the_build_args_file_is_the_one_make_sh_writes():
    script = (REPO_ROOT / "make.sh").read_text(encoding="utf-8")
    assert BUILD_ARGS_NAME in script, f"make.sh no longer writes {BUILD_ARGS_NAME}"


@needs_xdelta3
def test_withdrawing_the_ppf_deletes_its_asset_and_replaces_the_notes(
    repo, images, github_remote, gh_stub
):
    """The tag cut again with --no-ppf; the stub records both gh calls, one argument a line."""
    base, built = images
    git(repo, "tag", "-a", "-m", "v0.2.0", "v0.2.0")
    git(repo, "push", "-q", str(github_remote), "v0.2.0")
    out = assemble(repo, base, make_build(repo, base, built), ppf=False)
    assert publish(out, repo, yes=True, withdraw_ppf=True) == 0
    called = gh_stub.read_text().splitlines()
    edit = called.index("edit")
    assert called[:4] == ["release", "delete-asset", "v0.2.0", PPF.asset("0.2.0")]
    assert "--yes" in called[:edit]
    assert called[edit - 1 : edit + 2] == ["release", "edit", "v0.2.0"]
    assert called[called.index("--notes-file") + 1] == str(out / NOTES_PATH)
    assert "create" not in called


def test_withdrawing_from_a_release_that_still_carries_the_ppf_is_refused(
    tagged_release, repo, gh_stub, capsys
):
    assert publish(tagged_release, repo, yes=True, withdraw_ppf=True) == 1
    assert "--no-ppf" in capsys.readouterr().out
    assert not gh_stub.exists()


def test_a_release_of_the_one_zip_layout_is_refused_as_an_older_format(
    tagged_release, repo, gh_stub, capsys
):
    path = tagged_release / RELEASE_MANIFEST
    manifest = json.loads(path.read_text())
    # 1 is the one-zip layout of the first release machinery, its notes not at NOTES_PATH.
    path.write_text(json.dumps({**manifest, "format": 1}))
    assert publish(tagged_release, repo, yes=True) == 1
    assert f"format-{RELEASE_FORMAT}" in capsys.readouterr().out
    assert not gh_stub.exists()
