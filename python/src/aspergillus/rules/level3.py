"""NASA Level 3 rules: type safety + explicit error handling."""

from __future__ import annotations

import libcst as cst
from fixit import Invalid, LintRule, Valid

# ASP301 (RaiseInsteadOfResult) — RETIRED for Python (pebble asp-80c).
#
# ASP301 flagged any function with both a `raise` path and a `return
# <value>` path, prescribing a Result/Either type. That is a
# TypeScript/neverthrow / Rust / Haskell convention (model failure as a
# value, never throw). Python has NO ergonomic Result type and the MTM
# Python corpus does not use one, so an idiomatic guard clause
# (`if bad: raise ...; ...; return x`) is correct, standard Python — not
# an antipattern. The only way to satisfy the rule was to split every
# fallible function into a raise-only shell plus a pure-return half,
# doubling function count for zero benefit (no Result value threads
# through). The rule mis-prescribed on Python exactly as ASP202 did
# before asp-070/asp-da5 refined it.
#
# The genuinely-dangerous error-shaping patterns remain covered by the
# surviving L3 rules: ASP302 (OptionalReturnType) catches None-sentinel
# returns, and ASP303 (ErrorSwallowedIntoSentinel) catches an error
# swallowed into a success-typed falsy sentinel. Neither of those was
# ASP301's job; ASP301 caught only FP style, so nothing safety-relevant
# is uncovered by its removal. The Rust (`clippy::panic`/`unwrap_used`)
# and TypeScript (`no-throw` / neverthrow `must-consume-result`)
# analogues stay in force — those languages HAVE ergonomic Result types,
# so forcing their use there is a real standard, not dogma.


class OptionalReturnType(LintRule):
    """ASP302: Function returns Optional — consider stronger type.

    Functions annotated with `-> X | None` or `-> Optional[X]` use
    None as a sentinel for "no value" or "error." Consider using a
    Result type or raising (for __init__) to make the failure mode
    explicit.

    Exempt: __init__, dunders, test functions.
    """

    MESSAGE = "ASP302: Function returns Optional/None — consider Result type or stronger return"

    VALID = [
        Valid("def get_value() -> int:\n    assert True\n    assert True\n    return 42\n"),
        Valid("def __init__(self) -> None:\n    self.x = 1\n"),
        # asp-80c: an idiomatic guard-raise-then-return function (raise on a
        # bad input, then return a concrete non-Optional value) is correct,
        # standard Python — NOT flagged. This is the pattern the retired
        # ASP301 wrongly flagged; ASP302 must not pick it up in ASP301's
        # place (the return type is `int`, not Optional).
        Valid(
            "def parse(s: str) -> int:\n"
            "    assert isinstance(s, str)\n"
            "    assert len(s) > 0\n"
            "    if not s.isdigit():\n"
            "        raise ValueError('not a number')\n"
            "    return int(s)\n"
        ),
    ]
    INVALID = [
        Invalid(
            "def find(key: str) -> int | None:\n"
            "    assert isinstance(key, str)\n"
            "    assert len(key) > 0\n"
            "    return None\n"
        ),
        Invalid(
            "from typing import Optional\n"
            "def find(key: str) -> Optional[int]:\n"
            "    assert isinstance(key, str)\n"
            "    assert len(key) > 0\n"
            "    return None\n"
        ),
    ]

    EXEMPT_PREFIXES = ("test_", "__")

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        name = node.name.value
        if any(name.startswith(p) for p in self.EXEMPT_PREFIXES):
            return

        if node.returns is None:
            return

        annotation = node.returns.annotation
        if self._is_optional(annotation):
            self.report(node, self.MESSAGE)

    @staticmethod
    def _is_optional(node: cst.BaseExpression) -> bool:
        """Check if annotation is Optional[X] or X | None."""
        # X | None (BinaryOperation with BitOr)
        if isinstance(node, cst.BinaryOperation):
            if isinstance(node.operator, cst.BitOr):
                if (isinstance(node.right, cst.Name) and node.right.value == "None") or (
                    isinstance(node.left, cst.Name) and node.left.value == "None"
                ):
                    return True
        # Optional[X]
        if isinstance(node, cst.Subscript):
            if isinstance(node.value, cst.Name) and node.value.value == "Optional":
                return True
        return False


