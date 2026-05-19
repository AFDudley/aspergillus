"""ASP406: Tupling — multi-pass aggregation over the same iterable.

Bird, *Pearls of Functional Algorithm Design* 2010, Pearls 9 & 11;
technique introduced in Bird, "Tabulation Techniques for Recursive
Programs," ACM Comput. Surv. 1980. Catalog entry:
``aspergillus/docs/refactoring-catalog.md`` § "Bird Pearls 2010" →
``Tupling``.

**Ships without autofix** (Tier 2 per
``docs/decisions/2026-05-19-mtm-past-warn-promotion-phase.md``).

The Tupling move collapses two traversals over the same structure
into one traversal returning a tuple. The trigger is mechanically
detectable (two consecutive single-iterable builtins over the same
name), but the SAFE rewrite depends on context the rule cannot
mechanically verify:

- Is the iterable a one-shot generator? Then the first builtin
  exhausts it and the second sees an empty iterable — the two
  passes were NEVER equivalent, and "fusing" them is a no-op vs.
  a different shape entirely.
- Is the builtin pair commutative-with-each-other under a single
  pass? ``sum`` + ``max`` are; ``sum`` + ``next`` are not.
- Does the user actually want a single pass? Two passes may be
  intentional for readability or for caching pressure reasons.

Surfacing the opportunity is the rule's value. The developer (or
an L3 refinement agent invoked by the cascade) decides whether to
apply the move; if so, the rewrite is hand-written as a single
loop accumulating both values.

Catalog applicability: aggregation builtins {``sum``, ``max``,
``min``, ``len``, ``any``, ``all``} called consecutively in the
same function body with the same single positional argument (a
plain ``Name``) trigger the rule.
"""

from __future__ import annotations

import libcst as cst
from fixit import Invalid, LintRule, Valid

# Aggregation builtins that consume an iterable in one pass.
# ``len`` is included because two passes via ``sum`` + ``len`` over
# the same iterable is the prototypical Tupling trigger (mean
# computation).
_AGGREGATION_BUILTINS: frozenset[str] = frozenset(
    {"sum", "max", "min", "len", "any", "all"}
)


class Tupling(LintRule):
    """ASP406: Two passes over ``xs`` with aggregation builtins —
    consider a single-pass tuple/dataclass return (Tupling).

    Detection-only: surfaces the opportunity at the second pass.
    """

    MESSAGE = (
        "ASP406: Two passes over the same iterable with aggregation "
        "builtins — consider Tupling into a single-pass traversal "
        "returning a tuple"
    )

    VALID = [
        Valid("def stats(xs):\n    total = sum(xs)\n    return total\n"),
        # Different iterables: not a Tupling trigger.
        Valid(
            "def stats(xs, ys):\n"
            "    a = sum(xs)\n"
            "    b = sum(ys)\n"
            "    return a, b\n"
        ),
        # Separated by unrelated logic: trigger only on consecutive
        # statements (conservative).
        Valid(
            "def stats(xs):\n"
            "    a = sum(xs)\n"
            "    print('hi')\n"
            "    b = max(xs)\n"
            "    return a, b\n"
        ),
        # Non-builtin call: not in the aggregation set.
        Valid(
            "def stats(xs):\n"
            "    a = mean(xs)\n"
            "    b = stddev(xs)\n"
            "    return a, b\n"
        ),
    ]
    INVALID = [
        Invalid(
            "def stats(xs):\n"
            "    total = sum(xs)\n"
            "    biggest = max(xs)\n"
            "    return total, biggest\n"
        ),
        Invalid(
            "def stats(xs):\n"
            "    total = sum(xs)\n"
            "    count = len(xs)\n"
            "    return total / count\n"
        ),
    ]

    def visit_IndentedBlock(self, block: cst.IndentedBlock) -> None:
        previous: tuple[str, str] | None = None
        for stmt in block.body:
            current = _extract_aggregation(stmt)
            if current is not None and previous is not None:
                _prev_builtin, prev_iterable = previous
                cur_builtin, cur_iterable = current
                if prev_iterable == cur_iterable:
                    # Same iterable, two aggregation calls back-to-
                    # back. Surface on the second statement.
                    self.report(stmt, self.MESSAGE)
            previous = current


def _extract_aggregation(stmt: cst.BaseStatement) -> tuple[str, str] | None:
    """Return (builtin_name, iterable_name) if stmt is an aggregation
    assignment on a plain Name iterable, else None.

    Recognises ``a = builtin(xs)`` and ``a: T = builtin(xs)``. Excludes
    augmented assignment (``a += builtin(xs)``) because the semantics
    differ from a straight aggregation and the Tupling move applies
    awkwardly to in-place accumulation.
    """
    if not isinstance(stmt, cst.SimpleStatementLine):
        return None
    if len(stmt.body) != 1:
        return None
    inner = stmt.body[0]
    value: cst.BaseExpression | None
    if isinstance(inner, cst.Assign):
        value = inner.value
    elif isinstance(inner, cst.AnnAssign):
        value = inner.value
    else:
        return None
    if not isinstance(value, cst.Call):
        return None
    if not isinstance(value.func, cst.Name):
        return None
    if value.func.value not in _AGGREGATION_BUILTINS:
        return None
    if len(value.args) != 1:
        return None
    arg = value.args[0]
    if arg.keyword is not None or arg.star:
        return None
    if not isinstance(arg.value, cst.Name):
        return None
    return (value.func.value, arg.value.value)
