"""ASP403: eta-reduction.

Church, *The Calculi of Lambda-Conversion* 1941, η-conversion;
HLint hint ``Eta reduce``. Catalog entry:
``aspergillus/docs/refactoring-catalog.md`` § "HLint corpus" →
``Eta-Reduction / Eta-Expansion``.

Python-side analogue of
``aspergillus/typescript/ast-grep-rules/eta-reduce-arrow.yml``.
The same conservativeness applies: only reduce when the callee is
a plain identifier (Name). Method calls (``obj.method(x)``) and
attribute references (``mod.f(x)``) are NOT safe to eta-reduce in
Python — descriptor protocol (``__get__``) and bound-method
identity make the extracted reference observationally distinct
from the lambda. The rule encodes this in the pattern (false
negative preferred to false positive).
"""

from __future__ import annotations

import libcst as cst
from fixit import Invalid, LintRule, Valid


class EtaReduce(LintRule):
    """ASP403: ``lambda x: f(x)`` → ``f`` (when ``f`` is a plain name).

    Conservativeness:

    - Lambda must have exactly one positional parameter, no
      annotation, no default, no ``*args``, no ``**kwargs``, no
      keyword-only or positional-only params.
    - Lambda body must be ``Call(Name(f), [Arg(Name(x))])`` where
      the call has exactly one positional argument equal to the
      lambda's bound name, no star/keyword, and the callee is a
      bare ``Name`` (not ``Attribute``, ``Subscript``, ``Call``,
      etc.). This deliberately excludes ``lambda x: obj.method(x)``
      because Python's bound-method semantics make the eta-reduced
      reference observationally distinct (different ``id``, possibly
      different lifetime).
    - The callee Name must NOT be the same as the bound parameter
      name (would produce infinite recursion under eta-reduction).
    """

    MESSAGE = "ASP403: Eta-reduce lambda to bare function reference"

    VALID = [
        Valid("xs = list(map(f, [1, 2, 3]))\n"),
        # Method call — NOT safe to eta-reduce.
        Valid("xs = list(map(lambda x: obj.method(x), [1, 2, 3]))\n"),
        # Attribute access — NOT safe.
        Valid("xs = list(map(lambda x: mod.f(x), [1, 2, 3]))\n"),
        # Multi-arg lambda — out of scope for the unary rule.
        Valid("xs = list(map(lambda x, y: f(x, y), pairs))\n"),
        # Different arg name than parameter — not eta-reducible.
        Valid("xs = list(map(lambda x: f(y), [1, 2, 3]))\n"),
        # Lambda with default — out of scope.
        Valid("xs = list(map(lambda x=1: f(x), [1, 2, 3]))\n"),
    ]
    INVALID = [
        Invalid(
            "xs = list(map(lambda x: f(x), [1, 2, 3]))\n",
            expected_replacement="xs = list(map(f, [1, 2, 3]))\n",
        ),
        Invalid(
            "xs = list(map(lambda y: g(y), [1, 2, 3]))\n",
            expected_replacement="xs = list(map(g, [1, 2, 3]))\n",
        ),
    ]

    def visit_Lambda(self, node: cst.Lambda) -> None:
        params = node.params
        # Reject any non-trivial parameter shape.
        if len(params.params) != 1:
            return
        if params.kwonly_params:
            return
        if params.posonly_params:
            return
        if params.star_arg is not cst.MaybeSentinel.DEFAULT:
            return
        if params.star_kwarg is not None:
            return
        param = params.params[0]
        if param.default is not None:
            return
        if param.annotation is not None:
            return
        if param.star:
            return

        bound_name = param.name.value

        # Body must be Call(Name(f), [Arg(Name(bound_name))]).
        body = node.body
        if not isinstance(body, cst.Call):
            return
        if not isinstance(body.func, cst.Name):
            return
        callee_name = body.func.value
        if callee_name == bound_name:
            return  # Would be infinite recursion.
        if len(body.args) != 1:
            return
        arg = body.args[0]
        if arg.keyword is not None:
            return
        if arg.star:
            return
        if not isinstance(arg.value, cst.Name):
            return
        if arg.value.value != bound_name:
            return

        # Safe to reduce: replace the entire lambda with just the
        # function reference.
        replacement = cst.Name(value=callee_name)
        self.report(node, self.MESSAGE, replacement=replacement)
