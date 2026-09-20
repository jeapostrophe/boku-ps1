"""Publishing a directory without ever leaving a half-written one behind.

Four steps of this pipeline produce a directory — the import, the extract, the trial image
and the release patches — and each one had grown its own staging-and-swap dance. This is
the one home for the rules they share, which are all rules about what happens when a run
dies half way:

* **Build beside the destination, never into it.** The destination is replaced whole, so
  nothing is deleted until the replacement exists in full.
* **Refuse a destination that is not this tool's to delete.** A directory holding anything
  other than a previous run of the same kind (recognised by its manifest) is somebody's
  data, and `--out ~/Downloads` must not destroy it.
* **Never write over the source.** `--out disc` would overwrite the one artifact in the
  repo that cannot be regenerated without the contributor's own dump.
* **The completeness marker is renamed last.** A reader that finds the marker has to be
  able to rely on everything it indexes already being there.

`boku.extract` is the odd one out and says why in `staged_inside`: it may only write inside
`disc/script/`, so it stages *inside* its own destination rather than beside it.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class StagingRefused(Exception):
    """The output directory is not one this tool may replace."""


def check_out_dir(
    out_dir: Path,
    *,
    manifest_name: str,
    what: str = "run",
    source: Path | None = None,
    doing: str | None = None,
) -> None:
    """Refuse an output directory whose contents are not this tool's to delete.

    A successful run replaces `--out` wholesale, so pointing it at a directory that holds
    anything else -- `--out ~/Downloads` -- would destroy it. A directory that holds a
    manifest is a previous run of the same kind and may be replaced.

    `source` is a file the run reads; give it and the directory holding it is protected in
    both directions. `doing` names the activity in those two messages when it is not the
    same word as `what` (`boku trial` is a "trial" to replace and a "build" to read).
    Both sides are resolved first: on macOS `/tmp` is a symlink to
    `/private/tmp`, so an unresolved pair of paths to the same directory are not relative
    to each other and the whole guard silently passes.
    """
    if not out_dir.name:
        raise StagingRefused(f"{out_dir} has no name to write into; give --out a directory")
    if source is not None:
        doing = doing or what
        source_dir = Path(source).resolve().parent
        resolved = Path(out_dir).resolve()
        if resolved == source_dir or resolved.is_relative_to(source_dir):
            raise StagingRefused(
                f"--out {resolved} is inside {source_dir}, which holds the image this "
                f"{doing} reads. The {doing} writes a patched copy; putting it there would "
                f"overwrite your verified import, and every test that checks against the "
                f"real disc would silently run on the patched one."
            )
        if source_dir.is_relative_to(resolved):
            raise StagingRefused(
                f"--out {resolved} contains {source_dir}, and a successful {doing} replaces "
                f"--out whole; that would delete your verified import."
            )
    if not out_dir.exists():
        return
    if not out_dir.is_dir():
        raise StagingRefused(f"--out {out_dir} exists and is not a directory")
    contents = list(out_dir.iterdir())
    if contents and not (out_dir / manifest_name).is_file():
        raise StagingRefused(
            f"--out {out_dir} is not empty and holds no {manifest_name}, so it is not a "
            f"previous {what}. A successful {what} replaces this directory whole; refusing "
            f"to delete {len(contents)} item(s) that are not this tool's."
        )


@contextmanager
def staged(out_dir: Path, *, suffix: str) -> Iterator[Path]:
    """Yield a fresh sibling directory; on a clean exit it *becomes* `out_dir`.

    On any exception the staging directory is removed and whatever was at `out_dir`
    before is untouched. The swap goes through a second sibling so that a failure of the
    rename itself can put the previous run back.
    """
    out_dir = Path(out_dir).resolve()
    staging = out_dir.parent / f".{out_dir.name}.{suffix}.{os.getpid()}"
    replaced = out_dir.parent / f".{out_dir.name}.replaced.{os.getpid()}"
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    try:
        yield staging
        if out_dir.exists():
            out_dir.rename(replaced)
        try:
            staging.rename(out_dir)
        except OSError:
            if replaced.exists():
                replaced.rename(out_dir)
            raise
        shutil.rmtree(replaced, ignore_errors=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


@contextmanager
def staged_inside(out_dir: Path, *, suffix: str, marker: str) -> Iterator[Path]:
    """The same, for a step that may only write *inside* its own destination.

    `boku extract` writes `disc/script/` and nothing else under `disc/`, which is the
    contributor's import; so it stages in `disc/script/.building` and moves the finished
    entries up one level. `marker` is the file a reader treats as "this extract is
    complete" and is therefore renamed last, after everything it indexes.
    """
    out_dir = Path(out_dir)
    staging = out_dir / f".{suffix}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        yield staging
        if not (staging / marker).is_file():
            raise StagingRefused(f"{staging} holds no {marker}; nothing was published")
        for stale in sorted(out_dir.iterdir()):
            if stale != staging:
                shutil.rmtree(stale) if stale.is_dir() else stale.unlink()
        produced = sorted(p for p in staging.iterdir() if p.name != marker)
        for entry in [*produced, staging / marker]:
            entry.rename(out_dir / entry.name)
        staging.rmdir()
    finally:
        shutil.rmtree(staging, ignore_errors=True)
