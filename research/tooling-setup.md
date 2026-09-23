# Reverse-engineering toolchain on Apple Silicon macOS

Everything `PLAN` `ENV-03` and `ENV-04` asked for, as installed and verified on this machine
(Darwin 24.3 / macOS 15.3.1, Apple Silicon, Homebrew, no sudo) on 2026-09-20. Every claim below
was run from a command line with no GUI interaction; where something does **not** work, this file
says so rather than leaving the next person to find out.

Nothing here lives in the repo. Tools go under `~/Dev/dist/`, Ghidra projects under the
gitignored `work/`. The only tracked outputs are `tools/ghidra/`, `tools/redux/` and
`research/symbols/`.

## What is installed

| Tool | Version | Where | Proof it works |
|---|---|---|---|
| armips | `v0.11.0-219-g62adab4` (repo `62adab4`, 2026-08-01) | `~/Dev/dist/armips/build/armips` | assembles 3 instructions; `llvm-mc` decodes them back identically |
| Ghidra | 12.1.3, build 20260817 | `~/Dev/dist/ghidra_12.1.3_PUBLIC` | arm64 natives built; headless import + analysis of `SCPS_100.88` succeeds |
| ghidra_psx_ldr | release 2026.09.03, the 12.1.3 zip | `…/Ghidra/Extensions/ghidra_psx_ldr` | loader `PsxLoader` used; PsyQ **4.6.0** detected; 417 functions named by signature |
| OpenJDK | 21.0.12.1 (Homebrew, keg-only) | `/opt/homebrew/opt/openjdk@21` | Ghidra's `application.properties` requires java min 21, compiler 21 |
| Gradle | wrapper-provisioned 9.6.1 | `…/support/gradle/gradlew` | `buildNatives` green |
| PCSX-Redux | dev-macos-arm `PCSX-Redux-e3e051ca-Arm.dmg` | `~/Dev/dist/pcsx-redux/PCSX-Redux.app` | boots `disc/image.cue` with no window; Lua reads RAM; breakpoint fires |
| mkpsxiso / dumpsxiso | 2.30 (universal binary) | `~/Dev/dist/mkpsxiso/mkpsxiso-2.30-Darwin/bin` | dumps the whole image + XML; re-extracted `SCPS_100.88` is byte-identical to `disc/files/` |
| xdelta | 3.2.0 (Homebrew) | `/opt/homebrew/bin/xdelta3` | — |
| LLVM | 21.1.6 (Homebrew, pre-existing) | `/opt/homebrew/opt/llvm/bin` | `llvm-mc -triple=mipsel -disassemble` is our independent MIPS decoder |

Download checksums, so a stranger can tell whether they fetched the same artifact:

```
93a5d11a9ad510622acaaf908c556a7b9b764d338e78a7567f3689bf5081fd54  ghidra_12.1.3_PUBLIC_20260817.zip
04ddface00dd141f41924effa93a5dadb5630a24cdde36400bc703d25fcdec27  ghidra_12.1.3_PUBLIC_20260903_ghidra_psx_ldr.zip
a64d4d57d78ce57cd810a6a044602ce3cf1b552ca7c7e8675518f554206e0b49  mkpsxiso-2.30-Darwin.zip
b3737a580dfdeb2ea27e61a2cf7686bd830d04dd2ff1df302bfdc41f7835bcee  PCSX-Redux-e3e051ca-Arm.dmg
```

`ghidra_psx_ldr` ships one zip per Ghidra point release and the version must match exactly —
the extension declares `version=12.1.3`. Upgrading Ghidra means re-fetching the loader.

## Reproducing it on a fresh Mac