class ErrorSwallowedIntoSentinel(LintRule):
    """ASP303: empty/falsy literal returned from `except` — error swallowed.

    A ``return []`` / ``return {}`` / ``return ""`` / ``return 0`` (any
    empty or falsy literal) lexically inside an ``except`` handler, in a
    function whose return type is a bare success-shaped value (a list, a
    dict, a str — NOT ``Result[...]``/``Optional[...]``/``X | None``),
    conflates "the operation failed" with "the operation succeeded and
    produced nothing." The caller cannot tell a read error from a
    genuinely-empty result. Make the failure explicit: return a
    ``Result[T, E]`` (or re-raise) instead of a success sentinel.

    Live instance that motivated the rule: gateway
    ``laconic_registry._fetch_records_raw`` does
    ``except httpx.HTTPError: ... return []`` with a
    ``-> list[dict[str, Any]]`` annotation — a chain read failure is
    indistinguishable from "zero records on chain."

    Sibling to ASP302 (Optional return): both target a return shape that
    hides the error in the type. ASP303 is the one ASP302 misses — the
    error is swallowed into a *success-typed* falsy sentinel, so the
    None-sentinel (ASP302) heuristic does not fire. (ASP301, the former
    raise+return heuristic, is retired for Python — pebble asp-80c — as it
    mis-flagged idiomatic guard clauses; it never covered this
    swallowed-sentinel shape anyway.)

    Exempt: test functions, dunders; functions with no return annotation
    (cannot establish the success shape); and functions already returning
    ``Result[...]``/``Optional[...]``/``X | None``/``None`` (the error is
    already explicit, or the function returns nothing meaningful).
    """

    MESSAGE = (
        "ASP303: empty/falsy literal returned from `except` — error swallowed "
        "into a success sentinel; return Result"
    )

    VALID = [
        # Empty literal, but NOT inside an except handler.
        Valid("def f() -> list:\n    assert True\n    return []\n"),
        # asp-80c: an idiomatic guard-raise-then-return function (raise on a
        # bad input outside any `except`, then return a concrete value) is
        # correct, standard Python — NOT flagged. The retired ASP301 wrongly
        # flagged raise+return; ASP303 must not pick it up in its place (the
        # raise is a guard, not an error swallowed into a success sentinel).
        Valid(
            "def parse(s: str) -> int:\n"
            "    assert isinstance(s, str)\n"
            "    assert len(s) > 0\n"
            "    if not s.isdigit():\n"
            "        raise ValueError('not a number')\n"
            "    return int(s)\n"
        ),
        # Already returns Result — error is explicit in the type.
        Valid(
            "def f() -> Result[list, str]:\n"
            "    try:\n"
            "        return fetch()\n"
            "    except OSError:\n"
            "        return Err('boom')\n"
        ),
        # except re-raises rather than swallowing into a sentinel.
        Valid(
            "def f() -> list:\n"
            "    try:\n"
            "        return fetch()\n"
            "    except OSError:\n"
            "        raise\n"
        ),
        # except returns a non-empty value (not a falsy sentinel).
        Valid(
            "def f() -> list:\n"
            "    try:\n"
            "        return fetch()\n"
            "    except OSError:\n"
            "        return [fallback]\n"
        ),
        # `-> None` procedure: returning None from except is normal.
        Valid(
            "def f() -> None:\n    try:\n        do()\n    except OSError:\n        return None\n"
        ),
        # No return annotation — success shape cannot be established.
        Valid(
            "def f():\n    try:\n        return fetch()\n    except OSError:\n        return []\n"
        ),
    ]
    INVALID = [
        # `-> list` with `return []` in except.
        Invalid(
            "def f() -> list:\n"
            "    try:\n"
            "        return fetch()\n"
            "    except OSError:\n"
            "        return []\n"
        ),
        # `-> dict` with `return {}` in except.
        Invalid(
            "def f() -> dict:\n"
            "    try:\n"
            "        return fetch()\n"
            "    except OSError:\n"
            "        return {}\n"
        ),
        # `-> str` with `return ""` in except.
        Invalid(
            "def f() -> str:\n"
            "    try:\n"
            "        return fetch()\n"
            "    except OSError:\n"
            "        return ''\n"
        ),
        # The _fetch_records_raw shape: subscripted `-> list[...]`,
        # `except httpx.HTTPError: return []`.
        Invalid(
            "def _fetch_records_raw(q: str) -> list[dict[str, Any]]:\n"
            "    try:\n"
            "        return query(q)\n"
            "    except httpx.HTTPError:\n"
            "        return []\n"
        ),
    ]

    EXEMPT_PREFIXES = ("test_", "__")

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        name = node.name.value
        if any(name.startswith(p) for p in self.EXEMPT_PREFIXES):
            return

        # No annotation → cannot establish a success shape; don't fire.
        if node.returns is None:
            return

        if _is_explicit_error_annotation(node.returns.annotation):
            return

        if _has_falsy_return_in_except(node.body, in_except=False):
            self.report(node, self.MESSAGE)


