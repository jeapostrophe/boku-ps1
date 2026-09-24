"""The encyclopedia spreads drawn in textures: the insect book and the kite book (PLAN `GFX-06`).

Every field of a page is pixels. Its English is `mzkan@<n>.<field>` (insect page n: `name`,
`family`, `size`, `food`, `body`) and `tzkan@<n>.<field>` (kite page n: `name`, `level`,
`body`) in `translation/textures/books.txt`; a page takes all its fields or none, and the
family builds the pages it is given. Where each area is, how it is cleared and what is set in
it: `research/texture-recipes.md` § "The books". A page whose English does not fit its areas
is refused, never cut.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from boku import texture_paint as paint
from boku.archive import Archive
from boku.reinsert import ByteEdit
from boku.texture_buttons import saturation
from boku.textures import Inventory
from boku.tim import luminance
from boku.typeset import Face, pixel_face, wrap

from boku.texture_text import (  # isort: skip
    Entry, TextureTextError, found, ink_of, keyed,
)  # fmt: skip

INSECT = "mzkan@"
KITE = "tzkan@"
INSECT_PACKS = ("_DATA_MZKAN1.BIN", "_DATA_MZKAN0.BIN")
"""The same nine spreads lit for day (`MZKAN1`) and for night (`MZKAN0`), in the same order:
each English page is set into page n of both."""
KITE_PACK = "_DATA_TZKAN.BIN"
INSECT_FIELDS = ("name", "family", "size", "food", "body")
INSECT_HEADER_FIELDS = ("family", "size", "food")
KITE_FIELDS = ("name", "level", "body")
BODY_FACE = "bean"
INK = 110
"""Luminance under which a pixel of a text area is the Japanese's ink."""
FURNITURE = 60
"""Saturation over which a pixel is the page's furniture -- a green rule, the photograph's
colour -- which no text area may take in, and which no mark cleared may touch."""
INSET = 4
"""Paper left at each side of a left-aligned body line."""
GAP = 2
"""How far apart two strokes of one glyph may be."""
PAPER_SHARE = 0.03
"""An entry covering this share of a name or header box is the page's paper there."""
MARK = 20
"""How much darker than its column's paper a pixel is to be a mark of the Japanese."""
LEVEL_GAP = 4
"""Rows between a kite's difficulty and its body."""
FIRST_ROW = 1
"""Rows of paper above the first line set in an area."""


@dataclass(frozen=True)
class Area:
    box: paint.Box
    reach: int = 0
    """Rows above and below `box` whose Japanese `clear_body` also clears."""


INSECT_NAME = Area((140, 12, 111, 13))
"""The species name, across the diagonal edge of the grey curl at the right page's top."""
INSECT_HEADER = Area((140, 27, 108, 60))
"""Family, size and food, one centred paragraph each, above the green rule."""
INSECT_BODY = (Area((8, 96, 120, 77), reach=12), Area((130, 95, 118, 78), reach=12))
"""The body's two pages: under the photograph, whose lower edge slopes down to row 95 and on
which the Japanese starts, and under the rule, down to the rules at the pages' foot."""
KITE_TEXT = Area((106, 13, 134, 159), reach=4)
"""The right page, and the column of the left page the Japanese runs on to; the kite's
picture is left of it."""
KITE_SET = (128, 14, 110, 156)
"""Where the English goes on a kite page: the right page's paper."""


def pages(inv: Inventory, pack: str) -> list:
    """`pack`'s spreads in the order they are stored (the ids end in the fixed-width offset)."""
    return sorted((t for t in inv.textures if t.id.startswith(pack + "__")), key=lambda t: t.id)


def _ink(canvas: paint.Canvas, box: paint.Box, what: str) -> int:
    """Refuse a box that takes in furniture; the entry the Japanese's ink in it used most."""
    palette = canvas.palette(0)
    points = paint.points(box)
    furniture = [p for p in points if saturation(palette[canvas.at(p, stock=True)]) > FURNITURE]
    if furniture:
        raise TextureTextError(
            f"{what}: the area {box} takes in {len(furniture)} pixel(s) of the page's furniture "
            f"(a rule, the photograph), first {sorted(furniture)[:3]}"
        )
    ink = found({p for p in points if luminance(palette[canvas.at(p, stock=True)]) < INK}, what)
    return canvas.most_used(ink, stock=True)


