"""Catalog-move rules (ASP4xx).

Python-side analogues of the FP-leaning HIGH-LEVERAGE moves from
`aspergillus/docs/refactoring-catalog.md`. Each rule is a separate
module so its trigger, fix, and conservativeness notes live next to
each other; this package's ``__init__`` re-exports them so fixit's
``enable = ["aspergillus.rules"]`` config can discover them via the
parent ``aspergillus.rules`` package.

Tier semantics (see
`docs/decisions/2026-05-19-mtm-past-warn-promotion-phase.md`
+ `aspergillus/docs/decisions/2026-05-19-severity-graduation.md`):

- Tier 1 (autofix): ASP401 map-fusion, ASP402 filter-fusion,
  ASP403 eta-reduce, ASP404 redundant-conditional-bool. Each ships
  a ``replacement=`` on its ``self.report()`` call.
- Tier 2 (no autofix; detection-only): ASP406 tupling, ASP407
  worker-wrapper. Pattern detection identifies the opportunity;
  the move's safety depends on context the rule cannot mechanically
  verify (e.g., that ``rep`` and ``unrep`` are mutual inverses), so
  the developer/agent applies the move by hand. The pre-commit
  ratchet's count-baseline mechanism still gates these — see
  ``scripts/git-hooks/gateway-lint-ratchet.sh`` header.

Catalog citations are inline in each rule module via the
``aspergillus/docs/refactoring-catalog.md`` § anchor in the
docstring.

### Why no ASP405 redundant-await-return

The TS sibling rule
``aspergillus/typescript/ast-grep-rules/redundant-await-return.yml``
rewrites ``return await x`` → ``return x`` outside try-blocks. The
catalog cites JavaScript's auto-await-on-returned-promise semantics
("an async function automatically awaits the promise it returns
before resolving its own"). **This is a JS-specific guarantee that
Python does NOT share.** In Python:

    async def inner(): return 42
    async def outer(): return inner()   # returns the COROUTINE
                                        # OBJECT, not 42
    asyncio.run(outer())   # RuntimeWarning: coroutine 'inner'
                           # was never awaited

``return inner()`` in an async function does NOT await; it returns
the unawaited coroutine. ``return await inner()`` awaits and returns
the resolved value. The two are not equivalent, so the Python
analogue of the TS rule would corrupt observable behavior. The rule
is deliberately absent from the Python catalog. (Verified during
the catalog-moves-and-autofix-mode pebble: applying the analogous
rule to the gateway baseline broke 10 unit tests with
``coroutine ... was never awaited`` warnings.)
"""

from aspergillus.rules.catalog.anti_special_casing import AntiSpecialCasing
from aspergillus.rules.catalog.eta_reduce import EtaReduce
from aspergillus.rules.catalog.filter_fusion import FilterFusion
from aspergillus.rules.catalog.in_process_e2e import InProcessE2E
from aspergillus.rules.catalog.map_fusion import MapFusion
from aspergillus.rules.catalog.redundant_conditional_bool import (
    RedundantConditionalBoolAnd,
    RedundantConditionalBoolOr,
)
from aspergillus.rules.catalog.shell_to_self import ShellToSelf
from aspergillus.rules.catalog.tupling import Tupling
from aspergillus.rules.catalog.worker_wrapper import WorkerWrapper

__all__ = [
    "AntiSpecialCasing",
    "EtaReduce",
    "FilterFusion",
    "InProcessE2E",
    "MapFusion",
    "RedundantConditionalBoolAnd",
    "RedundantConditionalBoolOr",
    "ShellToSelf",
    "Tupling",
    "WorkerWrapper",
]