```sh
brew install openjdk@21 gradle xdelta llvm
mkdir -p ~/Dev/dist

# armips — no Homebrew formula, no macOS release asset; source only.
git clone --recursive https://github.com/Kingcom/armips ~/Dev/dist/armips
cmake -B ~/Dev/dist/armips/build -S ~/Dev/dist/armips -DCMAKE_BUILD_TYPE=Release
cmake --build ~/Dev/dist/armips/build -j8

# Ghidra. Strip quarantine BEFORE extracting, or every .jar inherits it.
curl -L -o /tmp/ghidra.zip \
  https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.3_build/ghidra_12.1.3_PUBLIC_20260817.zip
xattr -d com.apple.quarantine /tmp/ghidra.zip
unzip -q /tmp/ghidra.zip -d ~/Dev/dist/

# The arm64 natives. See the PATH trap below — this line is the whole reason it is here.
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
PATH="$JAVA_HOME/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
  sh -c 'cd ~/Dev/dist/ghidra_12.1.3_PUBLIC/support/gradle && ./gradlew --no-daemon buildNatives'

# The PSX loader, unpacked where headless Ghidra finds it without a GUI install step.
curl -L -o /tmp/psxldr.zip \
  https://github.com/lab313ru/ghidra_psx_ldr/releases/download/2026.09.03/ghidra_12.1.3_PUBLIC_20260903_ghidra_psx_ldr.zip
unzip -q /tmp/psxldr.zip -d ~/Dev/dist/ghidra_12.1.3_PUBLIC/Ghidra/Extensions/

# mkpsxiso / dumpsxiso
curl -L -o /tmp/mkpsxiso.zip \
  https://github.com/Lameguy64/mkpsxiso/releases/download/v2.30/mkpsxiso-2.30-Darwin.zip
unzip -q /tmp/mkpsxiso.zip -d ~/Dev/dist/mkpsxiso
xattr -dr com.apple.quarantine ~/Dev/dist/mkpsxiso

# PCSX-Redux. Unsigned; the xattr is what replaces the right-click-Open dance.
mkdir -p ~/Dev/dist/pcsx-redux
curl -L -o ~/Dev/dist/pcsx-redux/PCSX-Redux-Arm.dmg \
  https://distrib.app/pub/org/pcsx-redux/project/dev-macos-arm/latest
hdiutil attach ~/Dev/dist/pcsx-redux/PCSX-Redux-Arm.dmg -nobrowse -readonly -mountpoint /tmp/redux-dmg
cp -R /tmp/redux-dmg/PCSX-Redux.app ~/Dev/dist/pcsx-redux/
hdiutil detach /tmp/redux-dmg
xattr -dr com.apple.quarantine ~/Dev/dist/pcsx-redux/PCSX-Redux.app
```

### The PATH trap that costs an hour

`gradle buildNatives` fails to link the decompiler if Homebrew's LLVM is ahead of `/usr/bin` on
`PATH`:

```
Undefined symbols for architecture arm64:
  "std::__1::__hash_memory(void const*, unsigned long)", referenced from: … in marshal.o
```

Homebrew `clang++` 21 compiles against its own libc++ headers, which call an out-of-line
`__hash_memory`, and then links against the macOS SDK's older `libc++.dylib`, which has no such
symbol. Nothing in the message points at the compiler. Put `/usr/bin` first so Apple clang is
used (verify with `which clang++` — it must be `/usr/bin/clang++`) and the build is green in
about ten seconds. Homebrew LLVM is otherwise useful and should stay installed; it is what
`llvm-mc` comes from.

## armips

Verified by assembling three instructions and decoding the bytes with a *different* tool, so the
check does not consist of armips agreeing with itself:

```sh
printf '.psx\n.create "t.bin",0x80010000\n.org 0x80010000\n lui $t0,0x8002\n addiu $t0,$t0,0x37e0\n lbu $v0,0($t0)\n.close\n' > t.asm
~/Dev/dist/armips/build/armips t.asm            # -> 12 bytes
python3 -c "print(' '.join('0x%02x'%b for b in open('t.bin','rb').read()))" \
  | /opt/homebrew/opt/llvm/bin/llvm-mc -triple=mipsel -disassemble
#   lui   $8, 32770      (0x8002)
#   addiu $8, $8, 14304  (0x37e0)
#   lbu   $2, 0($8)
```

## Ghidra, headless

The project directory is `work/ghidra/`, which is gitignored: a Ghidra database embeds the
executable, so it is disc content and must never be tracked.

```sh
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
export PATH="$JAVA_HOME/bin:$PATH"
G=~/Dev/dist/ghidra_12.1.3_PUBLIC/support/analyzeHeadless

# Import + full auto-analysis. ~2 minutes; the PsyQ Signatures analyzer is 95 s of it.
$G work/ghidra boku -import disc/files/SCPS_100.88 -loader PsxLoader -overwrite
```

`-loader PsxLoader` is the only loader argument needed. The loader's own headless options are
`-loader-ramStart` and `-loader-ramSize` (defaults 0x80000000 / 0x200000, which are right here);
the PsyQ version is **detected**, not supplied, so there is no interactive prompt to answer.

What that run produced on `SCPS_100.88`
(sha256 `feac435d110c112ed83f9a84ceffd5902277a421cbca173939b9fcd92885f4a9`):