def clear_body(canvas: paint.Canvas, area: Area, what: str) -> int:
    """Blank `area.box` whole, each column to the paper it shows most (white, shaded only
    toward the spine), and clear the Japanese running out of it up to `area.reach` rows
    above and below: marks darker than the paper, paper all round, within `GAP` of the box or
    of a stroke already found. A group touching the photograph or a rule is the page's and
    stays. The entry the Japanese's ink used most."""
    ink_index = _ink(canvas, area.box, what)
    palette = canvas.palette(0)
    x0, y0, w, h = area.box

    def colour(p):
        return palette[canvas.at(p, stock=True)]

    paper = {}
    for x in range(x0, x0 + w):
        pale = [canvas.at((x, y), stock=True) for y in range(y0, y0 + h)
                if luminance(colour((x, y))) >= INK]  # fmt: skip
        if not pale:
            raise TextureTextError(f"{what}: column {x} of {area.box} shows no paper")
        paper[x] = Counter(pale).most_common(1)[0][0]

    def mark(p) -> bool:
        return luminance(colour(p)) < luminance(palette[paper[p[0]]]) - MARK

    top, bottom = max(0, y0 - area.reach), min(canvas.height, y0 + h + area.reach)
    japanese: set = set()
    loose = []
    for group in paint.groups({p for p in paint.points((x0, top, w, bottom - top)) if mark(p)}):
        if all(y0 <= y < y0 + h for _, y in group):
            japanese |= group
        elif all(
            x0 <= q[0] < x0 + w and 0 <= q[1] < canvas.height and not mark(q)
            and saturation(colour(q)) <= FURNITURE
            for q in paint.grown(group, 1, 1, 1, 1) - group
        ):  # fmt: skip
            loose.append(group)
    near = set(paint.points(area.box)) | japanese
    while joined := [g for g in loose if paint.grown(g, GAP, GAP, GAP, GAP) & near]:
        for g in joined:
            loose.remove(g)
            japanese |= g
            near |= g
    for x, y in near:
        canvas.pixels[y * canvas.width + x] = paper[x]
    return ink_index


def clear_heading(canvas: paint.Canvas, box: paint.Box, what: str) -> int:
    """Refill every pixel of `box` that is not one of its paper entries (`PAPER_SHARE`: white
    and the curl's grey) from the nearest that is -- the name and header straddle the curl's
    diagonal edge, so a column is not one paper. The entry the Japanese's ink used most."""
    ink_index = _ink(canvas, box, what)
    palette = canvas.palette(0)
    points = paint.points(box)
    counts = Counter(canvas.at(p, stock=True) for p in points)
    papers = {i for i, n in counts.items()
              if n >= PAPER_SHARE * len(points) and luminance(palette[i]) >= INK}  # fmt: skip
    mask = {p for p in points if canvas.at(p, stock=True) not in papers}
    left = canvas.fill_from_nearest(mask, set(points) - mask)
    if left:
        raise TextureTextError(f"{what}: {len(left)} pixel(s) had no paper near, {left[:3]}")
    return ink_index


def capacity(box: paint.Box, face: Face) -> int:
    """Lines of `face` a left-aligned area holds from `FIRST_ROW` down (`set_lines`' test)."""
    return (box[3] - FIRST_ROW - face.cell) // face.pitch + 1


def set_lines(canvas, face: Face, lines: Sequence[str], entry: Entry, box, top: int, ink: int,
              align: str, what: str) -> int:  # fmt: skip
    """Set `lines` from row `top` of `box`, `face.pitch` apart; the row after the last. A line
    wider than the box, or one past its foot, is refused."""
    x0, y0, w, h = box
    room = w - (0 if align == "centre" else 2 * INSET)
    for line in lines:
        if not line:
            continue
        width = face.measure(line)
        if width > room or top + face.cell > y0 + h:
            raise TextureTextError(
                f"{entry.where}: {what} has no room for {line!r} ({width} px at row {top}; the "
                f"area is {w}x{h} from row {y0}); nothing is cut to fit (README)"
            )
        x = x0 + (w - width) // 2 if align == "centre" else x0 + INSET
        canvas.stamp((x, top), ink_of(face, entry, line), ink)
        top += face.pitch
    return top


