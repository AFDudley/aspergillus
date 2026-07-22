"""ASP413: FSM enum dispatch must be checkable for exhaustiveness.

Verification-integrity family; sibling to ASP408 anti-special-casing,
ASP409 shell-to-self, and ASP410 in-process-e2e. Where those three guard
the honesty of a test/verification seam, ASP413 guards a state-machine
correctness seam: whether an enum-typed dispatch can even be checked for
exhaustiveness by the type checker.

Motivation
----------
mypy's ``exhaustive-match`` error code only fires inside ``match`` /
``assert_never`` forms. An ``if``/``elif`` chain that dispatches on a
single Enum-typed subject (comparing it with ``is``/``==`` against Enum
members) silently opts out of that check: add a new enum member later and
the chain falls through unnoticed, landing on whatever the trailing
fallthrough does (or nothing, if there isn't one) instead of a
statically-caught error. A ``match`` statement ending in
``case _: assert_never(subject)`` (or an ``if``/``elif`` chain whose final
``else`` is exactly ``assert_never(subject)``) makes the omission a type
error instead of a runtime surprise — that is the only shape this rule
accepts for an enum-typed dispatch.

Reject severity, no autofix
----------------------------
This is a **reject-severity** rule, not a Tier 2 severity-graduation
candidate (contrast ASP406/407/408/409/410, which land at warn and
promote once a consumer's tree is clean per
``docs/decisions/2026-05-19-mtm-past-warn-promotion-phase.md``). An
unguarded enum if/elif dispatch is a structural gap in exhaustiveness
checking with no ambiguity about whether it is wanted — it blocks from
the day the rule is enabled. There is no mechanical autofix: rewriting an
if/elif chain into a ``match`` statement (or appending the right
``else: assert_never(subject)``) requires picking the correct fallback
behavior for unmatched values, which is a human/agent judgment call, so
the rule surfaces the violation without a ``replacement=``.

Ported from ``scripts/check_asp_fsm_enum_dispatch.py`` (pebble
``asp-26e``); this rule reimplements that AST-based checker's pure
predicates directly over the LibCST tree so violations are caught by the
same ``fixit lint`` pass as every other aspergillus rule instead of a
standalone script nothing's gate invokes.

Scope
-----
Only single-target ``==``/``is`` comparisons against a bare
``<EnumClass>.<MEMBER>`` attribute access count as an enum dispatch
branch; comparisons against non-enum values, or against enum classes not
defined in the same module, are out of scope (mirrors the source
checker's ``_enum_class_names`` restriction to module-local ``Enum``
subclasses). A ``match`` statement is never flagged directly — it is
already the exhaustiveness-checkable form — regardless of whether it ends
in ``assert_never``; only ``if``/``elif`` chains are inspected.
"""

from __future__ import annotations

from collections.abc import Sequence

import libcst as cst
from fixit import Invalid, LintRule, Valid

ENUM_BASE_NAMES: frozenset[str] = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"})


def _base_name(base: cst.Arg) -> str | None:
    """Pure: the bare class name of a class-statement base-class arg, or None."""
    value = base.value
    if isinstance(value, cst.Name):
        return value.value
    if isinstance(value, cst.Attribute):
        return value.attr.value
    return None


def _enum_class_names(module: cst.Module) -> frozenset[str]:
    """Pure: names of classes in ``module`` that subclass a known Enum base."""
    return frozenset(
        node.name.value
        for node in _walk(module)
        if isinstance(node, cst.ClassDef)
        and any(_base_name(base) in ENUM_BASE_NAMES for base in node.bases)
    )


def _walk(node: cst.CSTNode) -> Sequence[cst.CSTNode]:
    """Pure: every descendant of ``node`` (node itself excluded), any order."""
    descendants: list[cst.CSTNode] = []
    frontier = list(node.children)
    while frontier:
        current = frontier.pop()
        descendants.append(current)
        frontier.extend(current.children)
    return descendants


def _render(node: cst.CSTNode) -> str:
    """Pure: source text for ``node``, used to compare two subject expressions
    structurally without relying on identity."""
    return cst.Module(body=[]).code_for_node(node)