* `Executable Format = PSX Executables Loader` — the loader was used, not the raw-binary fallback.
* `PsyQ Version = 4.6.0` — detected from the `main()` prologue signature.
* **1542 functions**, of which **750** keep Ghidra's default `FUN_xxxxxxxx` name.
* **792 are named**: **417** by the PsyQ signature database, **375** by the loader itself
  (the synthetic `GTEMAC` block at 0x20000000 and the hardware-register labels).
* Memory blocks: `CODE` 0x80010000–0x8008f7ff initialised (the 0x7f800 of `.text` from the PS-X
  EXE header), `RAM` either side uninitialised, plus the I/O and GTE macro blocks.

The decompiler emits `Unable to resolve constructor at 80049200` for a handful of addresses —
GTE opcodes the PSX sleigh spec does not model. Cosmetic; analysis still succeeds.

### The symbol table is the durable artifact

`tools/ghidra/ExportSymbols.java` writes `research/symbols/SCPS_100.88.symbols.tsv`:
address, kind, name, size, source, namespace, for every function and label that is **not**
default-named. `tools/ghidra/ImportSymbols.java` is the inverse. Both are Java GhidraScripts
rather than Python: Ghidra 12 runs Python only through PyGhidra, which needs `pyghidra`
pip-installed into a virtualenv it manages, and a Java script needs nothing that Ghidra does not
already ship.

```sh
$G work/ghidra boku -process SCPS_100.88 -noanalysis -readOnly \
   -scriptPath tools/ghidra -postScript ExportSymbols.java research/symbols/SCPS_100.88.symbols.tsv

$G work/ghidra <proj> -process SCPS_100.88 -noanalysis \
   -scriptPath tools/ghidra -postScript ImportSymbols.java research/symbols/SCPS_100.88.symbols.tsv
```

Deliberately not exported: bytes, the contents of strings, decompilation, comments. A comment can
quote the Japanese script; a name and an address cannot. The header carries the executable's
sha256 so a contributor with a different dump can tell that the names were derived elsewhere.

**`ImportSymbols` expects an already-analysed program.** It renames what analysis found and adds
what it missed; it does not rebuild a program from the TSV. On a truly `-noanalysis` import there
is no disassembly, so Ghidra cannot derive a function body and every `FUNC` row fails. Two
consequences worth stating plainly, because the opposite is easy to assume:

* The **`size` column is not applied.** It is there for a human reading the file. A re-export
  reproduces the sizes because the analyser regenerates them, not because the TSV carried them.
* The round trip therefore closes over *names, kinds, sources and namespaces*, which is what we
  actually learn and what analysis cannot re-derive.

Verified, 2026-09-20, in this order:

1. A second import + analysis of the same file into a separate project exported a TSV
   **byte-identical** to the tracked one. Analysis is deterministic; the database really is
   disposable.
2. Red on purpose: `grep Boku_RoundTripProbe` on that fresh export found nothing, so the check
   below can fail.
3. The tracked TSV plus one row auto-analysis will never produce
   (`80011b08 FUNC Boku_RoundTripProbe 396 USER_DEFINED Global`, over a function Ghidra had left
   as `FUN_80011b08`) was applied with `ImportSymbols` and re-exported. The probe came back at
   exactly that address, and the re-export matched the input in every line but the `# symbols`
   count, which the hand-edited input had not been updated for. Re-exporting that project later
   still shows the probe, so the name was really written to the database.
4. The provenance guard, red and green. `ImportSymbols` compares the TSV's `# sha256` header
   against `currentProgram.getExecutableSHA256()` and **throws before writing anything** on a
   mismatch; with the hash edited to `deadbeef…` it refuses with both hashes in the message, and
   with the real file it prints `sha256 matches this program` and applies all 2561 rows.

That hash check is the guard that matters, and it replaced one that could not fail for its stated
reason: refusing only when a row falls outside memory catches a truncated file, but a TSV from a
*different regional build* has the same layout, so every address would land inside the image and
2561 wrong names would apply silently.

## PCSX-Redux, headless

`tools/redux/run-headless.sh` is the launcher and `tools/redux/smoke.lua` the gate and the worked
example. The flags that matter, all verified by running them:

* `-no-ui` — no window and no GL context. With it, none of the font/OpenGL warnings a windowed
  run prints appear.
* `-testmode` — makes Lua's `PCSX.quit(n)` terminate the process with status `n`. Without it the
  emulator keeps running and any gate hangs forever. There is no `pcsx_exit()` in the Lua global
  table; `PCSX.quit` is the function.
