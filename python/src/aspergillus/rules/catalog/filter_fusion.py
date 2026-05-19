"""ASP402: filter-fusion.

Bird + de Moor 1997 §2.6:  ``filter p . filter q  ≡  filter (\\x -> q x && p x)``.
Catalog entry: ``aspergillus/docs/refactoring-catalog.md`` §
"Bird + de Moor 1997" → ``filter-fusion``.

Python-side analogue of
``aspergillus/typescript/ast-grep-rules/filter-fusion.yml``. Order
matters for side-effect-bearing predicates: the rewrite preserves
the original inner-then-outer evaluation order (the inner ``q``
runs first, then the outer ``p``).
"""

from __future__ import annotations

import libcst as cst
from fixit import Invalid, LintRule, Valid


class FilterFusion(LintRule):
    """ASP402: ``filter(p, filter(q, xs))`` → ``filter(lambda _x: q(_x) and p(_x), xs)``.

    Conservativeness:

    - Only fires when both ``filter`` calls have exactly two
      positional arguments (predicate + iterable).
    - Only fires when the call is ``filter`` by plain name. Re-bindings
      / ``itertools.filterfalse`` / partials don't trigger.
    - Evaluation order is preserved by emitting ``q(_x) and p(_x)``
      (inner predicate first, matching the original semantics where
      ``filter(p, filter(q, xs))`` evaluates ``q`` per element first
      then ``p`` on the survivors).
    - The inserted parameter binding ``_x`` is a fixed name; rename
      the call-site conflict before accepting the autofix.
    """

    MESSAGE = (
        "ASP402: Two adjacent filter() calls allocate an intermediate; "
        "fuse to filter(lambda _x: inner(_x) and outer(_x), xs)"
    )

    VALID = [
        Valid("list(filter(p, xs))\n"),
        Valid("list(filter(lambda _x: q(_x) and p(_x), xs))\n"),
        Valid("xs.filter(p).filter(q)\n"),  # method call shape
    ]
    INVALID = [
        Invalid(
            "list(filter(p, filter(q, xs)))\n",
            expected_replacement="list(filter(lambda _x: q(_x) and p(_x), xs))\n",
        ),
    ]

    def visit_Call(self, node: cst.Call) -> None:
        if not _is_unary_filter(node):
            return
        inner = _arg_value(node, position=1)
        if not isinstance(inner, cst.Call) or not _is_unary_filter(inner):
            return

        outer_pred = _arg_value(node, position=0)
        inner_pred = _arg_value(inner, position=0)
        iterable = _arg_value(inner, position=1)
        if outer_pred is None or inner_pred is None or iterable is None:
            return

        fused_lambda = _build_conjunction_lambda(inner_pred, outer_pred)
        replacement = node.with_changes(
            args=[
                cst.Arg(value=fused_lambda),
                cst.Arg(value=iterable),
            ],
        )
        self.report(node, self.MESSAGE, replacement=replacement)


def _is_unary_filter(node: cst.Call) -> bool:
    if not isinstance(node.func, cst.Name) or node.func.value != "filter":
        return False
    if len(node.args) != 2:
        return False
    return all(arg.keyword is None and not arg.star for arg in node.args)


def _arg_value(node: cst.Call, position: int) -> cst.BaseExpression | None:
    if position >= len(node.args):
        return None
    return node.args[position].value


def _build_conjunction_lambda(
    first: cst.BaseExpression,
    second: cst.BaseExpression,
) -> cst.Lambda:
    """Build ``lambda _x: first(_x) and second(_x)``.

    ``first`` runs before ``second`` (preserves evaluation order from
    the original inner-then-outer filter pair).
    """
    bound = cst.Name(value="_x")
    left = cst.Call(func=first, args=[cst.Arg(value=bound)])
    right = cst.Call(func=second, args=[cst.Arg(value=bound)])
    body = cst.BooleanOperation(left=left, operator=cst.And(), right=right)
    return cst.Lambda(
        params=cst.Parameters(params=[cst.Param(name=bound)]),
        body=body,
    )
