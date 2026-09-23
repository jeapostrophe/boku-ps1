"""Every glyph the code can draw is protected by one gate or the other (`PLAN TXT-05`).

The font build redraws only cells nothing draws. Two gates decide "nothing": the text-site
index (every glyph of every message, select and array of the import) and `code_glyph_ids`
(every id the code proves a `jal glyph_draw` gets, on every path into it). What neither sees
is a draw whose `a0` the code does not prove -- the "23 computed-id sites" `research/font.md`
left open. So every such site is named here, one by one, with what its function walks, and
each name is checked: an array's line ids must be in the site index, `messages` means event
text (in the index), `callers` a wrapper that passes on the id its callers chose (each caller
is its own site). A new unproven site, or one of these proven, fails the test and has to be
read before it is added. What this cannot check: that a function walks nothing BUT the
arrays named -- that is the reading the names record (`research/text-outside-events.md`
§ "Readers", `research/text-renderer.md` § 3).
"""

from __future__ import annotations

import pytest

from boku.arrays import read_code_labels
from boku.text import SiteIndex
from tests.test_vwf_prototype import NEEDS_IMPORT, vwf_prototype

pytestmark = NEEDS_IMPORT

EXE = "SCPS_100.88"
ITEM_NAMES = ("exe@80046214", "exe@800461CC", "exe@80046364", "exe@8004636C")
FISHING = ("exe@8004637C", "exe@80046384", "exe@80046390")
DESCRIPTIONS = ("exe@80046398", "exe@80046614", "exe@800462C8", "exe@800462E4")
SELECTS = ("exe@80046158", "exe@80046178", "exe@800461BC", "hhon@6874", "zukan@32E8")

UNPROVEN: dict[tuple[str, int], tuple[str, ...]] = {
    (EXE, 0x8002BA0C): ("callers",),  # glyph_draw_layer
    (EXE, 0x8002BF54): ("messages", "exe@80029AFC"),  # dialog_draw, and the ant count
    (EXE, 0x8002C2C8): ("messages", *SELECTS, "tako@4", "musi@4"),  # select_draw
    (EXE, 0x800353CC): ("exe@80029B20",),  # text_draw_right: controls help
    (EXE, 0x80035488): ("exe@80029B20",),  # help_line_draw
    (EXE, 0x80037B18): ("exe@8003D2E0",),  # sysmsg_draw across: an insect name, 13 -> 14
    (EXE, 0x80037B60): ("exe@8003D2E0",),  # sysmsg_draw down
    (EXE, 0x8003A8C8): ("exe@80036750",),  # fortune_draw
    (EXE, 0x8003C698): ("exe@8003DA4C",),  # sys_title_draw: fish names
    (EXE, 0x8004382C): (*ITEM_NAMES, *FISHING),  # text_draw_line_h
    (EXE, 0x8004389C): (*DESCRIPTIONS, "exe@80046314", "exe@80046334"),  # text_draw_h
    ("TITLE.OVL", 0x8007CDD0): ("exe@8003D5F0",),  # memory-card messages
    ("TITLE.OVL", 0x8007D034): ("title@7A78",),  # the two answers
    ("TITLE.OVL", 0x8007FBBC): ("exe@8003D9BC",),  # config labels
    ("TITLE.OVL", 0x80080450): ("exe@8003DA00",),  # summer-memories label 5
    ("TITLE.OVL", 0x80080788): ("exe@8003DA00",),  # summer-memories labels 0-4
    ("TAKO.OVL", 0x8007C718): ("tako@440",),  # the crash banner
    ("MUSI.OVL", 0x8007C708): ("musi@348",),  # the button hint
    ("MUSI.OVL", 0x8007EE24): ("musi@358",),  # strength labels, rows 0-1
    ("MUSI.OVL", 0x8007EE80): ("musi@358",),  # strength labels, row 2
    ("MUSI.OVL", 0x80085098): ("musi@2C",),  # move names
    ("MUSI.OVL", 0x80085200): ("musi@2C",),
    ("HHON.OVL", 0x8007C220): ("hhon@5328",),  # the hub's notebook page
    ("HHON.OVL", 0x8007C2BC): ("hhon@5328",),  # the grid
}


@pytest.fixture(scope="module")
def sites(archive):
    return vwf_prototype().glyph_draw_sites(archive)


def test_every_unproven_glyph_draw_is_named_here(sites):
    unproven = {(site.image, site.ram) for site in sites if site.ids is None}
    new, gone = unproven - set(UNPROVEN), set(UNPROVEN) - unproven
    assert not new and not gone, f"new: {sorted(new)}; proven now: {sorted(gone)}"


def test_what_each_unproven_draw_walks_is_in_the_site_index(site_index: SiteIndex):
    ids = {entry.site.line_id for entry in site_index.placed}
    arrays = ids | {line_id.rpartition(".")[0] for line_id in ids}  # a select is one id
    messages = any(entry.site.is_message for entry in site_index.placed)
    for site, sources in UNPROVEN.items():
        for source in sources:
            if source == "messages":
                assert messages, site
            elif source != "callers":
                assert source in arrays, f"{site}: {source} is not in the site index"


def test_the_save_date_s_first_id_is_proven_at_its_draw(sites):
    """`save_date_draw` sets its first id twenty instructions above the draw, past arithmetic."""
    (site,) = [s for s in sites if (s.image, s.ram) == ("TITLE.OVL", 0x8007BBDC)]
    assert site.ids == {(0x3C, 1)}


def test_every_code_label_id_is_a_code_glyph_id(archive):
    """Two resolvers of what code passes `glyph_draw` agree: `boku.arrays`' label reader
    (forward from each literal, per function) and the scanner (back from each draw)."""
    labels = {i for label in read_code_labels(archive) for i in label.glyph_ids}
    missing = labels - vwf_prototype().code_glyph_ids(archive)
    assert labels and not missing, f"label ids the scanner does not prove: {sorted(missing)}"
