"""ASP411: FSM redundant branches — likely redundant states in an enum
dispatch.

Verification-integrity family; sibling to ASP408 anti-special-casing,
ASP409 shell-to-self, and ASP410 in-process-e2e. Ported from the
standalone ASP-FSM-REDUNDANT probe (pebble ``asp-5a8``, itself derived
from exophial's exo-011 rule 4) into the fixit rule pack so a real lint
gate — not an ad-hoc script no CI invokes — enforces it.

Within one ``match`` statement or one ``if``/``elif`` chain dispatching
on a single Enum-typed subject, two branch bodies whose location- and
comment-stripped (but NOT alpha-renamed) ASTs are identical are a
likely sign of a redundant state — the exact shape of exophial's
hand-found PRESERVE/FAIL defect, where both branches were literally
``Fail(reason)``. Textual-identical-body is a decidable PROXY for
state redundancy, not a proof of behavioral equivalence (undecidable,
per Rice's theorem), so this WARNS rather than rejects, and it
deliberately never renames variables before comparing — two branches
that differ only by a local variable's name stay silent (that
difference may be semantically load-bearing, e.g. distinguishing which
state produced the value).

**Ships without autofix** (Tier 2, detection-only, per
``docs/decisions/2026-05-19-mtm-past-warn-promotion-phase.md``): which
states should actually merge, or whether the duplication is
intentional (two states sharing a terminal action on purpose), is
human/agent judgment the rule cannot mechanically resolve.

LibCST, not ``ast``
-------------------
The original checker used stdlib ``ast`` (parsing the whole fixture file
once per scenario). Fixit rules walk a LibCST tree instead, so branch
bodies are re-rendered to source (``Module(body=[]).code_for_node``),
dedented, and re-parsed with ``ast`` for the comparison — reproducing
the checker's exact "location- and comment-stripped, non-alpha-renamed"
normalization while living inside fixit's LibCST visitor contract.
"""

from __future__ import annotations

import ast
import textwrap

import libcst as cst
from fixit import Invalid, LintRule, Valid

ENUM_BASE_NAMES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"})


def _base_name(arg: cst.Arg) -> str | None:
    """Pure: the bare class name of a base-class argument, or None."""
    value = arg.value
    if isinstance(value, cst.Name):
        return value.value
    if isinstance(value, cst.Attribute):
        return value.attr.value
    return None


class _EnumClassCollector(cst.CSTVisitor):
    """Collects the names of classes anywhere in the module that subclass a
    known Enum base."""

    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        if any(_base_name(base) in ENUM_BASE_NAMES for base in node.bases):
            self.names.add(node.name.value)


def _enum_class_names(module: cst.Module) -> frozenset[str]:
    """Pure: names of classes in ``module`` that subclass a known Enum base."""
    collector = _EnumClassCollector()
    module.visit(collector)
    return frozenset(collector.names)


def _is_enum_member_access(node: cst.BaseExpression, enum_names: frozenset[str]) -> bool:
    """Pure: True iff ``node`` is ``<EnumClass>.<MEMBER>`` for a known enum."""
    return (
        isinstance(node, cst.Attribute)
        and isinstance(node.value, cst.Name)
        and node.value.value in enum_names
    )


def _normalize_expr(node: cst.BaseExpression) -> str:
    """Pure: canonical string for an expression, blind to source formatting."""
    code = cst.Module(body=[]).code_for_node(node)
    tree = ast.parse(textwrap.dedent(code), mode="eval")
    return ast.dump(tree.body, include_attributes=False)


def _normalize_block(body: cst.BaseSuite) -> str:
    """Pure: canonical string for a branch body, blind to source locations
    and comments -- variable names are kept verbatim, so a rename still
    differs."""
    code = cst.Module(body=[]).code_for_node(body)
    tree = ast.parse(textwrap.dedent(code))
    return "\n".join(ast.dump(stmt, include_attributes=False) for stmt in tree.body)


