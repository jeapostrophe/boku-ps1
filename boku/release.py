r"""`REL-04`: cut a release from a clean commit, and post it with `gh`.

`./make.sh release` refuses a tree with anything uncommitted, builds the days image, and
then `assemble_release` turns that build into `release/v<version>/`:

* the two patches, `PATCH.json` and `README.txt` exactly as `boku patch` writes them
  (`boku.patchfile`, `PIPE-05`), naming the base as the file the instructions tell a
  player to extract (`BASE_NAME`);
* a `.cue` for the patched image under its release name;
* `RELEASE-NOTES.md`, the GitHub release page: the template `boku/release-notes.md` filled
  from `PATCH.json`, the build's manifest, `translation/status.tsv` and two sections of
  `README.md` quoted whole (`HOW_MADE_HEADING`, `CREDITS_HEADING`) -- one home for each;
* `boku-ps1-v<version>.zip`, all of the above under their real names. It is the only
  asset uploaded: GitHub renames an asset whose name has spaces or brackets, and
  `PATCH.json`, `README.txt` and the `.cue` all name the files, so loose uploads would
  arrive with names nothing in them refers to;
* `RELEASE.json`, what `boku publish-release` reads: version, tag, commit and the asset's
  SHA-1.

Every patch is then applied to the base through `boku.patchfile.apply_patch` -- the path a
player's `boku apply-patch` takes -- and the result must hash to the built image, or
nothing is written.

The version is git's. A commit carrying one `v<version>` tag releases as that version; any
other commit is a snapshot named by `git describe` (`0.2.0-3-gabcdef12`, or `0-g<sha>`
before the first version tag), which can be built and tried but not published. The
package version in `pyproject.toml` is not the release's: `boku patch` still names its
files by it.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from string import Template

from boku import REPO_ROOT
from boku.build import IMAGE_NAME, cue_text
from boku.build import MANIFEST_NAME as BUILD_MANIFEST
from boku.coverage import BUILD_ID_NAME, CoverageError, Manifest
from boku.importer import IMAGE_SHA1, sha1_of
from boku.packets import markdown_sections
from boku.patchfile import (
    GAME_NAME,
    MANIFEST_NAME,
    README_NAME,
    TEAM,
    PatchError,
    apply_patch,
    build_patches,
    hashes_of,
    patch_stem,
    ppf_description,
)
from boku.ppf import DESCRIPTION_SIZE
from boku.reader import STATES, STATUS_FILE, ReaderRefused, build_revision, read_status
from boku.staging import StagingRefused, check_out_dir, staged

RELEASE_ROOT = Path("release")
RELEASE_MANIFEST = "RELEASE.json"
RELEASE_FORMAT = 1
RELEASE_KEYS = ("version", "tag", "commit", "title", "assets")
NOTES_NAME = "RELEASE-NOTES.md"
NOTES_TEMPLATE = Path("boku/release-notes.md")
STATUS_PATH = STATUS_FILE.relative_to(REPO_ROOT)
TAG_PREFIX = "v"
HOW_MADE_HEADING = "How the translation is made"
CREDITS_HEADING = "Related work and credit"
#: What the instructions have `chdman extractcd -ob` write, so every command in the notes
#: and in `PATCH.json` names a file the player has. The name is ours to choose; the
#: Redump-style one is the one a player's dump is most likely already called.
BASE_NAME = "Boku no Natsuyasumi - Summer Holiday 20th Century (Japan).bin"
#: research/disc-recon.md § "The dump" -- the disc page the base hashes were checked against.
REDUMP_URL = "http://redump.org/disc/4890/"
#: `./make.sh build-days` writes the arguments it passed through to `boku build` here, one
#: a line; a release is only of a build that was given none.
BUILD_ARGS_NAME = "BUILD-ARGS.txt"

_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+-]*")
_GITHUB = re.compile(r"github\.com[:/](?P<repo>[^/\s]+/[^/\s]+?)(?:\.git)?/?$")
_RELATIVE_LINK = re.compile(r"\[([^\]]+)\]\((?!https?://|#)([^)\s]+)\)")


class ReleaseRefused(Exception):
    """A release we will not build, or will not post."""


# ---------------------------------------------------------------------------
# git


def _git(repo: Path, *arguments: str) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *arguments], capture_output=True, text=True, check=True
        )
    except FileNotFoundError as error:
        raise ReleaseRefused("git is not on PATH") from error
    except subprocess.CalledProcessError as error:
        raise ReleaseRefused(f"git {' '.join(arguments)} failed: {error.stderr.strip()}") from error
    return done.stdout.strip()


@dataclass(frozen=True)
class Revision:
    commit: str
    version: str
    #: The `v<version>` tag on the commit; `None` for a snapshot, which is never posted.
    tag: str | None


def revision(repo: Path) -> Revision:
    """HEAD's release version: its one version tag, else `git describe`'s snapshot name."""
    commit = _git(repo, "rev-parse", "HEAD")
    tags = _git(repo, "tag", "--points-at", "HEAD", "--list", f"{TAG_PREFIX}[0-9]*").split()
    if len(tags) > 1:
        raise ReleaseRefused(
            f"HEAD carries {len(tags)} version tags ({', '.join(sorted(tags))}); a commit is "
            f"one release. Delete the wrong one."
        )
    if tags:
        tag = tags[0]
        version = tag.removeprefix(TAG_PREFIX)
    else:
        tag = None
        try:
            described = _git(
                repo, "describe", "--tags", "--match", f"{TAG_PREFIX}[0-9]*", "--abbrev=8"
            )
            version = described.removeprefix(TAG_PREFIX)
        except ReleaseRefused:  # no version tag anywhere behind HEAD yet
            version = f"0-g{_git(repo, 'rev-parse', '--short=8', 'HEAD')}"
    _check_version(version)
    return Revision(commit=commit, version=version, tag=tag)


def _check_version(version: str) -> None:
    if not _VERSION.fullmatch(version):
        raise ReleaseRefused(
            f"version {version!r} has characters a file name or the PPF fingerprint cannot "
            f"carry; use letters, digits, '.', '+' and '-'"
        )
    description = ppf_description(version, "0" * 40, "0" * 40)
    if len(description) > DESCRIPTION_SIZE:
        raise ReleaseRefused(
            f"version {version!r} is too long: the PPF description it rides in is "
            f"{DESCRIPTION_SIZE} bytes and {description!r} is {len(description)}"
        )


def require_clean_tree(repo: Path) -> None:
    """Refuse anything `git status` shows, untracked files included.

    `git describe --dirty`, which stamps the build id, sees only tracked edits; an
    untracked day file is read by the build all the same, and would ship in a release no
    commit can reproduce.
    """
    status = _git(repo, "status", "--porcelain", "--untracked-files=all")
    if status:
        lines = status.splitlines()
        shown = "\n  ".join(lines[:12]) + ("\n  ..." if len(lines) > 12 else "")
        raise ReleaseRefused(
            f"the tree has {len(lines)} uncommitted change(s); a release is built from a "
            f"commit and nothing else:\n  {shown}\nCommit or remove them first."
        )


def github_repo(repo: Path) -> str | None:
    """`OWNER/REPO` from the `origin` remote's URL, or `None` when there is no GitHub one."""
    try:
        url = _git(repo, "remote", "get-url", "origin")
    except ReleaseRefused:
        return None
    matched = _GITHUB.search(url)
    return matched["repo"] if matched else None


