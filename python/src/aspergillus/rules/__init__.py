"""Fixit lint rules organized by NASA quality level + catalog moves.

The ``level2`` and ``level3`` modules contain the structural rules
(ASP2xx, ASP3xx); each lives as a sibling .py file and is auto-
discovered by fixit's ``walk_module`` over this package's ``__path__``.

The ``catalog`` subpackage contains the catalog-move rules (ASP4xx)
with one rule per file. Fixit's rule discovery does NOT recurse into
sub-packages (see ``fixit/config.py`` ``walk_module``: ``if not is_pkg:
# do not recurse to sub-packages``), so the catalog rules are
re-exported here at the parent package level. The re-export makes them
``inspect.getmembers``-visible on ``aspergillus.rules`` itself, which
IS the level fixit walks when its config enables ``aspergillus.rules``.

If a future fixit release recurses into sub-packages, this re-export
becomes redundant and can be removed; until then, this is the load-
bearing seam that lets one-rule-per-file in ``catalog/`` coexist with
fixit's flat-only discovery.
"""

from aspergillus.rules.catalog import (
    AntiSpecialCasing,
    EtaReduce,
    FilterFusion,
FsmEdgeDuration,
    FsmRedundantBranches,
    FsmStringlyDispatch,
    InProcessE2E,
    MapFusion,
    RedundantConditionalBoolAnd,
    RedundantConditionalBoolOr,
    Tupling,
    WorkerWrapper,
)

__all__ = [
    "AntiSpecialCasing",
    "EtaReduce",
    "FilterFusion",
"FsmEdgeDuration",
    "FsmRedundantBranches",
    "FsmStringlyDispatch",
    "InProcessE2E",
    "MapFusion",
    "RedundantConditionalBoolAnd",
    "RedundantConditionalBoolOr",
    "Tupling",
    "WorkerWrapper",
]
