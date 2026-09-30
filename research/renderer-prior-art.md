# Renderer prior art — how the family solved vertical text and variable widths

> **What this is.** PLAN `RSH-02`: a full read of the primary sources on PS1/PS2/PSP text-renderer
> hacking, reduced to what applies to *our* target — R3000, PsyQ-era libs, a 512 KB PS-X EXE
> (`SCPS_100.88`), one headerless 104 MiB archive (`BOKU.BIN`) indexed from the EXE, text stored as
> `u16` glyph indices with `0x8000`-range control codes, and dialogue drawn **vertically** in fixed
> boxes that must end up horizontal and variable-width.
>
> **Who it is for.** The agent doing PLAN `TXT-01`…`TXT-05`. It is written as a set of methods in the
> order you would apply them, not as a survey. It does not repeat
> [`research/ps1-translation-practice.md`](ps1-translation-practice.md) or
> [`research/related-projects.md`](related-projects.md); §7 lists where this reading **contradicts or
> sharpens** those two.
>
> **Marks.** `[SRC]` = read in the source or transcript, cited by video timestamp or file + symbol.
> `[INF]` = my inference from what I read. Nothing here is a measurement of *our* disc — every
> claim about `SCPS_100.88` is a hypothesis until `TXT-01` checks it.
>
> **Sources read in full.** Hilltop, *How to Romhack: Mega Man Legends 2* (`reference/hilltop-mml2-ts.txt`);
> Hilltop, *Racing Lagoon Hacking Deep Dive* (`reference/hilltop-racing-lagoon-ts.txt`); Hilltop,
> *An introduction to hacking video games with Ghidra* (`reference/hilltop-ghidra-intro-ts.txt`);
> Hilltop, *An exhaustive look at extracting graphics from PS1 and PS2 games* — skimmed for the text
> and VRAM sections (`reference/hilltop-ps1-graphics-ts.txt`); slowbeef, `pnhack1`, `pnhack2`,
> `pnhack4`, `pnhack5` + LP Archive Update 50; GriffithVIII, *Mis primeras vacaciones de verano*
> (tradusquare.es, 2025-06-19, Spanish); `HilltopWorks/BokuNoNatsuyasumi2` (`scps_150.26.asm`,
> `asm_notes.txt`); `HilltopWorks/Mega-Man-Legends-2-Demo` (`SLPS_021.09.asm`);
> `Illidanz/PoPoTranslation` (`bin_patch.asm`, **MIT**); `KendritPy/Boku_ESP_JP`
> (`docs/boku-dialogue-format.md`, **MIT**).
> **Could not reach:** slowbeef's `pnhack3`, `pnhack6`, `pnhack7` — `pnhack3` 404s at the origin and
> the Wayback Machine has no usable capture of 6 or 7 (see §7, item 7).
>
> **Licence discipline.** Every HilltopWorks repo is unlicensed (all rights reserved). Techniques,
> symbol names and one-to-three-instruction excerpts are cited below; nothing is pasted in bulk, and
> our patches must be written from the description, not transcribed. `PoPoTranslation` and
> `Boku_ESP_JP` are MIT and may be quoted more freely — they still are not, here.
>
> Clones live in the gitignored `reference/repos/`. Re-clone to follow a citation.

---

## 1. Finding a PS1 text renderer, and its advance and line-step, in the order you would do it

This is the method the sources converge on. Steps 1–4 are cheap and answer "what kind of renderer is
this"; steps 5–8 are where the actual advance and line-step fall out.

### 1.1 First decide which of three renderer families you are in — it changes everything downstream

`[SRC]` Hilltop names all three across the videos, and the classification decides your whole strategy:

| Family | Tell | Where the advance lives |
|---|---|---|
| **BIOS kanji font** | the code calls `Krom2RawAdd` (BIOS `B(51h)`), or reads `0xBFC6xxxx` directly | inside the game's own copy loop; you usually replace the whole renderer |
| **Glyph sheet, sprite per glyph** | computes `u = (code % COLS) * W`, `v = (code / COLS) * H` and emits one textured primitive per character | a constant added to a cursor register, **or** the return value of the per-character function |
| **Glyph sheet, VRAM composition** | calls `MoveImage` (GP0 `80h`, VRAM→VRAM) per glyph to build a string into a scratch VRAM rect, then draws that rect once | a constant added to a destination-X between `MoveImage` calls |

`[SRC]` Hilltop, Ghidra intro [33:26]–[34:27]: for the BIOS-font case the trace is mechanical — xref
`Krom2RawAdd`, and *"a function will in theory call this krom to raw ad and then it will perform some
sort of memory to vram copy where it copies first from the bios to memory and then it uploads that
character from memory into vram."* He did exactly this for *b.l.u.e. Legend of Water* and ended up
replacing the BIOS font and the renderer together, which also let him drop the encoding from two
bytes per character to one.

`[INF]` For us the sheet families are far more likely than the BIOS family: our text is already
`u16` glyph indices, not Shift-JIS, and `research/related-projects.md` §4 records one TIM inside
`SCPS_100.88` and 2606 inside `BOKU.BIN`. A BIOS-font game would not need a sheet. But check
`Krom2RawAdd` anyway — it is one xref and it costs nothing, and *some* surface (a debug overlay, the
memory-card screen) may still use it.

### 1.2 Get a known line on screen and find it in RAM — twice, before and during

`[SRC]` slowbeef, `pnhack1`–`pnhack2`. The method is savestate hacking, and the non-obvious part is
that **you need two savestates**, not one:

* A savestate taken **while the text is on screen** shows you the *decoded, in-memory* form. This is
  the form the drawing code consumes. slowbeef: *"Sometimes the text is stored compressed or in a
  format you just can't find. Taking the savestate during shows you the text when it's in an
  uncompressed format."*
* A savestate taken **just before the text appears** (after the previous box is gone) is the one you
  can *edit* and see the change. Editing the "during" state does nothing, because the game has
  already read the buffer and drawn from it. slowbeef spent real time on this trap.

`[SRC]` `pnhack2` also records the pSX savestate-header offset quirk — the emulator prepends a
variable header (his was `0x2B0`, elsewhere `0x350`), so file offset minus header = RAM address. Any
emulator you use will have its own; measure it once by finding the `RAM` marker rather than assuming.
`[INF]` With PCSX-Redux this is moot — its web API serves raw RAM at `GET /api/v1/cpu/ram/raw`
(`research/ps1-translation-practice.md` §4.3), so you get the address space directly with no header
arithmetic. Prefer that.

### 1.3 Break on the *read*, not the write, to land in the renderer

`[SRC]` slowbeef used a **write** breakpoint on the decoded buffer to find the *decoder*
(`pnhack2`) — the loop he landed in read encoded bytes from one pointer and stored ASCII to another,
and the entire "decoder" turned out to be one `subu` instruction that negates the byte. Useful, but
it finds the decoder.