# ---------------------------------------------------------------------------
# The notes


def readme_section(readme: str, heading: str) -> str:
    """The body of README's `## heading`, with repo-relative links turned into paths.

    A relative link resolves on GitHub's file view and nowhere else, and the notes are read
    on the release page; the path in code is what a reader looks up in the source archive.
    """
    lines = next((body for title, body in markdown_sections(readme, 2) if title == heading), None)
    if lines is None:
        raise ReleaseRefused(
            f"README.md has no section '## {heading}', which the release notes quote whole"
        )
    body = "\n".join(lines).strip("\n")

    def as_path(matched: re.Match[str]) -> str:
        text, target = matched[1], matched[2]
        return f"`{target}`" if text == target else f"{text} (`{target}`)"

    return _RELATIVE_LINK.sub(as_path, body)


def _hash_table(side: dict) -> str:
    return (
        "| | |\n|---|---|\n"
        f"| File | `{side['name']}` |\n"
        f"| Size | {side['size']:,} bytes |\n"
        f"| CRC32 | `{side['crc32']}` |\n"
        f"| MD5 | `{side['md5']}` |\n"
        f"| SHA-1 | `{side['sha1']}` |"
    )


def _coverage(build_manifest: Manifest, status: dict) -> str:
    written = len(build_manifest.written)
    refused = len(build_manifest.refused)
    states = [unit.state for unit in status.values()]
    counted = ", ".join(f"{states.count(s)} {s}" for s in STATES if states.count(s))
    return (
        f"The build wrote {written:,} lines of English into the game"
        + (f"; {refused:,} did not fit and stay Japanese" if refused else "")
        + f". The translation's {len(states)} units (`translation/status.tsv`): {counted}."
    )