def insect_page(canvas: paint.Canvas, fields: dict[str, Entry], game: Face, what: str) -> None:
    bean = pixel_face(BODY_FACE)
    name = fields["name"]
    ink = clear_heading(canvas, INSECT_NAME.box, f"{what} name")
    _, y0, w, h = INSECT_NAME.box
    face = game if game.measure(name.text) <= w else bean  # Bean where the band has no room
    set_lines(canvas, face, [name.text], name, INSECT_NAME.box, y0 + (h - face.cell) // 2 + 1,
              ink, "centre", f"{what} name")  # fmt: skip
    ink = clear_heading(canvas, INSECT_HEADER.box, f"{what} header")
    top = INSECT_HEADER.box[1] + FIRST_ROW
    for key in INSECT_HEADER_FIELDS:
        entry = fields[key]
        lines = wrap(entry.text, bean, INSECT_HEADER.box[2])
        top = set_lines(canvas, bean, lines, entry, INSECT_HEADER.box, top, ink, "centre",
                        f"{what} header")  # fmt: skip
    body = fields["body"]
    inks = [clear_body(canvas, area, f"{what} body") for area in INSECT_BODY]
    width = min(area.box[2] for area in INSECT_BODY) - 2 * INSET
    lines = wrap(body.text, bean, width)
    per_page = [capacity(a.box, bean) for a in INSECT_BODY]
    if len(lines) > sum(per_page):
        raise TextureTextError(
            f"{body.where}: the body is {len(lines)} lines of Bean and the spread holds "
            f"{sum(per_page)}; nothing is cut to fit (README)"
        )
    for area, ink, share in zip(INSECT_BODY, inks, (lines[: per_page[0]], lines[per_page[0] :]),
                                strict=True):  # fmt: skip
        set_lines(canvas, bean, share, body, area.box, area.box[1] + FIRST_ROW, ink, "left",
                  f"{what} body")  # fmt: skip


def kite_page(canvas: paint.Canvas, fields: dict[str, Entry], game: Face, what: str) -> None:
    bean = pixel_face(BODY_FACE)
    ink = clear_body(canvas, KITE_TEXT, what)
    name, level, body = fields["name"], fields["level"], fields["body"]
    top = KITE_SET[1]
    top = set_lines(canvas, game, wrap(name.text, game, KITE_SET[2]), name, KITE_SET, top, ink,
                    "centre", what)  # fmt: skip
    top = set_lines(canvas, bean, [f"[{level.text}]"], level, KITE_SET, top, ink, "centre", what)
    set_lines(canvas, bean, wrap(body.text, bean, KITE_SET[2] - 2 * INSET), body, KITE_SET,
              top + LEVEL_GAP, ink, "left", what)  # fmt: skip


def book(namespace: str, packs, names, recipe):
    def build(archive: Archive, inv: Inventory, game: Face, entries: Sequence[Entry]):
        spreads = {pack: pages(inv, pack) for pack in packs}
        count = len(spreads[packs[0]])
        by_page: dict[str, list[Entry]] = defaultdict(list)
        for entry in entries:
            by_page[entry.id.removeprefix(namespace).split(".", 1)[0]].append(entry)
        edits: list[ByteEdit] = []
        for page, group in sorted(by_page.items()):
            if not page.isdigit() or page != str(int(page)) or not 0 <= int(page) < count:
                raise TextureTextError(
                    f"{group[0].where}: there is no page {page} of {namespace} (0-{count - 1})"
                )
            fields = keyed(f"{namespace}{page}", group, names)
            for pack in packs:
                texture = spreads[pack][int(page)]
                canvas = paint.Canvas(texture)
                recipe(canvas, fields, game, f"{texture.id} (page {page})")
                edits += canvas.patches()
        return edits

    return build


insect_book = book(INSECT, INSECT_PACKS, INSECT_FIELDS, insect_page)
kite_book = book(KITE, (KITE_PACK,), KITE_FIELDS, kite_page)
