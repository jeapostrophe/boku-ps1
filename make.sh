#!/usr/bin/env bash
# Every recurring command in this project is a verb here (CLAUDE.md § "Tooling is Python").
# Add a verb rather than documenting a command line somewhere else.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

usage() {
    cat >&2 <<'EOF'
usage: ./make.sh <verb> [arguments]

  import [SOURCE] [--out DIR]   write the image and its files from your own dump
                                (./make.sh import --help for the source kinds)
  extract [arguments]           decode your import's script into disc/script/
                                (./make.sh extract --help for the switches)
  research-tsv                  regenerate research/data/*.tsv from your import; a
                                test diffs them against the tracked copies, which is
                                the gate on the walk
  trial [arguments]             build the TXT-04 trial image into build/trial/
                                (./make.sh trial --help for the switches)
  patch [arguments]             emit the release patches into build/patch/
                                (./make.sh patch --help for the switches)
  apply-patch ORIG PATCH --out FILE
                                apply one of our patches, checking both hashes
  test [pytest arguments]       run the test suite
  lint                          ruff check + format check

Everything runs through uv, which installs Python and the dev tools on first use.
EOF
}

verb="${1:-}"
shift || true

case "$verb" in
    import)
        exec uv run boku import "$@"
        ;;
    extract)
        exec uv run boku extract "$@"
        ;;
    research-tsv)
        # The port's gate: the tables have to come back byte for byte. `git diff
        # research/data` afterwards is the answer.
        exec uv run boku extract --research-tsv research/data "$@"
        ;;
    trial)
        exec uv run boku trial "$@"
        ;;
    patch)
        exec uv run boku patch "$@"
        ;;
    apply-patch)
        exec uv run boku apply-patch "$@"
        ;;
    test)
        exec uv run pytest "$@"
        ;;
    lint)
        uv run ruff check .
        exec uv run ruff format --check .
        ;;
    ""|-h|--help|help)
        usage
        exit 0
        ;;
    *)
        echo "./make.sh: unknown verb '$verb'" >&2
        usage
        exit 2
        ;;
esac