`[SRC]` Hilltop, MML2 [39:28]: *"We can put a **load** breakpoint on the text and when we do that and
when that breakpoint triggers when the text is being read the emulator will break on this function."*
That is the one that lands you in the renderer. Same tool, opposite direction:

* **write** breakpoint on the decoded text buffer → the decoder / loader
* **read** breakpoint on the decoded text buffer → the renderer
* **write** breakpoint on the glyph sheet's VRAM staging area → a VRAM-composition renderer
* **read** breakpoint on the width/advance constant, once you have a candidate → every call site that
  shares it (this is how you find the *other* text surfaces, §4)

`[SRC]` Hilltop, Ghidra intro [14:30]: the same "break right when the uncompressed data is written,
then rewind" trick finds decompressors, and he notes the trajectory is always disc → memory
(compressed) → memory (decompressed) → VRAM, so you can pick your breakpoint by deciding which leg
you want.

### 1.4 Complementary route from the output: read the GPU command stream

`[SRC]` Hilltop, graphics video [87:18]–[88:41]. Stepping the GPU command log, a single text glyph
appears as a small textured blend primitive; he reads the dimensions straight out of the packet
(*"the final line of the GPU instruction is a 18 and then 18 well 18 is in hex is 24"*), plus the UV
coordinates, the texture page and the CLUT being applied. PCSX-Redux's GPU logger does this and works
with the dynarec on, so it is cheap to run.