* `-dofile <script>`, `-lua_stdout`, `-stdout` — run our Lua and let both it and the emulator log
  reach the shell.
* `-loadiso <cue>` `-run` — mount and boot. (`-iso`/`-exe` from the online flag list are not the
  spellings this build accepts; `-loadiso`/`-loadexe` are.)
* **`-debugger`** — arms the breakpoint machinery. This one is a trap: *without* it
  `PCSX.addBreakpoint` still returns a breakpoint object and the breakpoint simply never fires,
  with no warning. Measured by arming at an address the PC had been *observed* to hold
  (0x800588a8): no hit in 400 frames without the flag, hit at frame 81 with it.
* **A breakpoint callback must `return true` to keep firing.** Returning `false` (or nothing)
  fires it once and never again — measured 2026-09-21 on the movie player: six breakpoints
  returning `false` each counted exactly 1 hit over 5,600 frames while the PC was visibly
  looping through them; returning `true`, they produced [movies.md](movies.md) § 2.2's
  per-frame counts. `boot-to-dialogue.lua`'s `return false` is fine only because it wants
  one hit.
* **A breakpoint's `width` is a range.** `PCSX.addBreakpoint(start, 'Exec', length, …)` fires
  on every instruction executed in `[start, start + length)` — measured 2026-09-22 over
  `cd_load_sync` (164 bytes): 181,076 hits in a 1,500-vsync boot, five of them at consecutive
  addresses from its entry (`tools/redux/movie-sub.lua` with `BOKU_ISLAND_RANGE`). That is how
  a run can say a whole island of code was never executed.
* **`PCSX.GPU.takeScreenShot()` goes black in the movies' 24-bit display mode.** On the stock
  disc, a shot at vsync 3616 (STR frame 60) has 852 colours and every later one has one — all
  black — at 3700, 4178 and 4979, while Beetle shows the picture throughout and the frame is
  intact in main RAM ([movies.md](movies.md) § 7 reads it from the slice buffers instead).
  Measured 2026-09-22; the cause in Redux was not chased.
* **`-interpreter`** — the arm64 dynarec dies with `Illegal instruction: 4` (exit 132, no output
  at all) on `-run` with a retail BIOS. The debugger wants the dynarec off anyway. The windowed
  arm64 build has its own limit: playing the day-1 build (Jay, 2026-09-20) it aborted at the
  title screen's START, twice, with `Unimplemented LWC2 to GTE data register 15` — a GTE
  instruction the game's own 3D code issues (none of `asm/*.asm` touches cop2, so the patch
  cannot add one). Not reproduced on the stock disc yet; until it is, PCSX-Redux on arm64 is
  a debugger, not a play-test target — DuckStation and Beetle are.
* **DuckStation's window title** (ぼくのなつやすみ on the patched image) is not read from the
  disc. `System::UpdateRunningGame` (`src/core/system.cpp`, read 2026-09-23) takes the serial
  from `SYSTEM.CNF`, looks it up in its game database (`data/resources/gamedb.yaml`:
  `SCPS-10088` → `name` "Boku no Natsuyasumi - Summer Holiday 20th Century", `localizedName`
  ぼくのなつやすみ) and shows the localized name while the `[UI] GameListShowLocalizedTitles`
  setting is on (its default). Nothing on the disc short of a different serial changes it,
  and the serial stays. What a player can do: turn off "show localized titles" (the English name, for
  every game), or set this image's own title in the game list's Properties → Title
  (`custom_properties.ini`, `Title=`), which wins over the database.

### Answering "can an agent with no display drive this?"

Yes, for everything the project needs:

| Capability | Verdict | How it was shown |
|---|---|---|
| Run with no window | **yes** | `-no-ui`; the GL/font warnings a windowed run emits are absent |
| Advance N frames | **yes** | `PCSX.Events.createEventListener('GPU::Vsync', …)` |
| Read RAM | **yes** | `PCSX.getMemPtr()` → LuaJIT `uint8_t*` over the flat 2 MB; index by `addr & 0x1fffff` |
| Read CPU state | **yes** | `PCSX.getRegisters()` → cdata with `.pc`, `.GPR.n.<reg>`, and `PCSX.getCPUCycles()` |
| Execution breakpoints | **yes, with `-debugger`** | hit at 0x800588a8 on frame 81 and at 0x80049154 on frame 90 |
| Dump the framebuffer | **yes** | `PCSX.GPU.takeScreenShot()` → `{data,width,height,bpp}`; saved 640×478×2 = 611840 bytes via `Support.File.open(path,'TRUNCATE'):write(shot.data)` |
| Raw VRAM over HTTP | **no, not headless** | see below |
| GDB stub on 3333 | **no, not headless** | see below |
| Exit status for CI | **yes** | the gate returns 0, 2, 3, 4, 5, 6, 70 or 127 to the shell, one per failure mode |