def _is_enum_member_access(node: cst.BaseExpression, enum_names: frozenset[str]) -> bool:
    """Pure: True iff ``node`` is ``<EnumClass>.<MEMBER>`` for a known enum."""
    return (
        isinstance(node, cst.Attribute)
        and isinstance(node.value, cst.Name)
        and node.value.value in enum_names
    )


def _enum_dispatch_subject(test: cst.BaseExpression, enum_names: frozenset[str]) -> str | None:
    """Pure: if ``test`` compares one side against an enum member, return the
    rendered source of the other (subject) side; else None."""
    if not isinstance(test, cst.Comparison) or len(test.comparisons) != 1:
        return None
    target = test.comparisons[0]
    if not isinstance(target.operator, cst.Equal | cst.Is):
        return None
    left, right = test.left, target.comparator
    if _is_enum_member_access(right, enum_names):
        return _render(left)
    if _is_enum_member_access(left, enum_names):
        return _render(right)
    return None


def _as_expr(stmt: cst.CSTNode) -> cst.Expr | None:
    """Pure: the bare ``cst.Expr`` a suite statement wraps, for both the
    multi-line (``SimpleStatementLine``) and same-line (``SimpleStatementSuite``
    element, already a ``BaseSmallStatement``) ``else`` forms."""
    if isinstance(stmt, cst.SimpleStatementLine) and len(stmt.body) == 1:
        stmt = stmt.body[0]
    return stmt if isinstance(stmt, cst.Expr) else None


def _is_assert_never_call(stmt: cst.CSTNode, subject_source: str) -> bool:
    """Pure: True iff ``stmt`` is exactly ``assert_never(<subject>)``."""
    expr = _as_expr(stmt)
    if expr is None or not isinstance(expr.value, cst.Call):
        return False
    call = expr.value
    func = call.func
    name = None
    if isinstance(func, cst.Name):
        name = func.value
    elif isinstance(func, cst.Attribute):
        name = func.attr.value
    if name != "assert_never" or len(call.args) != 1:
        return False
    return _render(call.args[0].value) == subject_source


def _final_else_body(node: cst.If) -> Sequence[cst.CSTNode]:
    """Pure: walk an if/elif chain (elif == nested If in orelse) to the
    statements of its final ``else`` block, or empty if there is none."""
    current = node
    while isinstance(current.orelse, cst.If):
        current = current.orelse
    if isinstance(current.orelse, cst.Else):
        return current.orelse.body.body
    return ()


def chain_elif_ids(node: cst.If) -> frozenset[int]:
    """Pure: object ids of the If nodes in ``node``'s orelse chain (the elifs)."""
    ids: set[int] = set()
    current = node
    while isinstance(current.orelse, cst.If):
        current = current.orelse
        ids.add(id(current))
    return frozenset(ids)


def is_unguarded_enum_dispatch(node: cst.If, enum_names: frozenset[str]) -> bool:
    """Pure: True iff ``node`` heads an if/elif chain dispatching on a
    module-local enum with no ``else: assert_never(subject)`` guard."""
    subject_source = _enum_dispatch_subject(node.test, enum_names)
    if subject_source is None:
        return False  # not an enum-typed dispatch at all -- out of scope
    final_else = _final_else_body(node)
    if len(final_else) == 1 and _is_assert_never_call(final_else[0], subject_source):
        return False
    return True