`[INF]` For us this is the fastest way to answer the *first* question — **is a dialogue glyph one
primitive, or is the whole box one primitive?** One small textured quad per character ⇒ sprite-per-glyph
family (BnN2-PS2's shape); one big quad whose texture is a scratch VRAM rect ⇒ VRAM-composition family
(PopoloCrois's shape). You do not need Ghidra to answer that, and the answer picks your VWF design
in §3.

`[SRC]` GriffithVIII did the PSP equivalent first, before touching code at all: *"utilicé el depurador
gráfico que viene en el emulador PPSSPP"* — and the thing the graphics debugger told him was not the
glyph code but that **the text box's screen position was tied to the text position** (*"estaba atado
a la posición del texto"*). That is a structural fact you want *before* you start moving text, because
it means the box follows your changes rather than needing a second patch.

### 1.5 The texture-page trap, before you plan a replacement sheet

`[SRC]` Hilltop, graphics video [85:31]–[86:23]: PS1 VRAM is divided into 32 texture pages and a
primitive cannot cross a page boundary — *"the GPU can only really work on one texture page at a
time"*. He hit this on a real translation: *"I kept trying to load you know different text images from
different texture pages and it just didn't work at all and I couldn't really figure out why."*

`[INF]` Directly binding on us. If the English sheet is bigger than the Japanese one (TECHNICAL § "The central risk", fallback
2, a replacement OFL glyph sheet), the first constraint is not disc space, it is that **every glyph a
single draw call reaches must sit inside one texture page**. Check the existing sheet's page
placement in the VRAM viewer before designing the replacement, and treat "how many glyphs fit in a
page at our bit depth" as a hard budget.

### 1.6 In Ghidra: the three features that do the work

`[SRC]` Hilltop, Ghidra intro. Setup he states explicitly: install the platform extension first
(it sets the load address and the CPU and identifies PsyQ library symbols for you), then import,
then analyse **with "aggressive instruction finder" ticked** despite the warning [5:55], then
*"select them all and hit delete"* on the auto-generated bookmarks [6:44]. Then:

1. **References / xrefs** [18:21]–[19:32] — *"the most powerful and important feature"*: for any
   address Ghidra tracks every instruction that reads or writes it, and for any function every call
   site. This is how you go from "the advance constant" to "every text surface in the game" (§4), and
   from `Krom2RawAdd` to the renderer.
2. **Edit function signature** [17:32]–[17:55] — Ghidra gets parameter lists wrong constantly and you
   fix them by hand. This matters enormously for us: the BnN2 print routine's *last* parameter is the
   text direction (§2), and you will not see that until the signature is right.
3. **Call trees** [22:37] — load the renderer, expand all, and you have the inventory of everything
   that feeds it.

`[SRC]` Two gotchas he states: Ghidra's main release *"does not have very good support for searching
for non-ASCII strings"* [23:31], and **re-analysing your own patched binary is a verification step** —
he decompiles his own armips output to check it does what he meant [35:51]. `[INF]` That second one is
a cheap gate for us and should be in the build: assemble, re-import, read the decompilation of the
patched region.

`[SRC]` Also useful and easy to forget: **scalar search** [24:22] — if you have a number (a fixed
glyph advance, a line cap, a box width), search for instructions that use it as an immediate. Hilltop
calls it a long shot that *"really saved me a couple times"*. `[INF]` For us it is not a long shot: once
the VWF pass has told us the fixed advance (`0x10` on PSP, `0xC` on MML2, see §2), a scalar search for
that immediate is a direct index of candidate advance sites.

### 1.7 Recognising the advance and the line-step once you are in the routine

Three shapes, and the third is the one the existing research under-describes:

* **`addiu cursor, cursor, WIDTH`** — the cursor register is incremented by a constant. BnN2's
  dialogue advance lives here (`set_kerning`, `scps_150.26.asm`), as do its many menu sites
  (`addiu s1, s1, mfw`, `addiu s2, s2, mfw`).
* **`li reg, WIDTH`** — a constant loaded into a register that is added elsewhere. BnN2's
  `set_spacing` (newline distance) and `mfw` menu-width sites.
* **The width is the *return value* of the per-character print function.** `[SRC]` Hilltop, MML2
  [40:22]: *"the return value for this function which prints a single character is the width of that
  character and it's being set right here."* In `Mega-Man-Legends-2-Demo/SLPS_021.09.asm` the whole
  VWF is a hijack of the tail of that function that sets `t3` — the return register — and the
  two-byte-character path keeps the original constant `li t3, 0xC`. `[INF]` This shape hides from a
  scalar search on the *cursor*, because the cursor addition is in the caller and takes a register,
  not an immediate. If you do not find an immediate advance, look for a per-character function whose
  return value the caller adds to X.

**The line-step is a separate constant and a separate site.** `[SRC]` BnN2 keeps `font_spacing equ 0xD`
(dialogue newline distance, written at `set_spacing`) distinct from the per-glyph advance at
`set_kerning`, and separately from `vert_menu_y_dist equ 0xF` and the menu `mfw equ 0xa`. In a vertical
renderer the *line* step moves the **column**, i.e. it is applied to X; the *glyph* step is applied to Y.
`[INF]` So the sanity check that you have found the right pair, in our vertical game, is: **the
per-glyph step should be on Y and the per-newline step should be on X, and the newline step should be
larger** (a column gap is wider than a character step). If you find them the other way round, the
surface you are looking at is already horizontal — which, per §2, is entirely possible.

### 1.8 Finding the text itself, if you do not already have it

`[SRC]` Hilltop, MML2 [24:55]–[26:19] and Racing Lagoon [11:23]: **relative searching with Monkey-Moore**,
seeded from the *font sheet order* rather than from a guess. You extract the sheet, read the glyph
order off it left-to-right top-to-bottom, put that order in one field and a sample line from the game
in the other, and the tool reports the encoding — e.g. that space is `0x4C` because space is the 76th
cell. Wildcards on for two-byte encodings. Racing Lagoon needed thousands of characters transcribed
by hand; BnN2 avoided that with `FontRecognizer.java` + KanjiTomo OCR.

`[INF]` We are ahead of this: `research/disc-recon.md` already decodes the script with pleonex's PSP
table. The value of relative search for us is as an **independent check on the table**, not as the
primary route — and the moment a glyph is wrong, the sheet order is what adjudicates.

---

## 2. What "vertical → horizontal" actually cost, as patterns to grep for in our EXE

This is the section that most changes how `TXT-01` should be planned, because **the cost is not one
thing.** In both family members the conversion split into two very different jobs.

### 2.1 BnN2 (PS2): the main dialogue renderer was a genuine rewrite

`[SRC]` `BokuNoNatsuyasumi2/asm_notes.txt` preserves the original routine beside the replacement, and
`scps_150.26.asm` ships the replacement. The shape:

* The original per-glyph drawing routine spans `draw_dialogue_char_start` … `draw_dialogue_char_end`
  in `scps_150.26.asm`. It is **replaced wholesale** — armips `.area` covers exactly that span, the
  first instruction becomes a jump to `font_loop`, and the real body is relocated to
  `text_loop_space`, labelled in-file as *free debug text space*.
* The rotation itself is one instruction. `asm_notes.txt` shows the original computing the
  **column** position as `subu s2, a2, v0` with `a2 = base_x` and `v0 = newlines*spacing` — i.e.
  `base_x − newlines×spacing`, columns marching **leftwards**, the classic Japanese layout. The hack
  is `addu s2, a2, v0` with `a2 = base_y` — rows marching **downwards**.
* But the one instruction is not the work. Everything downstream of `s2` had to be re-targeted,
  because `s2` changed meaning from "this glyph's X" to "this glyph's Y". In the original, `s2` feeds
  the `sh` stores at packet offsets `0x10` (x) and `0x20` (x_right), and the *running cursor* `s4`
  feeds `0x12` (y) and `0x22` (y_bottom). In `font_loop` those are swapped: `s2` feeds `0x12`/`0x22`
  and the cursor (`curr_x equ s4`) feeds `0x10`/`0x20`.
* The two helpers that convert to framebuffer coordinates, `get_fb_x` (`0x0012D390`) and `get_fb_y`
  (`0x0012D3C8`), are swapped at each `jal` for the same reason. `[INF]` These are the functions
  handling the PS2's double-buffer offset; the PS1 equivalent is whatever adds the current display
  area origin, and it will be one of the first things you meet in our routine.
* Constants that had to be re-derived because the axes swapped: `base_x equ 0x330`, `base_y equ 0xAA`,
  `font_spacing equ 0xD` (newline distance), `text_padding equ 2`.
* Separately, `set_x_top` and `set_x_top_2` — *"Set base x after newline"* — reset the cursor to
  `base_x` at each line break. In the original these reset the *column* origin; horizontally they
  reset the left margin. Two sites, both needed.

**Grep patterns for our EXE, in order of value** `[INF]`, derived from the above:

1. An `addu`/`subu` that combines a **base constant** with a **newline counter × spacing** product.
   In BnN2 the multiply and the combine are adjacent (`mult v0,v1,v0` then `subu s2,a2,v0`). A
   `subu` here is the signature of column-major layout; an `addu` is row-major. **Look for the
   `mult` first** — a newline count multiplied by a small constant is rare in graphics code.
2. Two `sh` stores into the same GPU packet at a fixed small stride, one fed by the newline-derived
   value and one by a cursor that increments per character. Whichever one the *cursor* feeds is the
   axis the text currently runs along.
3. A "reset base after newline" site — a `li`/`addiu` of a large constant into the cursor register,
   inside the newline branch. Expect two of them; BnN2 had exactly two.

### 2.2 BnN2 (PS2): the menus were converted by **writing a zero into a parameter the engine already had**

This is the finding most worth acting on, and neither existing research file says it.

`[SRC]` In `scps_150.26.asm`, Hilltop's own reconstruction of the game's print routine reads, as a
comment above his `voice_and_sub` hook:

> `void print(char *text_base_param, line_number, max_newlines, X, Y, char is_drop_shadow, char TEXT_DIRECTION)`

and his call into the game's own `print` (`0x0015a3f8`) ends with `li t1, 0` in the delay slot,
commented `;param 6 horizontal`.

`[SRC]` Then across the whole file, dozens of menu conversions are a *single constant store into that
argument*, not a rewrite. The comments name them: `;Keep/Release options vert->hori` → `li a3,0`
(twice); `;vert to hori` → `li a3,0` (three times); `;Inject tutorial vert->hori` → `li t1,0x0`;
`;Yes verti->hori` / `;No verti->hori` → `li a3,0x0`; `;verti to hori` in the fishing prompts → `li
t0,0` and `li t2,0`; `;Hikari Yes/No verti->hori`; `;label hori` → `li a3,0x0`; and
`;disable verti mode for space` → `li t1,0x0`. The register differs by site (`a3`, `t0`, `t1`, `t2`),
which `[INF]` means several entry points with different argument counts share one direction flag —
the flag is the **last** argument at each.

**So the engine shipped with a horizontal mode.** `[SRC]` Corroborated by the section header Hilltop
wrote: `; ################ Native Horizontal text fixes` — the fixes under it are about texel size
(`23->22`) and kerning, not about orientation, because those surfaces were *already* horizontal.

`[INF]` **What this means for `TXT-01`.** The first question to ask our renderer is not "how do I
rotate it" but **"does the print path take a direction argument, and where does the vertical branch
diverge?"** If the answer is yes, then every menu, prompt and label in our game converts for the price
of one `li reg, 0` per call site plus new X/Y coordinates — cheap, mechanical, and delegable — and
the expensive rewrite is confined to the dialogue path. If the answer is no, the PS1 original
predates the feature and §2.1's rewrite is the whole job. Answering this is a single Ghidra session
and it should gate the estimate for the rest of the text work. The tell in the disassembly is a
**branch on a small parameter that selects which of two axes the per-glyph step is applied to** —
look for two nearly identical blocks differing only in which register the step is added to.

`[SRC]` Note also `print_subs` (`0x0019d1e8`) as a *separate* print entry, and a commented-out site
labelled `;VERTICAL TEXT` near it, plus a live `;Vert to hori` at the "Underwater Text" surface that is
an `addiu s3, mfw` — i.e. some surfaces did *not* go through the direction parameter and got the
cursor-arithmetic treatment instead. `[INF]` Budget for a mixed population: some surfaces flip by
parameter, some by arithmetic, and the dialogue by rewrite.

### 2.3 BnN-PSP (Spanish): the same split, stated from the other side

`[SRC]` GriffithVIII, *Mis primeras vacaciones de verano*, § *Texto en vertical*. Order of operations,
in his words:

1. PPSSPP's graphics debugger first. *"lo importante era poder saber cómo funcionaba la caja de texto
   y como imprimía la orientación vertical"* — understand the box before the glyphs.
2. *"Tras un par de horas, pude identificar los valores que asignaban la posición de la caja en la
   pantalla del juego. En este caso estaba atado a la posición del texto."* The box position was
   **tied to the text position** — so fixing the text moved the box with it, and the box was not a
   second problem.
3. *"¡Al fin! Ya había dado con las instrucciones que definían la orientación."* — the instructions
   that *define the orientation*, found as a discrete thing.
4. *"Mi solución en aquel entonces fue simplemente intercambiar la variable del eje X con el del eje
   Y"* — swap the X-axis variable with the Y-axis variable. He gives the two instructions as
   `li v1,0x1D` commented *Axis X* and `li v0,0x1F7` commented *Axis Y*.

`[INF]` Read against §2.2, this is the same story: the orientation was localised to an identifiable
pair of assignments, not smeared across the renderer. And the two values are the *origins*, not the
steps — `0x1D` is a small left margin and `0x1F7` a near-right-edge column origin for a 480-wide
screen, which is what a right-to-left column layout needs. `[INF]` Our PS1 equivalent, on a 320- or
640-wide framebuffer, should be a similar pair: one small constant and one close to the right edge of
the dialogue box. **A scalar search for a constant slightly inside the right edge of the dialogue box
is a cheap way to find the vertical origin.**

`[SRC]` He also records the fixed advance the PSP used — *"las letras tienen un ancho fijo entre ellas
(16 píxeles originalmente)"* — and that before writing any VWF he **just set the fixed width to about
8 px** to see how Spanish would read (*"coloqué el ancho fijo a unos 8px aproximadamente"*).
`[INF]` That is the cheapest possible intermediate result on this exact engine family and it should
be our PLAN `TXT` trial milestone: one constant, English text legible, no table, no new code. It also
independently confirms `research/ps1-translation-practice.md` §3.5's "cheaper levers before a VWF"
recommendation on a Boku engine rather than on `b.l.u.e.`.

`[SRC]` One more datum from him worth recording: after reviewing around fourteen different fonts in
Japanese games he found only two that implemented variable width at all (*"solo he encontrado dos
casos donde implementaron un ancho variable"*). `[INF]` So: do not go looking for a dormant VWF in our
EXE. Expect a fixed advance.

### 2.4 What did **not** have to change

`[SRC]` In BnN2 the glyph **sheet indexing** survives rotation untouched — `font_loop` keeps the
original `char % 17` / `char / 17` column/row arithmetic and the same `mult … s7` glyph-cell scaling.
`[INF]` Rotation is purely about where the quad lands on screen, not about which texels it samples.
That is a useful scoping fact: the sheet, the table, the extractor and the reinserter are all
independent of the rotation decision, so `TXT-01` (read the renderer) does not block the script
pipeline work.

---

## 3. The three VWF designs, with hook shapes and free-space choices

All three are real, shipped, and readable. Pick by which renderer family §1.1 put you in.

### 3.1 Design A — per-glyph sprite advance (MML2; BnN2 dialogue)

**Shape.** The renderer draws one textured primitive per glyph and then advances a cursor. You leave
the drawing alone and change only the advance.

`[SRC]` `Mega-Man-Legends-2-Demo/SLPS_021.09.asm`, the minimal form — about twenty instructions:

* Free space is declared as `freespace_text_1_start` with `freespace_text_1_size`, wrapped in armips
  `.area` so overflow is a build error. `[INF]` Copy this discipline verbatim; it is the single
  cheapest defence against a patch that silently overruns into live code.
* `vwf_table:` is `.import "vwf.bin"` — a flat `u8[]` of pixel advances indexed by glyph code. Nothing
  more.
* The hook is at `jump_hijack`, the jump at the **end of the glyph renderer**: two instructions,
  `la v0, func_vwf` then `jr v0`.
* `func_vwf` loads the character from `t0 - 1` (the renderer's own read cursor, one past the glyph it
  just drew), masks to a byte, indexes the table, puts the width in `t3` — the function's return
  register — and adds one for the inter-letter gap with `addiu t3, t3, 0x1`. The gap is folded into
  the code, **not** into the table.
* Two-byte characters take a separate branch that keeps `li t3, 0xC`, the original fixed advance, so
  Japanese still renders correctly. `[INF]` We need the equivalent: our control codes and any glyph we
  do not redraw must keep a sane default rather than reading garbage out of the table.
* The trampoline re-executes the four displaced instructions and returns to `jump_hijack + 4*4`.

`[SRC]` `BokuNoNatsuyasumi2/scps_150.26.asm`, the elaborate form, for when the width is needed in
more than one place: `func_vwf` is called **three times per glyph** — from `font_loop` it is entered
at `texel_width` (to compute the right-hand UV), at `x_right` (to compute the right-hand screen X),
and at `after_text_loop` (for the advance itself). The calling convention is unusual and worth
copying: **`a0` carries the return address**, set by `la a0, <label>` before `j func_vwf`, so one
routine serves three call sites without touching `ra`. The table lookup itself is four instructions —
load table base, add the glyph code, `lbu`, then `sll v1, v1, 0x4` because one pixel is `0x10` in the
GS's fixed-point coordinates. `[INF]` **On PS1 that shift is wrong** — the GPU takes integer screen
coordinates, so our version has no scaling step. Do not port the `sll`.

**Free space chosen.** `[SRC]` BnN2 put `vwf_table` at `0x0712b24`, annotated in-file as *0xd0 bytes of
free space*; `func_vwf` at `0x028eb34`; the relocated `font_loop` at `text_loop_space = 0x00290538`,
annotated *free debug text space*; and the 1058-byte `font_kerning.bin` **inside the repurposed
`boku2.crc` file** at `+0x16374`, after NOPping the CRC check. A single word at `ra_stash =
0x0295610` was stolen to save `ra` across the sumo-subtitle hook. `[INF]` The pattern is: dead debug
code for *code*, and a data file the game no longer validates for *tables*. We have no CRC file to
repurpose, but we have `research/ps1-translation-practice.md` §4.7's list (the `~0x7B4` PS-X EXE
header hole, kernel holes, dead `FntPrint`/`FntFlush`/`FntOpen` debug-font routines, and appending
with a bumped `t_size`), and `SCPS_100.88` is exactly `0x80000` — check its tail for padding.

### 3.2 Design B — VRAM composition (PopoloCrois)

**Shape.** `[SRC]` `Illidanz/PoPoTranslation/bin_patch.asm` (MIT). The font lives in VRAM at
`FontVRamX equ 1024 - (256 / 4)`, `FontVRamY equ 48`, and `CharRender` blits one glyph per call with
`jal MoveImage` (the PsyQ VRAM→VRAM copy, GP0 `80h`). Per call it:

1. maps ASCII to Shift-JIS through a table built with armips `.sjisn` directives;
2. **linearly searches the game's own font table** at `FontTable` — five-byte records of the shape
   *(sjis hi, sjis lo, 00, index, 00)*, capped at `0x100` iterations, falling back to a space if not
   found — to turn Shift-JIS into the engine's internal glyph index;
3. converts that index to VRAM (x, y) with a `divu` by `0x20` (32 glyphs per row) plus the font base;
4. builds a `RECT` on the stack and calls `MoveImage`;
5. **returns the glyph's width in `v0`**, read from the width table.

`[INF]` That step 2 is the interesting one for us: rather than rebuild the game's table, they *query*
it at runtime. If our EXE holds a code→cell table we cannot cleanly relocate, the same move is
available — search it in the hook instead of duplicating it.

`[SRC]` The space character is special-cased **before** the lookup, because a bounding-box width would
be zero. Hilltop hits the identical problem from the generation side, MML2 [44:03]: *"we have to have
an a special exception for the space character … the bounding box will give it a width of zero."*
`[INF]` Two independent projects tripping on the same thing makes it a checklist item, not a footnote.

**Free space chosen.** `[SRC]` PoPo uses **five separate islands** in the EXE, each its own
`.org`/`.area` pair, and the space came from **deleting features they did not need**: the sections
are labelled *"Replace error codes"*, *"Replace the anime text rendering function"* (with the
still-needed parts of that routine, `ANIME_RENDER_CODE` and `ANIME_REDIRECT_CODE`, rewritten compactly
inside the same area so they fit), and several smaller ones. Two of the areas take an explicit fill
byte (`.area 0x44,0x0`).

`[INF]` **This is a free-space source `research/ps1-translation-practice.md` §4.7 does not list**, and
for us it may be the best one: a Japanese-only PS1 game is full of routines a translation patch makes
dead. Candidates to audit in our EXE once it is mapped — the furigana path (BnN2's sequel had one and
Hilltop's MML2 patch repurposed the *furigana toggle* itself into a dev-room switch, MML2 [57:13]);
any vertical-only code path we are about to stop calling; debug/`Fnt*` routines; and any
Shift-JIS-to-index machinery the redrawn sheet obsoletes.

### 3.3 Design C — overloading the width table

`[SRC]` PoPo again, `VWF` in `bin_patch.asm` (MIT). The table byte is not only a width:

* `> 0xD0` glyph codes skip the table entirely and take a fixed `addiu s4, s4, 0x8` (Japanese
  characters keep a half-width default).
* table value `<= 0x10` → **relative advance**: `addu s4, s4, t1`.
* table value `> 0x10` → **absolute tab stop**: the value is doubled (`sll t1, t1, 0x1`) and
  **assigned** to the cursor (`move s4, t1`), not added.

`[INF]` One byte per glyph therefore buys both proportional text and free column alignment in menus,
with no second mechanism and no new control code — the *escape* is a value range the real widths can
never occupy. `research/ps1-translation-practice.md` §3.5(c) names the overload but not the doubling
or the `>0xD0` fixed-width escape; both matter if we copy it. Note the cost: the tab stops are in
units of two pixels, so alignment is quantised.

`[SRC]` A separate, simpler table lookup, `BOOK_VWF`, serves the monster book — same table, different
base (`VWF_LOOKUP` vs `VWF_LOOKUP2 = VWF_LOOKUP + 0x60`), and it adds the width into a plain memory
word at a fixed address rather than a register. `[INF]` Two bases into one blob is a neat way to serve
both an ASCII-indexed surface and a glyph-index-indexed surface from a single artifact.

### 3.4 What all three share, and the one non-negotiable

`[SRC]` All three tables are generated, never typed. Hilltop, MML2 [43:33]: a Python function
*"creates a bounding box around every single character around every single cell"* and writes the widths
out. BnN2's `reprint.printFont` renders the sheet from a TTF and writes each glyph's measured
bounding-box width into `font_kerning.bin` **in the same pass**.

`[INF]` That single-pass property is the thing to preserve, and it is our own `ENG-1` in concrete
form: the atlas, the width table read by the ASM, and the word-wrapper used by the inserter must all
come from **one** emission. A hand-maintained second copy of the widths is a gate that passes exactly
until the two copies drift, which is when you needed it. Make the build emit sheet + `vwf.bin` +
wrap-widths together, and make the reinserter read the emitted file rather than a constant.

`[SRC]` And, across all three: **no pair kerning.** Every implementation is proportional advance plus
one global inter-letter gap. `[INF]` Do not spend a byte on it.

---

## 4. Checklist — everything that breaks the moment widths stop being constant

Work this list; each item is something a source hit in production.

- [ ] **`strlen`-derived centring and right-alignment.** `[SRC]` PoPo added `STRLEN_VWF` and re-hooked
      it at **six** `jal` sites. Every one of them was a place the game measured a string by counting
      characters and then divided to centre it. `[INF]` A PS1 game with dialogue, menus, item names and
      a diary will have several; find them by xref on the original `strlen` (PoPo's was at
      `0x8009b920` — ours will be a PsyQ symbol Ghidra's extension names for us) and audit each.
- [ ] **How exact the measurement has to be.** `[SRC]` PoPo's `STRLEN_VWF` is deliberately *not*
      pixel-accurate: it counts 2 for a normal glyph and 1 for the narrow ones (space `0x20`, `i`
      `0x69`, `l` `0x6c`), then halves the total (`srl v0, v0, 0x1`). `[INF]` Centring needs
      *consistency*, not accuracy; a cheap approximation that never disagrees with itself is fine, and
      much shorter than a second table walk.
- [ ] **In-band control codes must be skipped by the measurer, not just the renderer.** `[SRC]`
      `STRLEN_VWF` skips `0x1e` and follows a signed 16-bit relative **redirect** on `0x1f` before
      continuing. `[INF]` Our stream has `0x8000`/`0x8001`/`0x8002`-with-argument and, per §5, a
      `0x0000` page guard. Any width or length routine that does not model all of them will
      mis-measure, and it will mis-measure *silently*.
- [ ] **Line-length caps expressed in characters.** `[SRC]` BnN2's print routine takes a
      `max_newlines` parameter; `b.l.u.e.` had a `slti v0, v0, 0x20` cap that Hilltop doubled
      (`research/ps1-translation-practice.md` §3.5). `[INF]` A character cap is meaningless once widths
      vary — it will either truncate early or overrun the box. Find it and convert it to a pixel
      budget, or raise it far enough that the build-time wrapper is the only limit.
- [ ] **Every other text surface, one hack each.** `[SRC]` BnN2 patched, by name in
      `scps_150.26.asm`: shop prices, insect keep/release, insect tutorial, insect delete confirmation,
      the insect cage-full header, fishing prompts, the Hikari yes/no prompt, underwater text, the
      "caboose" and LV/EXP readouts, the memory-card text, the calendar and month digits, and the save
      string. PoPo separately patched the monster book, the EXP singular/plural, and several
      first-time/update width pairs. `[INF]` Our list is enumerated in
      `research/ps1-translation-practice.md` §3.5's closing note (dialogue, diary, insect
      encyclopedia, insect names, bottle caps, calendar, save/load, minigames, bug sumo, TV, endings).
      Treat "find them all" as a task with an xref-driven completion criterion — every caller of the
      advance constant and every caller of `strlen` — not as a play-through.
- [ ] **Box geometry, cursor positions and backgrounds.** `[SRC]` Roughly half of BnN2's
      `scps_150.26.asm` is not code at all: it is `.word` rewrites of background rectangles
      (x, y, w, h) and cursor coordinates next to each converted prompt. `[INF]` Budget for the data
      edits to outnumber the code edits, and for them to be found only by looking at the screen.
- [ ] **Glyph cell size vs texel size are two constants and both must move.** `[SRC]` BnN2 changed
      the sheet from 23 px cells to 22 px and had to patch **four** separate sites — menu texel width,
      menu texel height, menu glyph width, menu glyph height — each marked `EMULATOR PATCH THIS`
      because upscaling emulators need a different value than hardware. `[INF]` If our redraw changes
      the cell size, expect the same fan-out, and expect a native-resolution-vs-upscaled discrepancy.
      This is a reason to **keep the original cell size** in the replacement sheet unless there is a
      real gain from changing it.
- [ ] **Drop shadows double the packet.** `[SRC]` BnN2's `font_loop` emits a second quad per glyph and
      advances the GPU packet cursor by `0x50` instead of `0x28`, with `shadow_x equ 0x20` /
      `shadow_y equ 0x10` offsets. `[INF]` If our renderer already draws a shadow, the VWF must update
      *both* quads' right-hand X, and if the packet buffer is a fixed-size array, a wider English line
      can overrun it. Check the buffer's capacity against the worst-case glyph count per box.
- [ ] **The space character's measured width is zero.** `[SRC]` Hilltop MML2 [44:03] and PoPo's
      `@@space` path, independently. Special-case it in the generator *and* in the runtime.
- [ ] **The default for anything not in the table.** `[SRC]` MML2 keeps `li t3, 0xC` for two-byte
      characters; PoPo keeps `addiu s4, s4, 0x8` for codes `> 0xD0`. `[INF]` Our table will be indexed by
      a `u16` glyph code with a range far larger than the Latin glyphs we redraw. Decide the
      out-of-range behaviour explicitly, and make the table's bounds a build-time assertion.
- [ ] **Assets duplicated per scene.** `[SRC]` BnN2's `fixFishOnMem()` exists because `fishing.msg`
      is copied into a preloaded blob at a second fixed offset (`research/related-projects.md` §2).
      `[INF]` If our game preloads a copy of any string table to avoid a seek, patching one copy leaves
      the other Japanese — and it will show up in exactly one scene, late.
- [ ] **Re-verify the gate after the refactor.** `[INF]` Per `ENG-1`: a width-table assertion that
      re-derives the widths from the same generator it is checking measures nothing. The wrap test
      must compare the *generated* table against *rendered pixel output*, at the narrowest box in the
      game, and it must be made red on purpose once.

---

## 5. The PSP dialogue/event format (Kendrit's spec), and what of it is a hypothesis for PS1

`[SRC]` `KendritPy/Boku_ESP_JP/docs/boku-dialogue-format.md` — **MIT**, and the most precise statement
of this format anywhere. It targets *Boku no Natsuyasumi Portable*, the PSP port of **our** game.
Summarised faithfully; all of it is PSP-measured.

**Container chain.** `PSP_GAME/USRDIR/` → `cdimg.idx` + `cdimg0.img` → `map/gz/*.bin` →
`M_*.bin.gz` / `.gzx` → an unnamed pack → **member 1** → the dialogue file → a block → a text
element/run. `cdimg.idx` begins with `DFI\0`; offsets are in `0x800`-byte sectors; named packs are a
count plus `0x0C`-byte `(offset, size, name_offset)` entries, unnamed packs `0x08`-byte
`(offset, size)`. `.gz` is plain gzip, `.gzx` prefixes a 32-bit decompressed size. **Zero-sized
entries and original table positions must be preserved on rebuild** — the spec says so explicitly.

**Dialogue identity.** Not a RAM address: the tuple *(script, named-pack member, dialog/block id, text
element, segment/run)*. `[INF]` This is exactly the shape our TECHNICAL principle 3 wants for line ids,
and it is worth adopting rather than inventing — it survives a rebuild and it is derivable from the
extractor alone.

**Dialogue file.** A 32-bit block count, then entries of *(u16 id, u16 block length, u32 block
offset)*. Each block starts with an element count and an offset table, and **from index 3 onward the
entries alternate ASCII key/name data and `u16` text streams** — 3 key, 4 text, 5 key, 6 text, …
`[INF]` This is sharper than pleonex's "skip the first 3 elements and walk `i += 2`", because it says
*what* the odd entries are: ASCII names. An ASCII name field is a gift — it gives us human-readable
line ids and a speaker hint for free, and it is trivially recognisable in a hex dump.

**Text words** — little-endian `u16`:

| Word | Meaning |
|---|---|
| `0x8000` | normal terminator; preserve exactly |
| `0xFFFF` | alternate terminator; preserve exactly |
| `0x8001` | newline |
| `0x8002` | page/pause control; **consumes the following argument** |
| `0x0000` | segment/page guard or context-dependent boundary; **never discard blindly** |

`[SRC]` The verified multi-page sequence is `0x8002, argument, 0x0000, <first word of next page>`, and
**removing that `0x0000` drops the first visible character of the following page.** Page boundaries
are therefore parsed from the enclosing element and the control sequence, *not* by treating every zero
as a C-string terminator. `[INF]` This is a real defect waiting for us: a naive extractor that splits
on `0x0000` produces text that round-trips cleanly and loses a character per page in the game. It
should be a test in our reinserter from day one — and per `ENG-1` the test must be written against a
real multi-page line from the disc, not against a fixture someone typed.

**Font atlases.** Codes index 16×16 tiles across 512×512 4-bpp PIM2 sheets:
`atlas_index = code // 1024`, `tile_index = code % 1024`, `tile_x = (tile_index % 32) * 16`,
`tile_y = (tile_index // 32) * 16`. The PIM2 pixel data is PSP-swizzled.

**Runtime.** The plugin keeps JP and ES raw streams side by side and swaps the whole atlas rather than
assuming one edition's code table applies to the other; in Japanese mode it restores the JP atlas and
**"uses the original fixed 16-pixel advance."** `[SRC]` So the PSP's untouched advance is 16 px, matching
GriffithVIII's account (§2.3) from the other direction.

### What transfers to PS1, and how much to trust it

`[INF]` Ranked:

* **Very likely** — the `u16` control-word vocabulary (`0x8000` end, `0x8001` newline, `0x8002` +
  argument), because it is independently attested on PSP (pleonex, Kendrit) and PS2 (Hilltop's
  `MSG.convertRawToText`) and our own `research/disc-recon.md` already sees `0x8000`-range codes in
  `BOKU.BIN`.
* **Likely** — the block shape *(count, then (id, length, offset) entries)*, and "the first three
  element entries are not text", attested on both PSP and PS2.
* **Worth testing early, high value if true** — the **`0x0000` page guard** and the ASCII key/text
  alternation. Neither is in `research/related-projects.md`. Both are cheap to check against a dump
  and both change the extractor.
* **Do not assume** — gzip (a PSP-era choice; a 2000 PS1 game will not link zlib), the `DFI\0` index
  (our disc has no `.idx`), 16×16 cells, 4 bpp, 1024 glyphs per sheet, PIM2, and swizzling. PS1 uses
  TIM and its own cell geometry.
* **Definitely different** — the fixed advance. The PSP's is 16 px because the PSP sheet is 16×16.
  Ours will be whatever our cell is.

---

## 6. The escape hatch: hijack the text *lookup*, do not relocate the text

For when English does not fit and the pointers cannot be safely recomputed. This is slowbeef's
"DATCH", and `pnhack5` is its primary statement.

`[SRC]` slowbeef, `pnhack5` (*"Jump Hijacking"*). The framing is a top-down decomposition argument: a
big game funnels many different callers — item descriptions, menu responses, cutscene subtitles —
through a small number of shared routines, one of which looks up a string by pointer. He gives the
target in pseudocode as `lookUpText(TextBuffer, pointer)` walking to a null, and the replacement as
`lookUpEnglishText`, which:

1. reads a value **at the original pointer** and treats it as an offset (`i = pointer +
   hackedNewOffset`);
2. walks from there to the terminator;
3. **skips in-band control codes** while copying.

So the original pointer stops addressing a string and starts addressing a tiny header that redirects
to the real, longer English string somewhere else entirely. **Nothing in the game's pointer tables has
to move or be recomputed.**

`[SRC]` The mechanical recipe he states for installing it:

> - Identify the function you want to edit.
> - Find JALs to that function.
> - Write your new function somewhere else in memory.
> - Change the JAL's address to your new function.

plus the MIPS facts it rests on: `jal` stores the return address in `r31`, the callee returns with
`jr r31`, and the instruction in the delay slot always executes.

`[SRC]` `pnhack2` records the companion observation that makes this cheap to test: the *entire* decode
step in Policenauts' in-game text was one `subu r2, r0, r2`, and zeroing that one instruction in a
savestate made the game render raw ASCII. `[INF]` The general move — **neutralise one instruction in
RAM and watch what changes** — is the fastest way to confirm you have found the right routine before
writing any patch, and PCSX-Redux's Lua `PCSX.addBreakpoint` plus its inline MIPS assembler make it a
two-line experiment.

### When we would reach for it

`[INF]` Our situation is more favourable than Policenauts' — our text is in a data archive, not
compiled into adventure-VM bytecode, so relocation is probably available. Reach for the hijack when:

* the archive's directory in the EXE turns out to be **12-byte LBA records** (Hilltop's MML2 shape,
  §1 of his video) and growing a file forces the whole two-pass LBA rebuild for one line of text;
* a string is referenced by a **hardcoded `lui`/`addiu` pair** rather than a pointer dword (see §7,
  item 5) at more sites than is comfortable to patch;
* a table is size-locked by adjacent structures, which is precisely what happened to Hilltop on
  Racing Lagoon — `[SRC]` [14:39]–[15:31]: *"this game was so highly optimized with how its memory was
  put together that expanding the file actually crash the game"*, and the fix was to **inject a value
  into an unused field of the existing header** and have the game's own calculations read that
  instead, which freed the block ordering. `[INF]` Same family of move: change what the game *reads*
  rather than where the data *is*.

`[SRC]` Note also that PopoloCrois's own string format contains an in-band redirect (`0x1f` + a signed
16-bit relative offset, handled in both `ANIME_REDIRECT_CODE` and `STRLEN_VWF`). `[INF]` That is the
same idea implemented as a *control code* rather than a *function hijack* — worth considering if our
stream has a spare `0x80xx` code, since it needs no free space for a new routine, only a branch in
the existing walker.

---

## 7. Claims in our existing research that this reading contradicts or sharpens

1. **`ps1-translation-practice.md` §3.5 frames "vertical → horizontal" as one job. It is two, and the
   cheap half may cover most surfaces.** `[SRC]` In `scps_150.26.asm`, dozens of BnN2 menu
   conversions are a single `li <reg>, 0` into an argument of the game's **own** print routine, whose
   last parameter Hilltop's reconstruction names `TEXT_DIRECTION`; only the dialogue path got the
   axis-swap rewrite. The file even has a section headed `; Native Horizontal text fixes`.
   `[INF]` **Action:** `TXT-01`'s first deliverable should be a yes/no on "does our print path take a
   direction argument", because it changes the size of the rest of the text work by a large factor.
   §2.2.

2. **§3.5(b)'s "plus swapping every `get_fb_x`/`get_fb_y` pairing in the quad setup" is right but
   makes the job sound bigger than it is.** `[SRC]` The shipped `font_loop` calls each helper **once**;
   what is pervasive is not the helper calls but the re-targeting of the `sh` stores at packet
   offsets `0x10`/`0x12`/`0x20`/`0x22`, and the drop-shadow quad that doubles the packet stride from
   `0x28` to `0x50`. `[INF]` Restating it as "two helper calls swap, four packet stores re-target"
   makes it something you can plan against. §2.1.

3. **§3.5's distilled recipe step ① lists two shapes for the advance; there is a third, and it is the
   one MML2 uses.** `[SRC]` Hilltop, MML2 [40:22], and `SLPS_021.09.asm`: the advance is the **return
   value** of the per-character print function, written into `t3`. `[INF]` A scalar search for the
   advance immediate will not find this shape, because the addition lives in the caller and takes a
   register. §1.7.

4. **§3.5(b)'s width-lookup excerpt ends with `sll v1, v1, 0x4` ("1 pixel = 0x10 value"). That is a
   PS2 GS artifact and must not be ported.** `[SRC]` It exists because the GS takes fixed-point screen
   coordinates. `[INF]` The PS1 GPU takes integers; our `func_vwf` equivalent has no scaling step.
   §3.1.

5. **Neither file records the EXE-embedded-pointer gotchas, and they are the kind that cost a day.**
   `[SRC]` Hilltop, MML2 [35:36]–[39:28]: text embedded in the EXE is referenced two ways —
   as a plain pointer dword (easy), or as a **hardcoded `lui`/`addiu` pair** that constructs the
   address (Ghidra's xref points at the *use*, not at the pair that built it). And the trap: when
   editing the low half in place, *"if it's an add operation that you're editing you need to check if
   the immediate value is higher than 8000, because if so this add actually becomes a subtract and you
   need to add one to the upper two bytes to compensate."* `[INF]` Sign extension on `addiu`. Any
   pointer-rewriting tool we build must implement this or it will corrupt exactly the pointers whose
   low half crosses `0x8000`.

6. **§4.7's list of free space is missing the source PoPo actually used, which may be our best one.**
   `[SRC]` `bin_patch.asm` carves five `.org`/`.area` islands out of **features the translation makes
   dead** — error-code strings, the anime text renderer (partly rewritten compactly in place to fit),
   and more. `[INF]` A Japanese-only PS1 game with a furigana path, a vertical-only code path we are
   about to stop calling, and PsyQ debug-font routines is likely to yield more than the
   `0x7B4`-byte PS-X EXE header hole. Audit for dead features once the EXE is mapped. §3.2.

7. **§3.4's DATCH account attributes two specifics to `pnhack5` that are not on that page, and the
   pages that would carry them are unreachable.** `[SRC]` `pnhack5` covers the jump-hijack mechanism,
   the redirect-header idea and the control-code skipping. It does **not** contain the claim that
   Policenauts' pointers were embedded in adventure-VM bytecode where they collided numerically with
   opcodes, nor the quoted *"there was no systematic way to find and recompute them"*, nor the "needed
   4 variants for different string classes" detail. `pnhack3` 404s at the origin and the Wayback
   Machine has no usable capture of `pnhack6` or `pnhack7` (checked against four timestamps).
   `[INF]` Those three claims should be marked unverified in `ps1-translation-practice.md` §3.4 until
   someone finds another capture. **They do not change any decision** — the mechanism, which is the
   part we would copy, is fully documented on `pnhack5` and is restated here in §6. Flagging rather
   than filing, per `PLN-3`: no nameable harmed party, only a citation that overstates its source.

8. **`related-projects.md` §3's TraduSquare summary is accurate and can be sharpened with two things
   from the full devlog.** `[SRC]` (a) Before writing any VWF, GriffithVIII **just changed the fixed
   advance from 16 px to about 8 px** to see how Spanish would read — the cheapest possible
   intermediate on this exact engine family, and a natural trial milestone for us. (b) After surveying
   around fourteen Japanese-game fonts he found only two with a native VWF, so we should not expect a
   dormant one in our EXE. §2.3.

9. **`related-projects.md` §7(a) Tier 2 item 9 ("budget this as the single largest ASM task") stands,
   but should be split.** `[INF]` The PS2 evidence for column-major dialogue is solid
   (`base_x − newlines×spacing`). What §2.2 adds is that the *number of surfaces* needing a genuine
   rewrite may be one, with the rest flipping by parameter — so the budget is "one hard rewrite plus a
   long mechanical tail", not "a layout rewrite everywhere".

10. **`related-projects.md` §1's PSP script summary can be sharpened by Kendrit's spec.** `[SRC]`
    Elements from index 3 onward **alternate ASCII key and `u16` text** (not merely "skip 3, step 2"),
    `0xFFFF` is a genuine alternate terminator, and there is a `0x0000` page guard whose removal drops
    the first visible character of the next page. `[INF]` The ASCII key gives us free line ids and
    speaker hints if the PS1 shares it; the page guard is a silent-corruption trap for our
    reinserter. §5.

11. **`ps1-translation-practice.md` §3.5(c) names PopoloCrois's table overloading but not its two
    sharp edges.** `[SRC]` Tab-stop values are **doubled** before being **assigned** (so alignment is
    quantised to two pixels), and glyph codes above `0xD0` bypass the table entirely for a fixed
    half-width. `[INF]` Both change the design if we copy it. §3.3.

12. **§4.8's "Ghidra does not auto-detect Shift-JIS" is narrower than the real limitation.** `[SRC]`
    Hilltop, Ghidra intro [23:31]: Ghidra supports many encodings for *display* but the main release
    *"does not have very good support for searching for non-ASCII strings"* — it is the **search** that
    is ASCII-only. `[INF]` Immaterial for us in the end, since our text is glyph indices rather than
    Shift-JIS, but it means "find the Japanese strings in Ghidra" is not a route, and the route is the
    one in §1.8 (relative search against the sheet order, outside Ghidra).

---

## 8. The shortest path this reading suggests for `TXT-01`

`[INF]` Everything below is inference from §§1–6, in dependency order. No estimates.

1. Get a dialogue box on screen in PCSX-Redux and read the **GPU command log**. Count the primitives
   per box. That alone picks the VWF design (§1.1, §1.4).
2. In the VRAM viewer, locate the glyph sheet and note its **texture page** placement and cell size
   (§1.5).
3. Take the before/during savestate pair; set a **read** breakpoint on the decoded text buffer; land
   in the renderer (§1.2, §1.3).
4. In Ghidra: fix the renderer's function signature, then look for a **direction parameter**. This is
   the fork in the road (§2.2).
5. Identify the per-glyph step and the per-newline step and confirm which axis each is on (§1.7).
6. Cheapest possible result first: **change the fixed advance to roughly half**, insert one English
   line, look at it (§2.3). This validates the whole chain before any table or new code exists, and
   it is the `TXT` trial milestone.
7. Only then: carve free space with `.area`, emit the width table and the atlas from **one** pass, and
   hook per §3.
8. Then work §4's checklist, driven by xrefs on the advance constant and on `strlen`, not by playing.

---

*Written for PLAN `RSH-02`. Owned by this file; format knowledge belongs in `research/`, one home per
fact (`DOC-3`). Cited by symbol and section, never by line number (`PLN-6`).*