**The web server and the GDB stub do not come up under `-no-ui`.** Tried both ways: setting
`emulator.Debug.WebServer`/`GdbServer` from Lua at runtime, and writing them into
`~/.config/pcsx-redux/pcsx.json` before launch (`WebServerPort` 8080, `GdbServerPort` 3333,
`Debug` true). In both cases `lsof -a -p <pid> -iTCP -sTCP:LISTEN` shows the process holding **no
listening socket at all**, and `curl` gets a connection refusal. So `GET /api/v1/gpu/vram/raw` —
the documented route to *raw* VRAM, which the Lua memory API does not expose — is out of reach
without a GUI session, and so is driving the emulator from Ghidra over GDB. Anything needing raw
VRAM must either go through `takeScreenShot` (the visible framebuffer only) or trap the transfer
in main RAM. The config file was restored afterwards; this left no persistent change.

### The BIOS question

The bundled **OpenBIOS is not sufficient for this disc**. It reads the disc fine — the log shows
`CD-ROM ID: SCPS10088`, `CD-ROM EXE Name: SCPS_100.88;1`, and `*** Data is acceptable, booting
now. ***` — but a breakpoint on the executable's entry point at 0x80049154 never fires, and the PC
sits in a loop at 0x8003xxxx indefinitely.

With a retail Japanese BIOS (`SCPH-5500 (JP)`, which PCSX-Redux fingerprints as `ff3eeb8c`) the
executable is loaded at frame ~720, its entry point is reached at frame 835 and the game runs
(the frame-90 hit this section used to claim was the BIOS shell — see the last section). `run-headless.sh` takes the path in
`REDUX_BIOS`. The disc is `SCPS-10088`, i.e. NTSC-J, so SCPH-5500 is the matching region; a copy
lives at `~/Dev/retro-trainer/config/system/scph5500.bin` on this machine. A BIOS dump is not
this repo's to ship.

### The gate, red then green

```sh
export REDUX_BIOS=~/Dev/retro-trainer/config/system/scph5500.bin
BOKU_FRAMES=300 ./tools/redux/run-headless.sh   # exit 5
                ./tools/redux/run-headless.sh   # exit 0 (default 1000 frames, ~17 s)
```

The red case is the narrowest state in which the harm this gate exists to prevent occurs — not a
disc that fails to boot, but a run that looks like the game and is the **BIOS shell**. At frame
300 the PC is `0x800588a8`, inside `0x80010000..0x8008f800`, with a non-zero instruction stream
under it, so the PC checks pass; the sampled bytes do not, and the gate says
`ram @0x80012000 = 0000…` against the file's `b030c634…` before
`exit=5 main RAM does not hold the executable — this is not the game`. At the default 1000
frames the executable is in RAM, all six sampled offsets match `disc/files/SCPS_100.88`, the PC
is `0x8004be50` and the gate returns 0.

Exit code 6 was made red the same way, by launching the emulator with `BOKU_EXE_SAMPLES` unset:
the gate refuses on the first frame rather than spending a minute and then asserting nothing.

Exit codes: 0 ok, 2 hang, 3 the PC was not in the executable's range, 4 the PC was in range but
the instruction stream under it was all zero, 5 main RAM does not hold the executable, 6 no
expected bytes were supplied so 5 could not be decided, 70 the disc image changed, 127 a missing
file or a bad argument.

**The wall clock lives in the shell, not in the Lua** (`REDUX_TIMEOUT`, default 300 s). The first
version used a `PCSX.nextTick` watchdog inside the emulator; measured 2026-09-20, calling
`PCSX.quit()` from a `nextTick` callback **segfaults the process** — exit 139, no output at all.
So the one code path whose entire job was to report a hang was the least reliable in the gate. A
`kill` from outside cannot be disabled by the thing it is watching.

The launcher also hashes the disc image before and after and fails with status 70 if it changed;
PCSX-Redux can write to a mounted ISO (that is how it generates PPF patches), and a silently
rewritten dump is unrecoverable without re-ripping. That is detection, not prevention, and for an
unrecoverable harm prevention would be better — making the track read-only for the run, or
pointing the emulator at a copy under `work/`. Not done here because it means writing to `disc/`,
which this repo's rules forbid from a tool; worth revisiting by whoever owns the import step.