def render_notes(
    template: str,
    *,
    made: Revision,
    patch: dict,
    build_manifest: Manifest,
    status: dict,
    readme: str,
    cue_name: str,
    bundle_name: str,
) -> str:
    by_format = {entry["format"]: entry for entry in patch["patches"]}
    values = {
        "version": made.version,
        "commit": made.commit,
        "built_from": (
            f"tag `{made.tag}`" if made.tag else "an untagged commit: a snapshot, not a release"
        ),
        "bundle": bundle_name,
        "base_name": patch["original"]["name"],
        "base_stem": Path(patch["original"]["name"]).stem,
        "result_name": patch["result"]["name"],
        "cue": cue_name,
        "xdelta": by_format["xdelta3"]["file"],
        "ppf": by_format["ppf3"]["file"],
        "base_sha1": patch["original"]["sha1"],
        "original_table": _hash_table(patch["original"]),
        "result_table": _hash_table(patch["result"]),
        "redump": REDUMP_URL,
        "coverage": _coverage(build_manifest, status),
        "how_made": readme_section(readme, HOW_MADE_HEADING),
        "credits": readme_section(readme, CREDITS_HEADING),
    }
    try:
        return Template(template).substitute(values)
    except (KeyError, ValueError) as error:
        raise ReleaseRefused(
            f"{NOTES_TEMPLATE} has a placeholder we do not fill: {error}"
        ) from error


# ---------------------------------------------------------------------------
# Assembling


def _built_image(build_dir: Path, made: Revision, base_sha1: str) -> tuple[Path, Manifest]:
    """The build's image and manifest, refused unless it is the default build of HEAD."""
    image = build_dir / IMAGE_NAME
    args_path = build_dir / BUILD_ARGS_NAME
    for path in (build_dir / BUILD_ID_NAME, args_path, image):
        if not path.is_file():
            raise ReleaseRefused(f"no {path}: run ./make.sh release, which builds it")
    try:
        build_manifest = Manifest.load(build_dir / BUILD_MANIFEST)
    except CoverageError as error:
        raise ReleaseRefused(str(error)) from error
    built_id = build_manifest.build_id
    passed = args_path.read_text(encoding="utf-8").split()
    if passed:
        raise ReleaseRefused(
            f"build {built_id} was given {' '.join(passed)}; a release is the build "
            f"./make.sh build-days makes with no arguments (./make.sh release makes it)"
        )
    commit, dirty = build_revision(built_id)
    if dirty:
        raise ReleaseRefused(f"build {built_id} was made from uncommitted edits")
    if not commit or not made.commit.startswith(commit):
        raise ReleaseRefused(
            f"build {built_id} is of {commit or 'no commit'}, and HEAD is {made.commit[:8]}: "
            f"run ./make.sh release, which builds HEAD"
        )
    if build_manifest.source_sha1 != base_sha1:
        raise ReleaseRefused(
            f"build {built_id} was made from a base with sha1 {build_manifest.source_sha1}, "
            f"not the Redump dump ({base_sha1})"
        )
    return image, build_manifest


def _bundle(stage: Path, names: list[str], bundle: Path, folder: str, stamp: int) -> None:
    """A zip of `names` under `folder/`, byte-identical for the same files and commit time."""
    date_time = time.gmtime(max(stamp, 315532800))[:6]  # a zip date cannot precede 1980
    with zipfile.ZipFile(bundle, "w") as archive:
        for name in sorted(names):
            info = zipfile.ZipInfo(f"{folder}/{name}", date_time=date_time)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (stage / name).read_bytes(), compresslevel=9)


def _prove(stage: Path, base: Path, patch: dict, built_sha1: str, bundle: Path) -> None:
    """Apply every patch the way a player's `boku apply-patch` does, and read the bundle back."""
    produced = stage / ".release-proof.img"
    try:
        for entry in patch["patches"]:
            try:
                result = apply_patch(base, stage / entry["file"], produced)
            except PatchError as error:
                raise ReleaseRefused(f"{entry['file']} does not apply: {error}") from error
            if result.sha1 != built_sha1:
                raise ReleaseRefused(
                    f"{entry['file']} does not reproduce the built image: applied to the "
                    f"base it gives sha1 {result.sha1}, the build is {built_sha1}"
                )
    finally:
        produced.unlink(missing_ok=True)
    with zipfile.ZipFile(bundle) as archive:
        broken = archive.testzip()
        if broken is not None:
            raise ReleaseRefused(f"{bundle.name} reads back corrupt at {broken}")


