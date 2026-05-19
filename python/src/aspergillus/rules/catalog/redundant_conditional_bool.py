"""ASP404: boolean-conditional collapse.

HLint hints ``Use ||`` / ``Use &&``. Catalog entry:
``aspergillus/docs/refactoring-catalog.md`` § "HLint corpus" →
``Boolean-Conditional Collapse``.

Python-side analogue of the paired TS rules
``aspergillus/typescript/ast-grep-rules/redundant-ternary-bool-true.yml``
and ``redundant-ternary-bool-false.yml``. Two sub-rules in one
module because they share the trigger family (``X if test else Y``
where one branch is a Boolean literal) and the conservativeness
notes overlap.

Rewrites encoded:

- ``True if X else Y``  →  ``X or Y``
- ``Y if X else False`` →  ``X and Y``

NOT encoded (deferred; would need a UnaryOperation insertion which
introduces operator-precedence sensitivity the autofix template
can't trivially guarantee):

- ``False if X else Y`` →  ``not X and Y``
- ``Y if X else True``  →  ``not X or Y``

Type-change caveat: the conditional expression has type
``Literal[True | False] | type(other)``; the short-circuit form has
type ``type(X) | type(Y)``. In boolean context this is equivalent;
elsewhere the static type narrows differently. The rule's message
states the caveat.
"""

from __future__ import annotations

import libcst as cst
from fixit import Invalid, LintRule, Valid


class RedundantConditionalBoolOr(LintRule):
    """ASP404a: ``True if X else Y`` → ``X or Y``.

    The conditional returns ``True`` when ``X`` is truthy and ``Y``
    otherwise; ``X or Y`` returns ``X`` (truthy) or ``Y``. In boolean
    context these are equivalent. The type changes from
    ``Literal[True] | type(Y)`` to ``type(X) | type(Y)``; inspect the
    surrounding type to confirm the truthy-coercion change is
    acceptable. (Catalog § Boolean-Conditional Collapse.)
    """

    MESSAGE = "ASP404: `True if X else Y` collapses to `X or Y` (boolean context)"

    VALID = [
        Valid("x = a or b\n"),
        Valid("x = True if a else False\n"),  # paired pattern — see ASP404b
        Valid("x = a if b else c\n"),  # neither branch is literal True/False
    ]
    INVALID = [
        Invalid(
            "x = True if cond else other\n",
            expected_replacement="x = cond or other\n",
        ),
    ]

    def visit_IfExp(self, node: cst.IfExp) -> None:
        if not _is_name_value(node.body, "True"):
            return
        # Exclude paired `True if X else False` (handled differently).
        if _is_name_value(node.orelse, "False"):
            return
        replacement = cst.BooleanOperation(
            left=node.test,
            operator=cst.Or(),
            right=node.orelse,
        )
        self.report(node, self.MESSAGE, replacement=replacement)


class RedundantConditionalBoolAnd(LintRule):
    """ASP404b: ``Y if X else False`` → ``X and Y``.

    The conditional returns ``Y`` when ``X`` is truthy and ``False``
    otherwise; ``X and Y`` returns ``X`` (falsy) or ``Y``. In boolean
    context these are equivalent. The type changes from
    ``type(Y) | Literal[False]`` to ``type(X) | type(Y)``; inspect
    the surrounding type to confirm the falsy-coercion change is
    acceptable.
    """

    MESSAGE = "ASP404: `Y if X else False` collapses to `X and Y` (boolean context)"

    VALID = [
        Valid("x = a and b\n"),
        Valid("x = a if b else c\n"),
        Valid("x = True if cond else other\n"),  # ASP404a's pattern
    ]
    INVALID = [
        Invalid(
            "x = other if cond else False\n",
            expected_replacement="x = cond and other\n",
        ),
    ]

    def visit_IfExp(self, node: cst.IfExp) -> None:
        if not _is_name_value(node.orelse, "False"):
            return
        # Exclude paired `True if X else False`: ASP404a's reduction
        # to `cond or False` is degenerate; better to leave to the
        # developer.
        if _is_name_value(node.body, "True"):
            return
        replacement = cst.BooleanOperation(
            left=node.test,
            operator=cst.And(),
            right=node.body,
        )
        self.report(node, self.MESSAGE, replacement=replacement)


def _is_name_value(expr: cst.BaseExpression, value: str) -> bool:
    """True iff ``expr`` is a bare ``Name`` with the given value.

    Used to detect the literal ``True`` / ``False`` keyword-name
    forms libcst represents as ``Name``.
    """
    return isinstance(expr, cst.Name) and expr.value == value