def _enum_dispatch_subject(test: cst.BaseExpression, enum_names: frozenset[str]) -> str | None:
    """Pure: if ``test`` compares one side against an enum member, return a
    normalized dump of the other (subject) side; else None."""
    if not isinstance(test, cst.Comparison) or len(test.comparisons) != 1:
        return None
    target = test.comparisons[0]
    if not isinstance(target.operator, (cst.Equal, cst.Is)):
        return None
    left, right = test.left, target.comparator
    if _is_enum_member_access(right, enum_names):
        return _normalize_expr(left)
    if _is_enum_member_access(left, enum_names):
        return _normalize_expr(right)
    return None


def _chain_elif_ids(node: cst.If) -> set[int]:
    """Pure: object ids of the If nodes in ``node``'s elif chain."""
    ids: set[int] = set()
    current = node
    while isinstance(current.orelse, cst.If):
        current = current.orelse
        ids.add(id(current))
    return ids


def _if_chain_enum_branches(
    node: cst.If, enum_names: frozenset[str]
) -> list[cst.BaseSuite] | None:
    """Pure: bodies of the if/elif branches that guard on the same enum
    subject, or None if fewer than two such branches exist."""
    branches: list[cst.BaseSuite] = []
    subject_dump: str | None = None
    current: cst.If | None = node
    while isinstance(current, cst.If):
        test_subject = _enum_dispatch_subject(current.test, enum_names)
        if test_subject is None or (subject_dump is not None and test_subject != subject_dump):
            break
        subject_dump = test_subject
        branches.append(current.body)
        current = current.orelse if isinstance(current.orelse, cst.If) else None
    return branches if len(branches) >= 2 else None


def _match_case_enum_member(case: cst.MatchCase, enum_names: frozenset[str]) -> bool:
    """Pure: True iff ``case``'s pattern matches a known enum member value."""
    pattern = case.pattern
    return (
        isinstance(pattern, cst.MatchValue)
        and isinstance(pattern.value, cst.Attribute)
        and isinstance(pattern.value.value, cst.Name)
        and pattern.value.value.value in enum_names
    )


def _match_enum_branches(
    node: cst.Match, enum_names: frozenset[str]
) -> list[cst.BaseSuite] | None:
    """Pure: bodies of ``node``'s cases that match an enum member, or None if
    fewer than two such cases exist."""
    branches = [case.body for case in node.cases if _match_case_enum_member(case, enum_names)]
    return branches if len(branches) >= 2 else None


def _has_redundant_branches(branches: list[cst.BaseSuite]) -> bool:
    """Pure: True iff any two of ``branches`` normalize to the same body."""
    normalized = [_normalize_block(body) for body in branches]
    return any(
        normalized[i] == normalized[j]
        for i in range(len(normalized))
        for j in range(i + 1, len(normalized))
    )


