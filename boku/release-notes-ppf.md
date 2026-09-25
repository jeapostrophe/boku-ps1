
### Optional: the PPF, for DuckStation

While the release page lists it, `$ppf_bundle` is a separate download holding the same patch as a
PPF, with its own `PATCH.json`, `README.txt` and the cue sheet. DuckStation applies it
without patching anything: give `$ppf` your CHD's name with `.ppf` in place of `.chd`
(`Boku.chd` → `Boku.ppf`), put it beside the CHD, and tick *Settings → CD-ROM → Apply Image
Patches*, which is off by default. DuckStation checks nothing, and the hashes above are of
the extracted image, not the CHD — extract it once (steps 1 and 2) to check your dump.
