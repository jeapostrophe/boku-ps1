"""Addresses built by `lui`/`addiu` pairs, found and rewritten (`PLAN PIPE-07`).

A code-file text array is reached only through the instructions that build its address:
`lui rX, %hi(array)` then an `addiu`, `ori`, load or store whose immediate is `%lo(array)`
with `rX` -- or a register `addu`'d from it, when the code adds an index first -- as its
base (`research/text-outside-events.md`; no data word points at any array). Moving an
array therefore means rewriting the `lui` and every low half it feeds, and that is only
safe when *every* address the `lui` feeds moves by a rule the caller states.

`scan` follows each `lui` along every control-flow path to its function's `jr`
(`_follow` says why paths and not address order), until the register and every register
derived from it has been overwritten. A use reached only through a `jr` (a jump table) is
not seen. `tests/test_real_pointers.py` holds the scan against an independent count for
27 of the 34 arrays and, for all of them, against every `addiu`/`ori` whose low half is an
array start; a load's low half is not swept there (structure offsets alias array low halves
dozens of times), so an indexed use behind a jump table is the one case nothing checks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

_OP_SPECIAL, _OP_REGIMM, _OP_J, _OP_JAL = 0x00, 0x01, 0x02, 0x03
_OP_ADDIU, _OP_ORI, _OP_LUI = 0x09, 0x0D, 0x0F
_REG_RA = 31
_LOADS_STORES = range(0x20, 0x2F)
_FUNCT_ADD, _FUNCT_ADDU, _FUNCT_JR, _FUNCT_JALR = 0x20, 0x21, 0x08, 0x09
LOOKAHEAD = 256
"""Instructions a `lui` is followed for at most; a function's `jr ra` usually ends it first."""
_CALLER_SAVED = frozenset({1, 2, 3, 4, 5, 6, 7, *range(8, 16), 24, 25})
"""at, v0-v1, a0-a3, t0-t9: what a callee may leave changed."""


class PointerError(Exception):
    """A `lui` whose low halves cannot all be moved consistently."""


@dataclass(frozen=True)
class Use:
    ram: int
    """The instruction holding the low half."""
    target: int
    """The address it forms with the `lui`'s high half."""
    signed: bool
    """`addiu` and loads/stores sign-extend the low half; `ori` does not."""


@dataclass(frozen=True)
class LuiPair:
    """One `lui` and the low halves that complete an address with it."""

    ram: int
    uses: tuple[Use, ...]


def destination(word: int) -> int | None:
    """Which register an instruction writes, or `None` if it writes no general register.

    Only enough of MIPS I to answer *"did this clobber `a0`?"*. Getting that wrong in the
    permissive direction is what made two of the six labels grow a phantom character: a
    literal left in `a0` by a computed store or somebody else's call was then read as the
    argument of a `glyph_draw` dozens of instructions later.
    """
    op = word >> 26
    if op == _OP_SPECIAL:
        funct = word & 0x3F
        if funct == 0x09:  # jalr
            return _REG_RA
        if funct in (0x08, 0x0C, 0x0D, 0x18, 0x19, 0x1A, 0x1B):  # jr, syscall, break, mult/div
            return None
        return (word >> 11) & 0x1F
    if op == _OP_REGIMM:
        return _REG_RA if (word >> 16) & 0x1F in (0x10, 0x11) else None  # bltzal, bgezal
    if op == _OP_JAL:
        return _REG_RA
    if op in (_OP_J, 0x04, 0x05, 0x06, 0x07):  # j and the branches
        return None
    if 0x08 <= op <= 0x0F:  # addi(u), slti(u), andi, ori, xori, lui
        return (word >> 16) & 0x1F
    if 0x10 <= op <= 0x13:  # coprocessor: mfcz/cfcz write rt, mtcz/ctcz do not
        return (word >> 16) & 0x1F if (word >> 21) & 0x1F in (0, 2) else None
    if 0x20 <= op <= 0x26:  # the loads
        return (word >> 16) & 0x1F
    return None


def _s16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def words32(code: bytes) -> list[int]:
    """`code` as little-endian 32-bit instruction words."""
    return [int.from_bytes(code[i : i + 4], "little") for i in range(0, len(code) - 3, 4)]


def _transfer(word: int, index: int, base: int) -> tuple[str, int | None] | None:
    """How `word` at `index` moves the PC once its delay slot has run, or `None`."""
    op = word >> 26
    if op in (0x04, 0x05, 0x06, 0x07) or op == _OP_REGIMM:
        kind = "call" if op == _OP_REGIMM and (word >> 16) & 0x1F in (0x10, 0x11) else "branch"
        return kind, index + 1 + _s16(word & 0xFFFF)
    if op in (_OP_J, _OP_JAL):
        pc = base + 4 * index
        target = ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        return ("jump" if op == _OP_J else "call"), (target - base) // 4
    if op == _OP_SPECIAL and word & 0x3F == _FUNCT_JALR:
        return "call", None
    if op == _OP_SPECIAL and word & 0x3F == _FUNCT_JR:
        return "return", None
    return None