## dumpsxiso — the escape hatch

```sh
mkdir -p work/dumpsxiso-scratch && cd work/dumpsxiso-scratch
~/Dev/dist/mkpsxiso/mkpsxiso-2.30-Darwin/bin/dumpsxiso -x ./files -s ./project.xml ../../disc/image.cue
```

Dumps `BOKU.BIN`, `SCPS_100.88`, `SYSTEM.CNF`, the 27-file `__STR/` tree of `.IKI` XA streams and
`license_data.dat`, and writes an mkpsxiso project XML that rebuilds the image. The source image
is untouched (sha256 identical before and after). Output goes under `work/`, never tracked.

This is also how `disc/files/SCPS_100.88` was independently confirmed: a fresh dump produced a
byte-identical file (same sha256). The extraction in `disc/` is correct.

## Beetle PSX, as it stands on this machine

Read-only survey of `~/Dev/retro-trainer`; nothing there was modified.

* **The core exists and is built for arm64**:
  `~/Dev/retro-trainer/config/cores/mednafen_psx_libretro.dylib`, sha256
  `f53dabac7ceb17b3804f0e2dfe486488839f44dc69408390a6d4d5015d55333f`, which matches the
  `macos-arm64` pin in `cores.lock` for `mednafen_psx` — source
  `libretro/beetle-psx-libretro` at commit `c27ab27c05569575e04b25e03e87fe3220fde599`.
* **There is no RetroArch binary on this machine.** `~/Dev/dist/RetroArch` is a source checkout
  with no build output, and nothing is installed in `/Applications` or `~/Applications`.
* **The only frontend is retro-trainer's own binary**,
  `~/Dev/retro-trainer/target/release/retro-trainer`, and its CLI is
  `retro-trainer [OPTIONS] <DATA_DIR> [GAME]` — it takes a *registered game name*, not a path.
  Games live in `config/games.json` (126 entries) keyed by short name, with `rom` naming a file
  under `config/roms/`; its README's platform table lists PS1 → `mednafen_psx` → `.cue`/`.bin`,
  though every existing PS1 entry uses a `.chd`. **Neither existing frontend boots an arbitrary
  `.cue`**: retro-trainer would need a `games.json` entry plus the image under `config/roms/`,
  and there is no RetroArch to point at one. That is what `tools/libretro/run_core.py` is for —
  § "Beetle PSX, headless" below; nothing in retro-trainer had to change.
* **BIOS**: `config/system/` holds `scph5500.bin` (Japanese, sha256
  `9c0421858e217805f4abe18698afea8d5aa36ff0727eb8484944e00eb5e7eadb`) and `psxonpsp660.bin`.
  Beetle PSX wants `scph5500/5501/5502.bin` for JP/US/EU; only the JP one is present, which is the
  one SCPS-10088 needs.

## "Main RAM never contains the file's bytes" — settled: it was sampled too early

An earlier version of this section reported that RAM never matched `SCPS_100.88` and warned that
the Ghidra addresses might not be run-time addresses. **That was wrong**, and the measurement that
replaces it is [renderer-runtime.md](renderer-runtime.md) § Q0 (`tools/redux/q0-exe-load.lua`):

* While the logos play, the **BIOS shell runs from RAM at `0x8003xxxx–0x8005xxxx`**, the same
  addresses the game will occupy. The PC passes `0x80049154` — numerically the EXE's entry — more
  than 180,000 times in shell code before the game exists in memory, first at frame 90. That is
  what the "entry breakpoint at frame 90" was, and why the bytes under it were not the file's.
* The BIOS copies the executable in at **frame ~720**; the real entry is reached **once, at frame
  835**. Every sample the old note took (frames 5–300) predates the load.
* At frame 840 all of `0x80010000…0x8008F7FF` equals the file except 4 BSS bytes the program had
  already written. **File addresses are run-time addresses**: no relocation, no second `LoadExec`,
  no overlay over the image. (The seven `.OVL` files load *above* it, at `0x80079A08`.)

Two consequences for the rest of this file: wherever it says the entry point is "reached at frame
90", read "the BIOS shell passes that address at frame 90; the game starts at 835"; and a probe
that must mean "the game is running" has to compare RAM with the file, because no frame count and
no PC test can tell the shell from the game. `smoke.lua`'s old default of 300 frames passed on
**shell** code for exactly that reason; it now targets 1000 frames *and* compares six sampled
windows of `0x80010000…` against `disc/files/SCPS_100.88`, which `run-headless.sh` reads at launch
and passes in through `BOKU_EXE_SAMPLES` (no byte of the game is written into a tracked file). The
OpenBIOS observation ("the PC sits at `0x8003xxxx` indefinitely") was not re-measured.

