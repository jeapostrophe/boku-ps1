"""`python -m boku` -- the same entry point as the `boku` console script."""

import sys

from boku.cli import main

if __name__ == "__main__":
    sys.exit(main())
