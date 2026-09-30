"""Tools for the boku-ps1 English translation patch.

Everything here reads or writes a contributor's own dump of SCPS-10088; none of the
game's content lives in this repo (TECHNICAL principle 2).
"""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
"""The checkout this package was imported from — one home for it, not one per module."""

try:
    __version__ = version("boku")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0+unknown"
"""The version `pyproject.toml` declares — one home for it, not two (`DOC-3`)."""