class FsmEnumDispatchExhaustive(LintRule):
    """ASP413: an if/elif chain dispatching on an Enum-typed subject must be
    exhaustiveness-checkable — either rewritten as a ``match`` statement, or
    ending in ``else: assert_never(subject)``.

    Reject-severity (blocking), no autofix: the correct fallback behavior for
    an unmatched value is a human/agent decision.
    """

    MESSAGE = (
        "ASP413: if/elif dispatch on an Enum-typed value is not "
        "exhaustiveness-checkable — mypy's `exhaustive-match` only fires "
        "inside `match`/`assert_never` forms, so a new enum member added "
        "later falls through unnoticed. Rewrite as a `match` statement, or "
        "end the chain with `else: assert_never(<subject>)`."
    )

    #: Object ids of If nodes already accounted for as an elif of a chain
    #: already checked at its head — avoids re-reporting the same chain once
    #: per elif branch. Reset per module.
    _handled_elif_ids: frozenset[int]
    #: Enum classes defined in the current module. Reset per module.
    _enum_names: frozenset[str]

    def visit_Module(self, node: cst.Module) -> None:
        # Rule instances may be reused across files by the fixit engine.
        self._handled_elif_ids = frozenset()
        self._enum_names = _enum_class_names(node)

    def visit_If(self, node: cst.If) -> None:
        if id(node) in self._handled_elif_ids:
            return  # already covered as an elif of a chain checked at its head
        self._handled_elif_ids |= chain_elif_ids(node)
        if is_unguarded_enum_dispatch(node, self._enum_names):
            self.report(node, self.MESSAGE)

    VALID = [
        # match statement ending in assert_never -- the accepted shape.
        Valid(
            "from enum import Enum\n"
            "from typing import assert_never\n"
            "\n"
            "class Phase(Enum):\n"
            "    PENDING = 'pending'\n"
            "    RUNNING = 'running'\n"
            "    DONE = 'done'\n"
            "\n"
            "def handle(phase: Phase) -> str:\n"
            "    match phase:\n"
            "        case Phase.PENDING:\n"
            "            return 'waiting'\n"
            "        case Phase.RUNNING:\n"
            "            return 'working'\n"
            "        case Phase.DONE:\n"
            "            return 'finished'\n"
            "        case _ as unreachable:\n"
            "            assert_never(unreachable)\n"
        ),
        # if/elif chain with a terminal `else: assert_never(subject)` guard.
        Valid(
            "from enum import Enum\n"
            "from typing import assert_never\n"
            "\n"
            "class Phase(Enum):\n"
            "    PENDING = 'pending'\n"
            "    RUNNING = 'running'\n"
            "    DONE = 'done'\n"
            "\n"
            "def handle(phase: Phase) -> str:\n"
            "    if phase == Phase.PENDING:\n"
            "        return 'waiting'\n"
            "    elif phase == Phase.RUNNING:\n"
            "        return 'working'\n"
            "    elif phase == Phase.DONE:\n"
            "        return 'finished'\n"
            "    else:\n"
            "        assert_never(phase)\n"
        ),
        # if/elif over a non-enum value is out of scope entirely.
        Valid(
            "def handle(status: str) -> str:\n"
            "    if status == 'pending':\n"
            "        return 'waiting'\n"
            "    elif status == 'running':\n"
            "        return 'working'\n"
            "    return 'unknown'\n"
        ),
    ]
    INVALID = [
        # The load-bearing shape: if/elif enum dispatch with no
        # assert_never-guarded else -- falls through unnoticed on a new member.
        Invalid(
            "from enum import Enum\n"
            "\n"
            "class Phase(Enum):\n"
            "    PENDING = 'pending'\n"
            "    RUNNING = 'running'\n"
            "    DONE = 'done'\n"
            "\n"
            "def handle(phase: Phase) -> str:\n"
            "    if phase == Phase.PENDING:\n"
            "        return 'waiting'\n"
            "    elif phase == Phase.RUNNING:\n"
            "        return 'working'\n"
            "    elif phase == Phase.DONE:\n"
            "        return 'finished'\n"
            "    return 'unreachable'\n"
        ),
        # A plain (non-assert_never) else does not restore exhaustiveness
        # checking -- still flagged.
        Invalid(
            "from enum import Enum\n"
            "\n"
            "class Phase(Enum):\n"
            "    PENDING = 'pending'\n"
            "    RUNNING = 'running'\n"
            "\n"
            "def handle(phase: Phase) -> str:\n"
            "    if phase == Phase.PENDING:\n"
            "        return 'waiting'\n"
            "    else:\n"
            "        return 'other'\n"
        ),
    ]
