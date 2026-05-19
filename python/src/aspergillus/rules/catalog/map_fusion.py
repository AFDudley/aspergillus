"""ASP401: map-fusion.

Bird + de Moor 1997 §2.6 "Fusion laws":  ``map f . map g  ≡  map (f . g)``.
Catalog entry: ``aspergillus/docs/refactoring-catalog.md`` §
"Bird + de Moor 1997 (Bird-Meertens formalism)" → ``map-fusion``.

Python-side analogue of
``aspergillus/typescript/ast-grep-rules/map-fusion.yml``. Same
direction (fuse two ``map`` calls into one whose function composes
the originals), same caveat about the inserted lambda parameter
name (``_x``).
"""

from __future__ import annotations

import libcst as cst
from fixit import Invalid, LintRule, Valid


class MapFusion(LintRule):
    """ASP401: ``map(g, map(f, xs))`` → ``map(lambda _x: g(f(_x)), xs)``.

    Two adjacent ``map`` calls allocate the intermediate iterator and
    advance it lazily; fusing them composes the functions and visits
    each element of the source iterable exactly once.

    Conservativeness:

    - Only fires when BOTH outer and inner ``map`` calls have exactly
      two positional arguments (function + iterable). Python's
      ``map`` accepts ``map(f, xs, ys, ...)`` with N iterables, but
      the fusion law specialises to the unary form; we don't fuse
      multi-iterable maps.
    - Only fires when the call is ``map`` by plain name (not
      ``itertools.map`` or any rebinding) — the lookup-time identity
      of ``map`` matters for the rewrite's correctness.
    - The inserted parameter binding ``_x`` is a fixed name. If the
      call site already binds ``_x`` in the same scope, the developer
      should rename the conflict before accepting the autofix
      (matches the TS rule's caveat).
    """

    MESSAGE = (
        "ASP401: Two adjacent map() calls allocate an intermediate; "
        "fuse to map(lambda _x: outer(inner(_x)), xs)"
    )

    VALID = [
        Valid("list(map(f, xs))\n"),
        Valid("list(map(lambda _x: g(f(_x)), xs))\n"),
        # Multi-iterable map: not the fusion shape.
        Valid("list(map(f, xs, ys))\n"),
        # Method call (`.map`), not the builtin `map`: doesn't trigger.
        Valid("xs.map(f).map(g)\n"),
    ]
    INVALID = [
        Invalid(
            "list(map(g, map(f, xs)))\n",
            expected_replacement="list(map(lambda _x: g(f(_x)), xs))\n",
        ),
    ]

    def visit_Call(self, node: cst.Call) -> None:
        if not _is_unary_map(node):
            return
        inner = _unary_arg(node, position=1)
        if inner is None or not isinstance(inner, cst.Call):
            return
        if not _is_unary_map(inner):
            return

        outer_fn = _unary_arg(node, position=0)
        inner_fn = _unary_arg(inner, position=0)
        iterable = _unary_arg(inner, position=1)
        if outer_fn is None or inner_fn is None or iterable is None:
            return

        # Build: lambda _x: outer_fn(inner_fn(_x))
        fused_lambda = _build_compose_lambda(outer_fn, inner_fn)
        replacement = node.with_changes(
            args=[
                cst.Arg(value=fused_lambda),
                cst.Arg(value=iterable),
            ],
        )
        self.report(node, self.MESSAGE, replacement=replacement)


def _is_unary_map(node: cst.Call) -> bool:
    """True iff node is ``map(<expr>, <expr>)`` (plain name, two positional args)."""
    if not isinstance(node.func, cst.Name) or node.func.value != "map":
        return False
    if len(node.args) != 2:
        return False
    for arg in node.args:
        if arg.keyword is not None:
            return False
        if arg.star:
            return False
    return True


def _unary_arg(node: cst.Call, position: int) -> cst.BaseExpression | None:
    """Return the ``position``-th positional arg's value, or None."""
    if position >= len(node.args):
        return None
    return node.args[position].value


def _build_compose_lambda(
    outer: cst.BaseExpression,
    inner: cst.BaseExpression,
) -> cst.Lambda:
    """Build ``lambda _x: outer(inner(_x))``.

    The fixed parameter name ``_x`` matches the TS map-fusion rule
    (see catalog § map-fusion caveat).
    """
    bound = cst.Name(value="_x")
    inner_call = cst.Call(func=inner, args=[cst.Arg(value=bound)])
    outer_call = cst.Call(func=outer, args=[cst.Arg(value=inner_call)])
    return cst.Lambda(
        params=cst.Parameters(params=[cst.Param(name=bound)]),
        body=outer_call,
    )