## Beetle PSX, headless

`tools/libretro/run_core.py` is a libretro frontend: one file of Python and `ctypes` against
`~/Dev/retro-trainer/dist/libretro.h`, standard library only, no window and no human. It loads
the core dylib, answers the environment calls, runs N frames, presses buttons on a schedule,
writes PNGs and `retro_serialize` states, and prints what the core asked for. It is how a
result gets confirmed on the core Mode One runs (CLAUDE.md § "Working with the disc"); nothing
under `~/Dev/retro-trainer` is read except the core, the BIOS and the header.

```sh
export BOKU_LIBRETRO_CORE=~/Dev/retro-trainer/config/cores/mednafen_psx_libretro.dylib
export BOKU_LIBRETRO_SYSTEM=~/Dev/retro-trainer/config/system   # holds scph5500.bin

tools/libretro/smoke.sh                       # boots disc/image.cue to the title screen
tools/libretro/smoke.sh build/trial/image.cue # or any other image

# cold boot to the first dialogue line, screenshots and a state to resume from
uv run python tools/libretro/run_core.py disc/image.cue \
    --work work/beetle/stock --frames 5850 \
    --press-file tools/libretro/boot-to-dialogue.press \
    --shot 3251:title --shot 5850:first-dialogue --state-out 5850:first-dialogue

# start where that left off, instead of booting for eight seconds again
uv run python tools/libretro/run_core.py disc/image.cue --work work/beetle/resume \
    --state-in work/beetle/stock/first-dialogue.state --frames 300 --shot 300:later
```

Neither path has a default in a tracked file — pass `--core`/`--system` or set the two
variables. Everything written goes under `--work` (default `work/beetle/`, gitignored):
screenshots, states, and `saves/`, which is what the core is given as its save directory, so
nothing the core writes can land next to the image. Memory card 1 is **not** a file there: with
the core's default `use_mednafen_memcard0_method = libretro` it is the frontend's `SAVE_RAM`,
which starts formatted and empty on every run and is thrown away at the end unless
`--memcard-out` writes it; `--memcard CARD` puts a card in. That, `--ram-out` and `--poke`
are [save-format.md](save-format.md)'s § "Loading a card headlessly". `--peek ADDR:LEN`
samples a few RAM words into `peek.tsv` every `--peek-every` frames, where a 2 MB `--ram-out`
per sample would be hundreds of megabytes (`tests/test_real_clip_subtitle_beetle.py` reads
it). Two cold boots are byte-identical: the frame-5850 PNG has the same sha256.

**The trap that matters: Beetle boots without a BIOS and does not stop you.** With an empty
system directory the core logs `Firmware is missing` at INFO and runs the game on its own HLE
BIOS — no logo, and the boot runs ahead: at frame 3251 the real-BIOS boot is on the title
logo, while the HLE one is already further into the attract loop, so the schedule below does
not land where it should. Every timing measured that way, and every "confirmed on Beetle"
claim, would be about a different machine. `run_core.py` therefore reads that log line and exits 7 unless
`--allow-hle-bios` is given; a missing BIOS never shows up as a load failure.

Every failure gets its own exit code — `run_core.py --help` lists them, and `smoke.sh` maps
them one for one, adding 9 for "run_core.py fell over". `--assert-drawn FRAME[:COLOURS]` is
what makes the gate able to fail at all: it counts distinct pixel values in that frame, and
the measured spread on this disc is **1 on a blank screen, 433 on the title screen, 1518 in
the arrival scene** — so the default threshold of 100 separates "the game is drawing" from "it
is not". A frame that was asked for and never arrived (the core can ask to shut down early) is
also a failure, not a note: otherwise a gate could pass without its assertion ever running.

**Input timings are not Redux's.** `tools/libretro/boot-to-dialogue.press` holds the schedule
that reaches the first dialogue line on Beetle, with each frame's meaning; frames are
`retro_run` calls counted from 1. `tools/redux/boot-to-dialogue.lua` needs different numbers
for the same boot because it counts GPU vsyncs and its CD timing is not Beetle's. Both are
right about their own emulator; never copy one schedule into the other. A driver that reads
the pad back out of RAM to see whether a press landed must read **`0x8007276A`**, the level
word: `0x80072766` is edge-only — pressed *this frame* — and reads 0 again on the next
([renderer-runtime.md](renderer-runtime.md) § Q9).

