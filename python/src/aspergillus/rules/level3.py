"""NASA Level 3 rules: type safety + explicit error handling."""

from __future__ import annotations

from collections.abc import Iterator

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


class FailureDiscardsEvidence(LintRule):
    """ASP304: a surfaced failure references returncode but discards captured evidence.

    Flags the shape where a *failure representation* (an f-string, a
    ``str.format`` call, or a ``raise`` argument) embeds a process/gate
    result's ``.returncode`` while that same result's captured evidence —
    ``.stdout`` / ``.stderr`` / ``.output`` / ``.report`` — is in scope and
    is NEVER surfaced on that path. The evidence existed and was thrown
    away; the operator gets a one-bit summary of a failure whose cause was
    captured and dropped.

    Doctrinal ground: exophial ``docs/ORACLES.md`` §4.4 already outlaws the
    shape for oracle judgment — a verdict must observe "a real, well-typed,
    measured effect, not a one-bit exit code" — and this generalizes it to
    error surfacing everywhere. Reference violation: exophial ``exo-4f7``
    (the completion gate's PRESERVE reason is built from ``gate.returncode``
    while ``gate.report`` is discarded) and the dispatcher line
    ``f"... FAILED (returncode={r.returncode})"`` with ``r.stderr`` captured
    but unused — each cost real diagnostic time.

    A result is treated as *evidence-bearing* (evidence existed to discard)
    when, in the same function, EITHER:

    - it is bound from ``subprocess.run(..., capture_output=True)`` (or with
      an explicit ``stdout=`` / ``stderr=`` pipe kwarg) — a CompletedProcess
      carrying captured streams; OR
    - one of its evidence attributes (``.stdout`` / ``.stderr`` /
      ``.output`` / ``.report``) is referenced somewhere in the function — a
      GateResult-like value demonstrably carrying evidence.

    MUST NOT flag:

    1. *No capture.* ``subprocess.run`` without ``capture_output=True`` /
       ``stdout=`` / ``stderr=`` — no evidence was captured to discard.
    2. *Evidence surfaced.* The failure representation ALSO references an
       evidence attribute of the same result (any of stdout/stderr/output/
       report) — the cause is being reported.
    3. *Non-failure returncode use.* ``if r.returncode == 0`` guards, or
       returncode stored/returned as data, build no surfaced failure string,
       so nothing fires.

    Decidability boundary (honestly scoped, per LibCST's lack of type
    inference): the rule keys on *direct, same-function* attribute
    references. Two consequences are DELIBERATELY out of scope, documented
    rather than over-claimed:

    - A result whose evidence attribute is never referenced anywhere in the
      function AND is not bound from a capturing ``subprocess.run`` cannot be
      proven evidence-bearing (its type is invisible to the AST) and is not
      flagged.
    - Evidence surfaced only via an *intermediate variable*
      (``err = r.stderr`` then logged separately) is not tracked; exemption 2
      recognizes evidence referenced directly inside the failure
      representation.

    Sibling to ASP303 (error swallowed into a success sentinel): both target
    a failure that hides its cause — ASP303 in the return *type*, ASP304 in
    the surfaced *message*.
    """

    MESSAGE = (
        "ASP304: failure surfaces `returncode` but discards the captured evidence "
        "(.stdout/.stderr/.output/.report) of the same result — include it"
    )

    VALID = [
        # No capture: no evidence existed to discard.
        Valid(
            "import subprocess\n"
            "def run_plain() -> None:\n"
            "    r = subprocess.run(['pb', 'ready'])\n"
            "    if r.returncode != 0:\n"
            "        raise RuntimeError(f'failed rc={r.returncode}')\n"
        ),
        # Evidence surfaced: the failure message includes r.stderr.
        Valid(
            "import subprocess\n"
            "def run_gate() -> None:\n"
            "    r = subprocess.run(['pb', 'ready'], capture_output=True)\n"
            "    if r.returncode != 0:\n"
            "        raise RuntimeError(f'gate FAILED (rc={r.returncode}): {r.stderr}')\n"
        ),
        # Non-failure returncode use: a guard + returncode/evidence as data,
        # no surfaced failure string built from returncode.
        Valid(
            "import subprocess\n"
            "def run_ok() -> bytes:\n"
            "    r = subprocess.run(['pb', 'ready'], capture_output=True)\n"
            "    if r.returncode == 0:\n"
            "        return r.stdout\n"
            "    return r.stderr\n"
        ),
    ]
    INVALID = [
        # CompletedProcess: stderr captured, failure surfaces only returncode
        # (the dispatcher `f"... FAILED (returncode={r.returncode})"` shape).
        Invalid(
            "import subprocess\n"
            "def run_gate() -> None:\n"
            "    r = subprocess.run(['pb', 'ready'], capture_output=True)\n"
            "    if r.returncode != 0:\n"
            "        raise RuntimeError(f'gate FAILED (returncode={r.returncode})')\n"
        ),
        # GateResult-like: report used on the merge path, discarded on the
        # preserve path (the exo-4f7 completion.py PRESERVE-reason shape).
        Invalid(
            "def evaluate(gate) -> str:\n"
            "    if gate.returncode == 0:\n"
            "        return merge(gate.report)\n"
            "    return preserve(f'the re-run gate FAILED (returncode={gate.returncode})')\n"
        ),
    ]

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        body = node.body

        # Evidence-bearing results: bound from a capturing subprocess.run,
        # OR demonstrably carrying an evidence attribute somewhere in scope.
        evidence_bearing = _capture_bound_names(body) | _evidence_attr_names(body)
        if not evidence_bearing:
            return

        rc_surfaced, evidence_surfaced = _surfaced_result_vars(body)

        for name in rc_surfaced:
            if name in evidence_bearing and name not in evidence_surfaced:
                self.report(node, self.MESSAGE)
                return


