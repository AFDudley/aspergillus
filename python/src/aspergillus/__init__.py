"""aspergillus — NASA-grade Python linter."""

from importlib.metadata import version

# Single source of truth for the version is the distribution metadata
# (pyproject.toml ``[project].version``). Read it back at import time so a
# parity check can compare ``aspergillus.__version__`` /
# ``importlib.metadata.version("aspergillus")`` against the vendored subtree
# version without a second hand-maintained literal that could drift.
# The package is always installed (editable in-monorepo, or a resolved wheel /
# git pin standalone) when it is importable, so this never falls back.
__version__ = version("aspergillus")

__all__ = ["__version__"]
