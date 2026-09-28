An English translation patch for the PlayStation original of *Boku no Natsuyasumi*
(SCPS-10088, 2000). Version $version, built from commit `$commit` ($built_from).

**This is a patch, not the game.** You need your own dump of the Japanese disc; nothing here
contains it, and nothing here is ever sold.

## What is in English

$coverage The voices stay Japanese on purpose: this is a translation with subtitles, not a dub.

## Download

`$bundle` is the download, under the names the instructions below use:

* `$xdelta` — the patch (xdelta3).
* `$cue` — the cue sheet for the patched image.
* `PATCH.json` and `README.txt` — both sides' hashes, for a script and for a person.

## What you need

A raw dump of the Japanese disc, one MODE2/2352 track, matching Redump ($redump). Hash it
before you patch: if these do not match, the patch is not for your file.

$original_table

## How to apply it

1. **Extract** your CHD to a raw image ([chdman](https://docs.mamedev.org/tools/chdman.html)
   ships with MAME; `brew install rom-tools` on macOS):

   ```
   chdman extractcd -i "your dump.chd" -o "$base_stem.cue" -ob "$base_name"
   ```

   A BIN/CUE dump needs no extraction; use its `.bin`. Never patch a `.iso` (2048-byte
   sectors) or the `.chd` itself.

2. **Hash** the image and compare its SHA-1 with `$base_sha1`:

   ```
   # macOS
   shasum -a 1 "$base_name"
   # Linux
   sha1sum "$base_name"
   # Windows
   certutil -hashfile "$base_name" SHA1
   ```

3. **Patch** it with [xdelta3](https://github.com/jmacd/xdelta/releases) (`brew install xdelta`
   on macOS; [MultiPatch](https://github.com/Sappharad/MultiPatch) is a macOS app for the same
   job):

   ```
   xdelta3 -d -s "$base_name" "$xdelta" "$result_name"
   ```

   The browser patcher RomPatcher.js cannot apply this patch.

4. **Play**: put `$cue` beside `$result_name` and open the `.cue` in your emulator. You
   can recompress with `chdman createcd -i "$cue" -o "patched.chd"`.
$ppf_section
## What you should get

**A patched image whose SHA-1 is `$result_sha1` is v$version**, whatever the file is called.
The README on the project's GitHub page lists every version's, under "$versions_heading".

$result_table

`README.txt` in the download says all of this again, including what the patch does and does
not check for you.

## Where it is played

The project is developed and played on Beetle PSX (the mednafen core, as in RetroArch) and
DuckStation. It has never been tested on a real PlayStation.

## How the translation was made

$how_made

## Credits

$credits

## Licence

The tools and patches' source are MIT; the English script and its context notes are
CC BY-SA 4.0 — both in the source archive attached to this release. These patches were
built from a clone of the repository at this release's tag, with `./make.sh import` on a
dump and then `./make.sh release`. *Boku no Natsuyasumi* is © Sony
Interactive Entertainment; this project distributes none of it and is not affiliated with
Sony or Millennium Kitchen. Paths in `code` above are files in the source archive.