_EVIDENCE_ATTRS = frozenset({"stdout", "stderr", "output", "report"})


def _walk_same_function(node: cst.CSTNode) -> Iterator[cst.CSTNode]:
    """Yield ``node`` and every descendant, NOT descending into a nested
    ``FunctionDef``/``Lambda`` (their attribute references belong to their own
    scope — same boundary as ``_search_for_type``)."""
    yield node
    for child in node.children:
        if not isinstance(child, cst.CSTNode):
            continue
        if isinstance(child, (cst.FunctionDef, cst.Lambda)):
            continue
        yield from _walk_same_function(child)


def _attr_of_name(node: cst.CSTNode) -> tuple[str, str] | None:
    """If ``node`` is ``X.attr`` with ``X`` a bare Name, return ``(X, attr)``."""
    if isinstance(node, cst.Attribute) and isinstance(node.value, cst.Name):
        return node.value.value, node.attr.value
    return None


def _is_subprocess_run(func: cst.BaseExpression) -> bool:
    """True for ``subprocess.run(...)`` or a bare ``run(...)`` (a
    ``from subprocess import run`` binding)."""
    if isinstance(func, cst.Attribute) and func.attr.value == "run":
        return isinstance(func.value, cst.Name) and func.value.value == "subprocess"
    return isinstance(func, cst.Name) and func.value == "run"


def _is_capturing_run(expr: cst.BaseExpression) -> bool:
    """True if ``expr`` is a ``subprocess.run`` call that captures output —
    ``capture_output=True`` or an explicit ``stdout=``/``stderr=`` pipe."""
    if not isinstance(expr, cst.Call) or not _is_subprocess_run(expr.func):
        return False
    for arg in expr.args:
        if arg.keyword is None:
            continue
        key = arg.keyword.value
        if (
            key == "capture_output"
            and isinstance(arg.value, cst.Name)
            and arg.value.value == "True"
        ):
            return True
        if key in ("stdout", "stderr"):
            return True
    return False


def _capture_bound_names(body: cst.CSTNode) -> set[str]:
    """Names bound in this function from a capturing ``subprocess.run`` call."""
    names: set[str] = set()
    for n in _walk_same_function(body):
        if isinstance(n, cst.Assign) and _is_capturing_run(n.value):
            for target in n.targets:
                if isinstance(target.target, cst.Name):
                    names.add(target.target.value)
        elif isinstance(n, cst.AnnAssign) and n.value is not None and _is_capturing_run(n.value):
            if isinstance(n.target, cst.Name):
                names.add(n.target.value)
    return names


def _evidence_attr_names(body: cst.CSTNode) -> set[str]:
    """Names on which an evidence attribute (.stdout/.stderr/.output/.report)
    is referenced anywhere in this function — proof the value carries evidence."""
    names: set[str] = set()
    for n in _walk_same_function(body):
        attr = _attr_of_name(n)
        if attr is not None and attr[1] in _EVIDENCE_ATTRS:
            names.add(attr[0])
    return names


def _is_failure_representation(node: cst.CSTNode) -> bool:
    """A node that surfaces a failure: an f-string, a ``.format()`` call, or a
    ``raise``. (Positional/%-style logging args are out of scope — documented.)"""
    if isinstance(node, (cst.FormattedString, cst.Raise)):
        return True
    return (
        isinstance(node, cst.Call)
        and isinstance(node.func, cst.Attribute)
        and node.func.attr.value == "format"
    )


def _surfaced_result_vars(body: cst.CSTNode) -> tuple[set[str], set[str]]:
    """Scan every failure representation in this function; return the names
    whose ``.returncode`` is surfaced and the names whose evidence attribute is
    surfaced inside one. ``if r.returncode == 0`` guards and ``return
    r.returncode`` data uses are NOT failure representations, so they never
    populate the returncode set (exemption 3)."""
    returncode_vars: set[str] = set()
    evidence_vars: set[str] = set()
    for surface in _walk_same_function(body):
        if not _is_failure_representation(surface):
            continue
        for inner in _walk_same_function(surface):
            attr = _attr_of_name(inner)
            if attr is None:
                continue
            if attr[1] == "returncode":
                returncode_vars.add(attr[0])
            elif attr[1] in _EVIDENCE_ATTRS:
                evidence_vars.add(attr[0])
    return returncode_vars, evidence_vars


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