def _follow(words: list[int], start: int, register: int, high: int, base: int) -> tuple[Use, ...]:
    """The uses of the `lui` at `start`, along every path from it to a `jr`.

    Paths, not address order: `item_menu_draw` puts the `lui` in a branch's delay slot and
    completes the address on both sides of the branch, and a use on one side overwrites
    the register only on that side. A call ends what a caller-saved register carries;
    `LOOKAHEAD` bounds the instructions any one path is followed for.
    """
    seen_uses: set[int] = set()
    visited: set[tuple[int, frozenset[int]]] = set()

    def run(index: int, live: set[int]) -> None:
        word = words[index]
        op, rs, rt = word >> 26, (word >> 21) & 0x1F, (word >> 16) & 0x1F
        low = word & 0xFFFF
        use = None
        if op in (_OP_ADDIU, _OP_ORI) and rs in live:
            signed = op == _OP_ADDIU
            use = Use(
                base + 4 * index,
                ((high << 16) + (_s16(low) if signed else low)) & 0xFFFFFFFF,
                signed,
            )
        elif op in _LOADS_STORES and rs in live:
            use = Use(base + 4 * index, ((high << 16) + _s16(low)) & 0xFFFFFFFF, True)
        if use is not None and use.ram not in seen_uses:
            seen_uses.add(use.ram)
            found.append(use)
        written = destination(word)
        if written:
            derived = (
                op == _OP_SPECIAL
                and word & 0x3F in (_FUNCT_ADD, _FUNCT_ADDU)
                and (rs in live or rt in live)
            )
            if derived:
                live.add(written)
            else:
                live.discard(written)

    def successors(index: int, live: set[int]) -> list[tuple[int, set[int]]]:
        """After `index` (a transfer) and its delay slot have run."""
        transfer = _transfer(words[index], index, base)
        if transfer is None:
            return [(index + 1, live)]
        kind, target = transfer
        if kind == "return":
            return []
        if kind == "call":
            return [(index + 2, live - _CALLER_SAVED)]
        if kind == "jump":
            return [(target, live)]
        return [(target, set(live)), (index + 2, set(live))]

    found: list[Use] = []
    live0 = {register}
    before = start - 1
    starts = (
        successors(before, live0)
        if before >= 0 and _transfer(words[before], before, base)
        else [(start + 1, live0)]
    )
    work = [(index, live, 0) for index, live in starts]
    while work:
        index, live, steps = work.pop()
        while live and 0 <= index < len(words) and steps < LOOKAHEAD:
            key = (index, frozenset(live))
            if key in visited:
                break
            visited.add(key)
            run(index, live)
            steps += 1
            if _transfer(words[index], index, base) is None:
                index += 1
                continue
            if index + 1 < len(words):
                run(index + 1, live)  # the delay slot
            nexts = successors(index, live)
            if not nexts:
                break
            for other, other_live in nexts[1:]:
                work.append((other, other_live, steps))
            index, live = nexts[0]
    return tuple(sorted(found, key=lambda use: use.ram))


def scan(code: bytes, base: int) -> list[LuiPair]:
    """Every `lui` in `code` (loaded at `base`) that completes at least one address."""
    words = words32(code)
    out = []
    for i, word in enumerate(words):
        if word >> 26 != _OP_LUI:
            continue
        register, high = (word >> 16) & 0x1F, word & 0xFFFF
        if register == 0:
            continue
        uses = _follow(words, i, register, high, base)
        if uses:
            out.append(LuiPair(base + 4 * i, uses))
    return out


def resolve(code: bytes, base: int, lui_ram: int) -> int:
    """The address the first low half after the `lui` at `lui_ram` forms: an anchor, read."""
    words = words32(code)
    index = (lui_ram - base) // 4
    word = words[index]
    if word >> 26 != _OP_LUI:
        raise PointerError(f"0x{lui_ram:08X} holds {word:#010x}, not a lui")
    uses = _follow(words, index, (word >> 16) & 0x1F, word & 0xFFFF, base)
    if not uses:
        raise PointerError(f"the lui at 0x{lui_ram:08X} completes no address")
    return uses[0].target


def repoint(pair: LuiPair, move: Callable[[int], int], code: bytes, base: int) -> dict[int, int]:
    """New instruction words, by RAM address, that make every use of `pair` form
    `move(target)` instead. Refused when the uses need different high halves -- one of
    them moves and another does not, or they land in different 64 KB windows."""
    moved = {use: move(use.target) for use in pair.uses}
    if all(new == use.target for use, new in moved.items()):
        return {}
    highs = {
        ((new + 0x8000) >> 16) & 0xFFFF if use.signed else (new >> 16) & 0xFFFF
        for use, new in moved.items()
    }
    if len(highs) != 1:
        raise PointerError(
            f"the lui at 0x{pair.ram:08X} feeds "
            + ", ".join(f"0x{use.target:08X} -> 0x{new:08X}" for use, new in moved.items())
            + "; they need different high halves, so the lui cannot serve all of them"
        )
    (high,) = highs
    words = {}

    def word_at(ram: int) -> int:
        at = ram - base
        return int.from_bytes(code[at : at + 4], "little")

    words[pair.ram] = (word_at(pair.ram) & 0xFFFF0000) | high
    for use, new in moved.items():
        words[use.ram] = (word_at(use.ram) & 0xFFFF0000) | (new & 0xFFFF)
    return words
