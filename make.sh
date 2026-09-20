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
