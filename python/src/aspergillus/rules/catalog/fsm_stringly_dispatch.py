"""ASP411: stringly-typed dispatch shadowing a same-module Enum.

FSM-verification-integrity family; sibling to ASP408 anti-special-casing,
ASP409 shell-to-self, and ASP410 in-process-e2e. Where those three guard the
*honesty* of a verification gate, ASP411 guards the *exhaustiveness* of a
dispatch: an `if`/`elif` chain or `match` statement that branches on `==`
comparisons against string literals which happen to shadow a same-module
`Enum`'s values bypasses both mypy's `match` exhaustiveness checking and this
pack's own ASP-FSM-EXHAUSTIVE invariant (`scripts/check_asp_fsm_enum_dispatch.py`)
— the Enum exists, but the dispatch never goes through it, so adding a new
member silently leaves the string-keyed branches un-updated.

Ported from the standalone probe `scripts/check_stringly_dispatch.py`
(pebble asp-5be, exophial exo-011 rule 5), which ran only as an ad-hoc
stdin/stdout script with no linter gate invoking it. This rule carries the
exact same trigger and escape hatch into the enforced `aspergillus.rules`
fixit pack: pebble asp-fd1.4.

**Ships without autofix** (Tier 2, detection-only, per
`docs/decisions/2026-05-19-mtm-past-warn-promotion-phase.md`). The fix —
rewriting the string comparisons into a dispatch on the Enum member itself —
changes the dispatched-on value's type at every call site, which is a
judgment call the rule cannot make mechanically.

Escape hatch
------------
A function carrying a `# asp-fsm: boundary-parse` comment anywhere in its
body is exempt, even if it otherwise matches the pattern — genuine
serialization-boundary parsers (wire format -> Enum) legitimately compare
against the Enum's string values once, at the seam, before anything downstream
should ever see a bare string again.
"""

from __future__ import annotations

from collections.abc import Iterator

import libcst as cst
from fixit import Invalid, LintRule, Valid
from libcst.metadata import PositionProvider

#: Enum base names recognized when scanning same-module class defs (bare or
#: dotted, e.g. ``enum.Enum``).
ENUM_BASE_NAMES: frozenset[str] = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"})

#: Comment marker that silences this rule for the function it appears in
#: (serialization-boundary parsers legitimately dispatch on wire strings).
BOUNDARY_MARKER = "asp-fsm: boundary-parse"

_MESSAGE = (
    "ASP411: stringly-typed dispatch — this if/elif or match branches on "
    "string literals that shadow a same-module Enum's values, bypassing "
    "exhaustiveness checking. Dispatch on the Enum member instead (or add "
    "'# asp-fsm: boundary-parse' if this is a genuine serialization-boundary "
    "parser)."
)


class FsmStringlyDispatch(LintRule):
    """ASP411: if/elif or match dispatches on string literals that shadow a
    same-module Enum's values — dispatch on the Enum instead.

    Detection-only (no autofix): the fix changes the dispatched-on value's
    type at every call site, which is a judgment call.
    """

    MESSAGE = _MESSAGE
    METADATA_DEPENDENCIES = (PositionProvider,)

    #: Same-module Enum member string values seen in the current file.
    _enum_values: frozenset[str]
    #: The current file's source, split into lines (1-indexed by callers).
    _source_lines: list[str]
    #: Boundary-marker status of each enclosing FunctionDef, innermost last.
    _boundary_stack: list[bool]

    VALID = [
        # No same-module Enum at all -> nothing to shadow, stays silent.
        Valid('def route(status):\n    if status == "active":\n        return 1\n    return 0\n'),
        # Enum present, but the dispatch never compares against a string
        # literal that shadows one of its values.
        Valid(
            "from enum import Enum\n\n\n"
            'class Status(Enum):\n    ACTIVE = "active"\n    IDLE = "idle"\n\n\n'
            "def route(status):\n"
            "    if status == 1:\n"
            "        return Status.ACTIVE\n"
            "    return Status.IDLE\n"
        ),
        # Dispatch on the Enum member itself, not a stringly-typed shadow.
        Valid(
            "from enum import Enum\n\n\n"
            'class Status(Enum):\n    ACTIVE = "active"\n    IDLE = "idle"\n\n\n'
            "def route(status: Status):\n"
            "    match status:\n"
            "        case Status.ACTIVE:\n"
            "            return 1\n"
            "        case Status.IDLE:\n"
            "            return 0\n"
        ),
        # The escape hatch: a genuine serialization-boundary parser.
        Valid(
            "from enum import Enum\n\n\n"
            'class Status(Enum):\n    ACTIVE = "active"\n    IDLE = "idle"\n\n\n'
            "def parse_status(raw):\n"
            "    # asp-fsm: boundary-parse\n"
            '    if raw == "active":\n'
            "        return Status.ACTIVE\n"
            '    if raw == "idle":\n'
            "        return Status.IDLE\n"
            "    raise ValueError(raw)\n"
        ),
    ]
    INVALID = [
        # if/elif shadowing a same-module Enum's values.
        Invalid(
            "from enum import Enum\n\n\n"
            'class Status(Enum):\n    ACTIVE = "active"\n    IDLE = "idle"\n\n\n'
            "def route(status):\n"
            '    if status == "active":\n'
            "        return 1\n"
            '    elif status == "idle":\n'
            "        return 0\n"
            "    return -1\n"
        ),
        # `or`-ed string-literal comparisons shadowing a same-module Enum.
        Invalid(
            "from enum import Enum\n\n\n"
            'class Status(Enum):\n    ACTIVE = "active"\n    IDLE = "idle"\n\n\n'
            "def route(status):\n"
            '    if status == "active" or status == "idle":\n'
            "        return 1\n"
            "    return 0\n"
        ),
        # `match` dispatching on string literals shadowing a same-module Enum.
        Invalid(
            "from enum import Enum\n\n\n"
            'class Status(Enum):\n    ACTIVE = "active"\n    IDLE = "idle"\n\n\n'
            "def route(status):\n"
            "    match status:\n"
            '        case "active":\n'
            "            return 1\n"
            '        case "idle":\n'
            "            return 0\n"
        ),
    ]

    def visit_Module(self, node: cst.Module) -> None:
        # Reset per-file state — a rule instance may be reused across files
        # by the fixit engine.
        self._enum_values = _collect_enum_string_values(node)
        self._source_lines = node.code.splitlines()
        self._boundary_stack = []

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        pos = self.get_metadata(PositionProvider, node)
        lines = self._source_lines[pos.start.line - 1 : pos.end.line]
        self._boundary_stack.append(any(BOUNDARY_MARKER in line for line in lines))

    def leave_FunctionDef(self, node: cst.FunctionDef) -> None:
        self._boundary_stack.pop()

    def _dispatch_active(self) -> bool:
        """True only inside a non-boundary-marked function body — the
        original probe never scanned module-level code outside a function."""
        return (
            bool(self._enum_values) and bool(self._boundary_stack) and not self._boundary_stack[-1]
        )

    def visit_If(self, node: cst.If) -> None:
        if not self._dispatch_active():
            return
        literals = _eq_string_literals(node.test)
        if literals & self._enum_values:
            self.report(node.test, self.MESSAGE)

    def visit_Match(self, node: cst.Match) -> None:
        if not self._dispatch_active():
            return
        for case in node.cases:
            literals = _match_pattern_literals(case.pattern)
            if literals & self._enum_values:
                self.report(case, self.MESSAGE)