def assemble_release(
    *,
    repo: Path,
    base: Path,
    build_dir: Path,
    out_root: Path,
    base_sha1: str = IMAGE_SHA1,
) -> Path:
    """Write `out_root/v<version>/` from HEAD's days build. Returns the directory."""
    require_clean_tree(repo)
    made = revision(repo)
    actual_base = sha1_of(base)
    if actual_base != base_sha1:
        raise ReleaseRefused(
            f"{base} is not the Redump dump a release is made against: sha1 "
            f"{actual_base}, expected {base_sha1} (research/disc-recon.md § 'The dump')"
        )
    image, build_manifest = _built_image(build_dir, made, base_sha1)
    built_sha1 = sha1_of(image)
    if built_sha1 != build_manifest.result_sha1:
        raise ReleaseRefused(
            f"{image} has changed since its build wrote it: sha1 {built_sha1}, the build's "
            f"manifest says {build_manifest.result_sha1}"
        )
    try:
        status = read_status(repo / STATUS_PATH)
    except ReaderRefused as error:
        raise ReleaseRefused(str(error)) from error
    template = (repo / NOTES_TEMPLATE).read_text(encoding="utf-8")
    readme = (repo / "README.md").read_text(encoding="utf-8")

    out_dir = out_root / f"{TAG_PREFIX}{made.version}"
    try:
        check_out_dir(out_dir, manifest_name=RELEASE_MANIFEST, what="release")
    except StagingRefused as error:
        raise ReleaseRefused(str(error)) from error
    stem = patch_stem(made.version)
    bundle_name = f"{TEAM}-{TAG_PREFIX}{made.version}.zip"
    with staged(out_dir, suffix="releasing") as stage:
        try:
            build_patches(base, image, stage, version=made.version, original_name=BASE_NAME)
        except PatchError as error:
            raise ReleaseRefused(str(error)) from error
        patch = json.loads((stage / MANIFEST_NAME).read_text(encoding="utf-8"))
        cue_name = f"{stem}.cue"
        (stage / cue_name).write_text(cue_text(patch["result"]["name"]), encoding="utf-8")
        notes = render_notes(
            template,
            made=made,
            patch=patch,
            build_manifest=build_manifest,
            status=status,
            readme=readme,
            cue_name=cue_name,
            bundle_name=bundle_name,
        )
        (stage / NOTES_NAME).write_text(notes, encoding="utf-8")
        shipped = [entry["file"] for entry in patch["patches"]]
        shipped += [MANIFEST_NAME, README_NAME, cue_name, NOTES_NAME]
        bundle = stage / bundle_name
        commit_time = int(_git(repo, "show", "-s", "--format=%ct", made.commit))
        _bundle(stage, shipped, bundle, stem, commit_time)
        _prove(stage, base, patch, built_sha1, bundle)
        manifest = {
            "format": RELEASE_FORMAT,
            "version": made.version,
            "tag": made.tag,
            "commit": made.commit,
            "build": build_manifest.build_id,
            "title": f"{GAME_NAME}, English v{made.version}",
            "assets": [
                {"file": bundle_name, "size": bundle.stat().st_size, "sha1": hashes_of(bundle).sha1}
            ],
        }
        (stage / RELEASE_MANIFEST).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    return out_dir.resolve()


def main_release(repo: Path, base: Path, build_dir: Path, out_root: Path, preflight: bool) -> int:
    try:
        if preflight:
            require_clean_tree(repo)
            made = revision(repo)
            kind = f"tag {made.tag}" if made.tag else "a snapshot (no version tag on HEAD)"
            print(f"release v{made.version} of {made.commit[:8]}, {kind}")
            return 0
        out = assemble_release(repo=repo, base=base, build_dir=build_dir, out_root=out_root)
    except (ReleaseRefused, OSError, ValueError) as error:
        print(f"boku release: {error}")
        return 1
    manifest = json.loads((out / RELEASE_MANIFEST).read_text(encoding="utf-8"))
    print(f"wrote {out}/")
    for path in sorted(out.iterdir()):
        print(f"  {path.name}  {path.stat().st_size:,} bytes")
    if manifest["tag"]:
        print(f"post it with: ./make.sh publish-release {out}")
    else:
        print("a snapshot: tag the commit v<version> and run ./make.sh release again to publish")
    return 0


# ---------------------------------------------------------------------------
# Publishing


def publish_command(
    release_dir: Path, manifest: dict, github: str, *, draft: bool, prerelease: bool
) -> list[str]:
    """The one `gh` line that posts the release; `--verify-tag` so it attaches only to a tag
    already pushed, never to one gh would create from the default branch's tip."""
    command = ["gh", "release", "create", manifest["tag"]]
    command += [str(release_dir / asset["file"]) for asset in manifest["assets"]]
    command += ["--repo", github, "--verify-tag", "--title", manifest["title"]]
    command += ["--notes-file", str(release_dir / NOTES_NAME)]
    if draft:
        command.append("--draft")
    if prerelease:
        command.append("--prerelease")
    return command