**Speed**: ~760–850 frames per second on this Mac, one core, software rendering — a cold boot
to the first dialogue is about eight seconds of wall clock. Two such boots produce a
byte-identical frame-5850 PNG. `GET_CAN_DUPE` is answered **false** on purpose: a core allowed
to dupe sends NULL instead of redrawing, and the frame held for `--shot N` would then be an
older one wearing N's name.

**What the core actually asks for** (24 distinct environment calls on a full boot):
`GET_SYSTEM_DIRECTORY` and `GET_SAVE_DIRECTORY` once each, `SET_PIXEL_FORMAT` → **XRGB8888**
(so the framebuffer is 4 bytes per pixel, not the PS1's 16-bit word — `tools/redux/shot2png.py`
decodes the other kind), `GET_VARIABLE` 58 times during load, `GET_VARIABLE_UPDATE` every
frame, `GET_LOG_INTERFACE`, `SET_MEMORY_MAPS`, `SET_GEOMETRY`, `SET_SYSTEM_AV_INFO` (320×240 at
59.94 Hz, the geometry changing as the BIOS, the FMV and the game hand over). Core options are
answered from the core's own `SET_VARIABLES` defaults: the frontend claims core-options version
0, the core lowers its v2 definitions into legacy strings whose first choice is the default,
and those are handed straight back — no table of option values is retyped into the tool.

**This build never asks about hardware rendering at all.** `SET_HW_RENDER` is refused on
principle — no window, no GL context — but it is absent from a full boot's tally, so nothing
about the software path depends on that refusal here; it would only matter to a
`mednafen_psx_hw` build. The only call this core has refused on purpose is
`GET_CORE_OPTIONS_VERSION`, the version-0 claim above. Ten more are simply unimplemented and
refused harmlessly — the disk-control, VFS, LED, perf, rumble, bitmask, message and
audio/video-enable interfaces, `SET_CORE_OPTIONS_DISPLAY`, and an old-numbered
`SET_HW_SHARED_CONTEXT` this core still sends as plain 44 rather than 44|EXPERIMENTAL.
`run_core.py` prints those two lists separately, so a call the core newly depends on shows up
as unimplemented instead of hiding among the deliberate noes.

## XA voice clips decode with ffmpeg (measured 2026-09-21)

`__STR/BOKU_XA.XAM` is XA-interleaved and the importer does not extract it, but a raw sector
slice of the image decodes directly: 2,400 sectors from LBA 54417 (`dd bs=2352 skip=54417
count=2400`) probed with `ffprobe -f psxstr` give `adpcm_xa` streams at 37,800 Hz mono, one per
interleaved channel. So a voiced line's clip is its voice key (start sector, end sector,
channel — `research/text-format.md`) sliced with `dd` and decoded with `ffmpeg -f psxstr -i
slice.bin -map 0:a:<channel> clip.wav`. The `.IKI` movies take the same demuxer **for their
audio only**: ffmpeg's `mdec` decoder rejects every IKI video frame, and jPSXdec is the
decoder and encoder for the pictures ([movies.md](movies.md) § 4).
A key's span also holds the other 15 channels' sectors, so `./make.sh voice-only` keeps only
the sectors whose subheader carries the key's file and channel before decoding (`boku.voice`
`channel_sectors`); `-map 0:a:<channel>` is not needed. sox does not know XA.

**Speech-to-text (installed 2026-09-22)** — a machine tool, not a project dependency: the
model that translates cannot hear, so what it receives is a transcript with timing.
`brew install whisper.cpp` (1.9.4, `whisper-cli`, Metal on Apple Silicon) and two models in
`~/Dev/dist/whisper-models/`, from `huggingface.co/ggerganov/whisper.cpp` and
`huggingface.co/ggml-org/whisper-vad`:

| file | sha1 | what |
|---|---|---|
| `ggml-large-v3.bin` | `ad82bf6a9043ceed055076d0fd39f5f186ff8062` | Whisper large-v3 (3.1 GB) — the ASR |
| `ggml-silero-v5.1.2.bin` | `a372f48dcf0bd9e4330eef2802bc46e061c19634` | Silero voice-activity detector |

`$BOKU_WHISPER_MODEL` / `$BOKU_WHISPER_VAD` point elsewhere. `./make.sh voice-only
--transcribe` runs both passes over every clip and voiced movie (17 minutes on an M4 Max);
why both, and how Whisper fails on this material, is [voice-only.md](voice-only.md) § The
listening pass.