# --- literal / enum extraction ----------------------------------------------


def _string_value(node: cst.BaseExpression) -> str | None:
    """The value of a plain or concatenated string literal, else None."""
    if isinstance(node, (cst.SimpleString, cst.ConcatenatedString)):
        value = node.evaluated_value
        return value if isinstance(value, str) else None
    return None


def _eq_string_literals(test: cst.BaseExpression) -> frozenset[str]:
    """String literals compared via a single `==` (directly, or `or`-ed
    together) in a boolean test."""
    literals: set[str] = set()
    if isinstance(test, cst.Comparison) and len(test.comparisons) == 1:
        target = test.comparisons[0]
        if isinstance(target.operator, cst.Equal):
            for operand in (test.left, target.comparator):
                value = _string_value(operand)
                if value is not None:
                    literals.add(value)
    elif isinstance(test, cst.BooleanOperation) and isinstance(test.operator, cst.Or):
        literals |= _eq_string_literals(test.left)
        literals |= _eq_string_literals(test.right)
    return frozenset(literals)


def _match_pattern_literals(pattern: cst.MatchPattern) -> frozenset[str]:
    """String literals matched directly, or `|`-ed together, by a `case`."""
    literals: set[str] = set()
    if isinstance(pattern, cst.MatchValue):
        value = _string_value(pattern.value)
        if value is not None:
            literals.add(value)
    elif isinstance(pattern, cst.MatchOr):
        for element in pattern.patterns:
            literals |= _match_pattern_literals(element.pattern)
    return frozenset(literals)


def _base_name(base: cst.Arg) -> str | None:
    value = base.value
    if isinstance(value, cst.Name):
        return value.value
    if isinstance(value, cst.Attribute):
        return value.attr.value
    return None


def _is_enum_class(node: cst.ClassDef) -> bool:
    return any(_base_name(base) in ENUM_BASE_NAMES for base in node.bases)


def _iter_class_defs(node: cst.CSTNode) -> Iterator[cst.ClassDef]:
    if isinstance(node, cst.ClassDef):
        yield node
    for child in node.children:
        yield from _iter_class_defs(child)


def _collect_enum_string_values(module: cst.Module) -> frozenset[str]:
    """String values assigned by Enum members defined anywhere in the module."""
    values: set[str] = set()
    for class_def in _iter_class_defs(module):
        if not _is_enum_class(class_def):
            continue
        for stmt in class_def.body.body:
            if not isinstance(stmt, cst.SimpleStatementLine):
                continue
            for small in stmt.body:
                value_expr: cst.BaseExpression | None = None
                if isinstance(small, (cst.Assign, cst.AnnAssign)):
                    value_expr = small.value
                if value_expr is not None:
                    value = _string_value(value_expr)
                    if value is not None:
                        values.add(value)
    return frozenset(values)