def _publishable(release_dir: Path, git_repo: Path) -> dict:
    manifest_path = release_dir / RELEASE_MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ReleaseRefused(f"no readable {manifest_path}: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("format") != RELEASE_FORMAT:
        raise ReleaseRefused(f"{manifest_path} is not a format-{RELEASE_FORMAT} release manifest")
    absent = [key for key in RELEASE_KEYS if key not in manifest]
    if absent:
        raise ReleaseRefused(f"{manifest_path} has no {', '.join(absent)}; rebuild it")
    tag = manifest["tag"]
    if not tag:
        raise ReleaseRefused(
            f"v{manifest['version']} is a snapshot of an untagged commit. Tag the "
            f"commit (git tag v<version> {manifest['commit'][:8]}), run "
            f"./make.sh release again, and publish that."
        )
    try:
        tagged = _git(git_repo, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
    except ReleaseRefused as error:
        raise ReleaseRefused(f"there is no tag {tag} in this repository") from error
    if tagged != manifest["commit"]:
        raise ReleaseRefused(
            f"tag {tag} is now {tagged[:8]}, and this release was built from "
            f"{manifest['commit'][:8]}; rebuild it"
        )
    if not (release_dir / NOTES_NAME).is_file():
        raise ReleaseRefused(f"{NOTES_NAME} is missing from {release_dir}")
    for asset in manifest["assets"]:
        path = release_dir / asset["file"]
        if not path.is_file() or hashes_of(path).sha1 != asset["sha1"]:
            raise ReleaseRefused(
                f"{path} is missing or has changed since ./make.sh release wrote it; rebuild"
            )
    return manifest


def main_publish(
    release_dir: Path,
    *,
    yes: bool,
    draft: bool,
    prerelease: bool,
    github: str | None,
    git_repo: Path,
    remote: str | None = None,
) -> int:
    """Say what would be posted; post it only with `--yes`.

    `remote` is where the tag is looked up (default: the GitHub repository over https).
    """
    try:
        manifest = _publishable(release_dir, git_repo)
        github = github or github_repo(git_repo)
        if not github:
            raise ReleaseRefused(
                "this repository has no GitHub 'origin' remote; pass --repo OWNER/REPO"
            )
        gh = shutil.which("gh")
        if gh is None:
            raise ReleaseRefused("gh is not on PATH (brew install gh, then gh auth login)")
        tag, commit = manifest["tag"], manifest["commit"]
        pushed = remote_tag_commit(git_repo, remote or f"https://github.com/{github}.git", tag)
        if pushed is not None and pushed != commit:
            raise ReleaseRefused(
                f"tag {tag} on {github} names {pushed[:8]}, and this release was built from "
                f"{commit[:8]}: the release page's source archive would not be this patch's "
                f"source"
            )
        if pushed is None and yes:
            raise ReleaseRefused(f"tag {tag} is not on {github}: git push origin {tag} first")
    except ReleaseRefused as error:
        print(f"boku publish-release: {error}")
        return 1
    command = publish_command(release_dir, manifest, github, draft=draft, prerelease=prerelease)
    visibility = "a draft" if draft else "public"
    print(f"posting {tag} ({commit[:8]}) to {github}, {visibility}:")
    for asset in manifest["assets"]:
        print(f"  {asset['file']}  {asset['size']:,} bytes  sha1 {asset['sha1']}")
    print(f"  notes: {release_dir / NOTES_NAME}")
    if pushed is None:
        print(f"tag {tag} is not on {github} yet: git push origin {tag} before --yes")
    print(shlex.join(command))
    if not yes:
        print("dry run: nothing was posted. Add --yes to post it.")
        return 0
    return subprocess.run([gh, *command[1:]], check=False).returncode


def remote_tag_commit(git_repo: Path, remote: str, tag: str) -> str | None:
    """The commit `tag` names on `remote`, through an annotated tag; `None` when it is absent.

    gh's `--verify-tag` checks only that a tag of that name exists there, not which commit
    it names, so a tag moved locally and never force-pushed would pass it.
    """
    ref = f"refs/tags/{tag}"
    listed = _git(git_repo, "ls-remote", remote, ref, f"{ref}^{{}}")
    pairs = (line.split("\t", 1) for line in listed.splitlines() if "\t" in line)
    refs = {name: sha for sha, name in pairs}
    return refs.get(f"{ref}^{{}}") or refs.get(ref)
