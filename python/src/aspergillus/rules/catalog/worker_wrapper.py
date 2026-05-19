"""ASP407: Worker/Wrapper — trivial pass-through wrapper.

Gill + Hutton, "The Worker/Wrapper Transformation," J. Funct.
Program. 19(2), 2009. Catalog entry:
``aspergillus/docs/refactoring-catalog.md`` § "Gill + Hutton 2009" →
``Worker / Wrapper``.

**Ships without autofix** (Tier 2 per
``docs/decisions/2026-05-19-mtm-past-warn-promotion-phase.md``).

Worker/Wrapper introduces a fast inner representation behind a
clear outer interface: ``wrap = unrep . work . rep``. The
factorization theorem guarantees ``wrap`` is observationally equal
to the slow direct version when ``unrep . rep = id``.

Detecting "this function is a wrapper that should be split into
wrapper + worker" requires understanding which work is the
``rep`` / ``work`` / ``unrep`` decomposition — that's a design
decision the rule cannot mechanically make. What the rule CAN
mechanically detect is the *trivial pass-through wrapper* shape:

    def f(*args, **kwargs):
        return g(*args, **kwargs)

This is one of two things, and both deserve the developer's
attention:

1. A wrapper that's about to grow ``rep`` / ``unrep`` logic in
   subsequent commits — the rule reminds the developer the
   factorization theorem governs what they're building.
2. A wrapper that exists only to rename ``g`` to ``f`` — Inline
   Function (Fowler ch. 6) probably applies; delete the wrapper
   and inline at call sites.

The rule's value is surfacing the choice. The developer accepts
the lint by either (a) adding the worker/wrapper factorization
logic that justifies the indirection, or (b) inlining and
deleting the wrapper.

Conservativeness:

- Trigger ONLY when the function body is exactly one statement
  that is ``return <Call>``.
- Trigger ONLY when the Call's callee is a plain ``Name`` (not
  ``self.method``, not ``obj.attr.method``, not a subscript).
- Trigger ONLY when the wrapped call's args are exactly the
  function's positional params, in order, with no extras or
  reordering. (A wrapper that reorders args or adds defaults is
  doing more than pass-through; out of scope.)
- Exempt: dunder methods (``__init__``, ``__call__``, etc.),
  test functions (``test_``-prefixed), and async functions
  (async wrappers around sync workers are a legitimate adapter
  shape that this rule shouldn't flag).
"""

from __future__ import annotations

import libcst as cst
from fixit import Invalid, LintRule, Valid

_EXEMPT_PREFIXES: tuple[str, ...] = ("test_", "__")


class WorkerWrapper(LintRule):
    """ASP407: Trivial pass-through wrapper — apply Worker/Wrapper
    factorization or inline the wrapper.
    """

    MESSAGE = (
        "ASP407: Trivial pass-through wrapper — either factor into "
        "Worker/Wrapper (introduce rep/unrep) or inline the wrapper"
    )

    VALID = [
        # Non-trivial body — not pass-through.
        Valid(
            "def f(x):\n"
            "    y = x + 1\n"
            "    return g(y)\n"
        ),
        # Reordered args — not a trivial pass-through.
        Valid(
            "def f(x, y):\n"
            "    return g(y, x)\n"
        ),
        # Extra args — not a trivial pass-through.
        Valid(
            "def f(x):\n"
            "    return g(x, 42)\n"
        ),
        # Method call — bound-method indirection has its own rules.
        Valid(
            "def f(x):\n"
            "    return self.g(x)\n"
        ),
        # Dunder exempt.
        Valid(
            "def __call__(self, x):\n"
            "    return self._fn(x)\n"
        ),
        # Async wrapper — legitimate adapter.
        Valid(
            "async def f(x):\n"
            "    return await g(x)\n"
        ),
        # Test function exempt.
        Valid(
            "def test_foo(x):\n"
            "    return g(x)\n"
        ),
    ]
    INVALID = [
        Invalid(
            "def f(x):\n    return g(x)\n",
        ),
        Invalid(
            "def f(x, y):\n    return g(x, y)\n",
        ),
    ]

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        name = node.name.value
        if any(name.startswith(p) for p in _EXEMPT_PREFIXES):
            return
        # Async wrappers are legitimate (sync-to-async adapter).
        if node.asynchronous is not None:
            return

        # Body must be a single statement: `return Call(Name(...), args)`.
        body = node.body
        if not isinstance(body, cst.IndentedBlock):
            return
        if len(body.body) != 1:
            return
        only = body.body[0]
        if not isinstance(only, cst.SimpleStatementLine):
            return
        if len(only.body) != 1:
            return
        ret = only.body[0]
        if not isinstance(ret, cst.Return) or ret.value is None:
            return
        call = ret.value
        if not isinstance(call, cst.Call):
            return
        if not isinstance(call.func, cst.Name):
            return
        if call.func.value == name:
            return  # Self-recursion, not a wrapper.

        # The wrapper's positional params, in declaration order.
        wrapper_param_names = _positional_param_names(node.params)
        if wrapper_param_names is None:
            return

        # The call's positional arg names, in call order. Reject if
        # any arg is non-Name, keyword, or starred.
        call_arg_names = _positional_arg_names(call)
        if call_arg_names is None:
            return

        if call_arg_names != wrapper_param_names:
            return

        self.report(node, self.MESSAGE)


def _positional_param_names(params: cst.Parameters) -> list[str] | None:
    """Return the wrapper's positional param names, or None if the
    parameter list has shapes the rule excludes (defaults, *args,
    **kwargs, annotations don't matter — only structural shape).
    """
    if params.star_arg is not cst.MaybeSentinel.DEFAULT:
        return None
    if params.star_kwarg is not None:
        return None
    if params.kwonly_params:
        return None
    names: list[str] = []
    for p in (*params.posonly_params, *params.params):
        if p.default is not None:
            return None
        if p.star:
            return None
        names.append(p.name.value)
    return names


def _positional_arg_names(call: cst.Call) -> list[str] | None:
    """Return arg names if every Call arg is a plain positional
    ``Name``, else None.
    """
    names: list[str] = []
    for arg in call.args:
        if arg.keyword is not None:
            return None
        if arg.star:
            return None
        if not isinstance(arg.value, cst.Name):
            return None
        names.append(arg.value.value)
    return names
