"""The two front documents as GitHub renders them (PLAN `DOC-02`): every relative link and
image of `README.md` and `TECHNICAL.md` names a tracked file, every `#anchor` a heading of its
own document, the README's screenshots are exactly the files `./make.sh screenshots` writes, and
what the README says has been released agrees with its table of versions."""

from __future__ import annotations

import json
import re

import pytest

from boku import REPO_ROOT
from boku.png import read as read_png
from tests.libretro_tools import libretro_tool
from tests.test_make_verbs import CITABLE, document, headings, tracked_files

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)|<(?:img|a)\b[^>]*?\b(?:src|href)=\"([^\"]+)\"")
IMAGE = re.compile(r"<img\b[^>]*>|!\[[^\]]*\]\([^)]*\)")
RELEASES = "../../releases"
"""The repository's Releases page, from a file GitHub shows at `<repo>/blob/<branch>/`: the
one link that leaves the tree, so that the README names no owner or host."""
SHOTS_DIR = "docs/screenshots"
PICTURES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tim")
PICTURE_HOMES = (SHOTS_DIR + "/",)
"""Where a picture may be tracked (CLAUDE.md § "This repo is public"). An English redraw of a
texture would be the other sanctioned kind; the build typesets those, so none is tracked."""


def targets(text: str) -> list[str]:
    return [a or b for a, b in LINK.findall(text)]


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def attribute(tag: str, name: str) -> str:
    found = re.search(rf'\b{name}="([^"]*)"', tag)
    return found[1] if found else ""


@pytest.mark.parametrize("name", CITABLE)
def test_every_relative_link_names_a_tracked_file_or_a_heading(name):
    text = document(name)
    tracked = set(tracked_files())
    directories = {path.rsplit("/", 1)[0] + "/" for path in tracked if "/" in path}
    anchors = {slug(heading) for heading in headings(name)}
    found, broken = targets(text), []
    for target in found:
        if re.match(r"https?://", target) or target == RELEASES:
            continue
        if target.startswith("#"):
            if target[1:] not in anchors:
                broken.append(f"{target}: no such heading")
        elif target not in tracked and target not in directories:
            broken.append(f"{target}: not a tracked file")
    assert found, f"no link found in {name}.md -- the pattern is out of date"
    assert not broken, f"{name}.md: {broken}"


def test_the_readme_shows_the_screenshots_the_verb_writes_and_no_others():
    written = [f"{SHOTS_DIR}/{shot}.png" for shot in libretro_tool("screenshots").SHOTS]
    shown = [attribute(tag, "src") for tag in IMAGE.findall(document("README"))]
    assert shown == written, "the README's images are not ./make.sh screenshots' files, in order"
    tracked = sorted(path for path in tracked_files() if path.startswith(SHOTS_DIR + "/"))
    assert tracked == sorted(written), f"{SHOTS_DIR}/ does not hold exactly what the verb writes"


def test_every_screenshot_has_alt_text_and_is_the_cores_frame_scaled_whole():
    scale = libretro_tool("screenshots").SCALE
    for tag in IMAGE.findall(document("README")):
        src = attribute(tag, "src")
        assert len(attribute(tag, "alt")) > 40, f"{src}: no alt text that describes the screen"
        shot = read_png((REPO_ROOT / src).read_bytes())
        assert int(attribute(tag, "width")) * scale == shot.width, (
            f"{src}: not shown at the width of the frame the core drew"
        )
        rgba, stride = shot.rgba, shot.width * 4
        rows = [rgba[y * stride : (y + 1) * stride] for y in range(shot.height)]
        assert all(rows[y] == rows[y - y % scale] for y in range(shot.height)), (
            f"{src}: not scaled by whole pixels (rows)"
        )
        assert all(
            row[x * 4 : x * 4 + 4] == row[(x - x % scale) * 4 : (x - x % scale) * 4 + 4]
            for row in rows[::scale]
            for x in range(shot.width)
        ), f"{src}: not scaled by whole pixels (columns)"


def test_the_only_pictures_tracked_are_the_readmes_screenshots():
    pictures = [path for path in tracked_files() if path.lower().endswith(PICTURES)]
    stray = [path for path in pictures if not path.startswith(PICTURE_HOMES)]
    assert not stray, f"pictures tracked outside {PICTURE_HOMES} (CLAUDE.md): {stray}"


def test_the_movie_screenshot_is_aimed_at_a_frame_a_subtitle_covers(tmp_path):
    """Against the tracked `translation/movies.txt`, so a retimed cue fails here first."""
    tool = libretro_tool("screenshots")
    assert tool.movie_cue(tool.MOVIE, tool.MOVIE_FRAME)
    cues = tmp_path / "movies.txt"
    cues.write_text(f"{tool.MOVIE}\t{tool.MOVIE_FRAME}\t{tool.MOVIE_FRAME + 40}\tText.\n")
    with pytest.raises(tool.StepError, match="choose another MOVIE_FRAME"):
        tool.movie_cue(tool.MOVIE, tool.MOVIE_FRAME, cues)  # a cue's first frame is its edge
    assert tool.movie_cue(tool.MOVIE, tool.MOVIE_FRAME + 1, cues) == "Text."


def test_a_build_without_the_movie_hook_is_refused_in_words(tmp_path):
    tool = libretro_tool("screenshots")
    edits = tmp_path / "edits.json"
    symbols = {"symbols": {"movie_sub_frame_no": "0x80012E04"}}
    edits.write_text(json.dumps({"movie_subtitles": {"islands": [symbols]}}))
    assert tool.movie_frame_counter(edits) == 0x80012E04
    edits.write_text(json.dumps({"movie_subtitles": {"islands": []}}))
    with pytest.raises(tool.StepError, match="frame counter"):
        tool.movie_frame_counter(edits)
    with pytest.raises(tool.StepError, match="frame counter"):
        tool.movie_frame_counter(tmp_path / "absent.json")
