"""aspergillus — NASA-grade Python linter."""

from importlib.metadata import PackageNotFoundError, version

# Single source of truth for the version is the distribution metadata
# (pyproject.toml ``[project].version``). Read it back at import time so a
# parity check can compare ``aspergillus.__version__`` /
# ``importlib.metadata.version("aspergillus")`` against the vendored subtree
# version without a second hand-maintained literal that could drift.
# When the package is not installed as a distribution (imported straight
# from source, as the acceptance probes in scripts/ do under bare
# python3), no distribution metadata exists, so the lookup falls back to a
# fixed placeholder string.
try:
    __version__ = version("aspergillus")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