def _is_explicit_error_annotation(node: cst.BaseExpression) -> bool:
    """True if the return type already makes failure explicit.

    Exempt shapes: ``Result[...]``, ``Optional[...]``, ``X | None``, and
    bare ``None`` (a procedure that returns nothing meaningful).
    """
    # X | None
    if isinstance(node, cst.BinaryOperation) and isinstance(node.operator, cst.BitOr):
        if (isinstance(node.right, cst.Name) and node.right.value == "None") or (
            isinstance(node.left, cst.Name) and node.left.value == "None"
        ):
            return True
    # Optional[X] / Result[...]
    if isinstance(node, cst.Subscript) and isinstance(node.value, cst.Name):
        if node.value.value in ("Optional", "Result"):
            return True
    # bare None
    if isinstance(node, cst.Name) and node.value == "None":
        return True
    return False


def _has_falsy_return_in_except(node: cst.CSTNode, in_except: bool) -> bool:
    """Search for `return <falsy-literal>` lexically inside an except handler.

    Does not descend into nested function definitions (their returns
    belong to their own signature). ``in_except`` becomes True once we
    cross an ``ExceptHandler`` boundary.
    """
    if isinstance(node, cst.Return) and in_except and node.value is not None:
        if _is_falsy_literal(node.value):
            return True
    for child in node.children:
        if not isinstance(child, cst.CSTNode):
            continue
        # Don't descend into nested functions.
        if isinstance(child, cst.FunctionDef):
            continue
        next_in_except = in_except or isinstance(child, cst.ExceptHandler)
        if _has_falsy_return_in_except(child, next_in_except):
            return True
    return False


_EMPTY_CONSTRUCTORS = frozenset({"list", "dict", "set", "tuple", "frozenset"})


def _is_falsy_literal(node: cst.BaseExpression) -> bool:
    """True for an empty/falsy literal: [] {} () "" 0 0.0 None False set()."""
    # None / False
    if isinstance(node, cst.Name) and node.value in ("None", "False"):
        return True
    # 0
    if isinstance(node, cst.Integer) and node.value.strip() in ("0", "0x0", "0o0", "0b0"):
        return True
    # 0.0
    if isinstance(node, cst.Float):
        stripped = node.value.replace("_", "")
        if stripped in ("0.0", "0.", ".0", "0"):
            return True
    # "" (empty string literal)
    if isinstance(node, cst.SimpleString) and node.raw_value == "":
        return True
    # [] {} ()
    if isinstance(node, (cst.List, cst.Tuple)) and len(node.elements) == 0:
        return True
    if isinstance(node, cst.Dict) and len(node.elements) == 0:
        return True
    # set()/dict()/list()/tuple()/frozenset() with no args
    if isinstance(node, cst.Call) and isinstance(node.func, cst.Name):
        if node.func.value in _EMPTY_CONSTRUCTORS and len(node.args) == 0:
            return True
    return False