class FsmRedundantBranches(LintRule):
    """ASP411: likely redundant states — two branches of an enum dispatch
    (a ``match`` statement or an ``if``/``elif`` chain) have identical
    bodies once source locations and comments are stripped, without
    renaming variables. Detection-only (no autofix); merging the states
    is human/agent judgment.
    """

    MESSAGE = (
        "ASP411: likely redundant states — two branches of this enum "
        "dispatch have identical bodies (ignoring source location and "
        "comments). This is the PRESERVE/FAIL shape: two states doing "
        "the exact same thing may mean one of them is spurious. If the "
        "duplication is intentional, this warning is a false positive; "
        "otherwise, merge the redundant states."
    )

    #: Reset per module by ``visit_Module``: names of Enum subclasses in the
    #: current file, and ids of If nodes already consumed as an elif link
    #: (so an elif isn't re-checked as the head of its own chain).
    _enum_names: frozenset[str]
    _handled_as_elif: set[int]

    def visit_Module(self, node: cst.Module) -> None:
        self._enum_names = _enum_class_names(node)
        self._handled_as_elif = set()

    def visit_If(self, node: cst.If) -> None:
        if id(node) in self._handled_as_elif:
            return
        self._handled_as_elif |= _chain_elif_ids(node)
        branches = _if_chain_enum_branches(node, self._enum_names)
        if branches is not None and _has_redundant_branches(branches):
            self.report(node, self.MESSAGE)

    def visit_Match(self, node: cst.Match) -> None:
        branches = _match_enum_branches(node, self._enum_names)
        if branches is not None and _has_redundant_branches(branches):
            self.report(node, self.MESSAGE)

    # Fixtures below are ported verbatim from the standalone checker's merged
    # scenarios (tests/fixtures/asp_fsm_redundant.py, pebble asp-5a8), sharing
    # the same Phase/Fail preamble that file used.
    _PREAMBLE = (
        "from enum import Enum\n"
        "\n"
        "\n"
        "class Phase(Enum):\n"
        '    PENDING = "pending"\n'
        '    RUNNING = "running"\n'
        '    DONE = "done"\n'
        "\n"
        "\n"
        "class Fail:\n"
        "    def __init__(self, reason: str) -> None:\n"
        "        self.reason = reason\n"
        "\n"
        "\n"
    )

    VALID = [
        # renamed_variable_not_flagged: structurally identical branches, but
        # a renamed local variable -- deliberately NOT flagged (no
        # alpha-rename; the rename may be semantically load-bearing).
        Valid(
            _PREAMBLE + "if phase == Phase.PENDING:\n"
            '    reason = "bad state"\n'
            "    return Fail(reason)\n"
            "elif phase == Phase.RUNNING:\n"
            '    cause = "bad state"\n'
            "    return Fail(cause)\n"
            "elif phase == Phase.DONE:\n"
            '    return "finished"\n'
        ),
        # genuinely_different_bodies: every branch does something different.
        Valid(
            _PREAMBLE + "if phase == Phase.PENDING:\n"
            '    return "waiting"\n'
            "elif phase == Phase.RUNNING:\n"
            '    return "working"\n'
            "elif phase == Phase.DONE:\n"
            '    return "finished"\n'
        ),
        # non_enum_dispatch_identical_bodies: identical bodies, but the
        # dispatch subject isn't Enum-typed -- out of scope.
        Valid(
            _PREAMBLE + 'if status == "pending":\n'
            '    reason = "bad state"\n'
            "    return Fail(reason)\n"
            'elif status == "running":\n'
            '    reason = "bad state"\n'
            "    return Fail(reason)\n"
            "else:\n"
            '    return "finished"\n'
        ),
    ]
    INVALID = [
        # redundant_identical_bodies: match dispatch where RUNNING and DONE
        # are both literally ``Fail(reason)`` -- the real PRESERVE/FAIL shape.
        Invalid(
            _PREAMBLE + "match phase:\n"
            "    case Phase.PENDING:\n"
            '        return "waiting"\n'
            "    case Phase.RUNNING:\n"
            '        reason = "not ready"\n'
            "        return Fail(reason)\n"
            "    case Phase.DONE:\n"
            '        reason = "not ready"\n'
            "        return Fail(reason)\n"
        ),
        # redundant_comment_whitespace_diff: if/elif dispatch where PENDING
        # and RUNNING do the same thing, but one branch has an extra comment
        # and different indentation -- still flagged.
        Invalid(
            _PREAMBLE + "if phase == Phase.PENDING:\n"
            '    reason = "bad state"\n'
            "    return Fail(reason)\n"
            "elif phase == Phase.RUNNING:\n"
            "        # extra comment explaining this branch\n"
            '        reason  =    "bad state"\n'
            "        return Fail(reason)\n"
            "elif phase == Phase.DONE:\n"
            '    return "finished"\n'
        ),
    ]
