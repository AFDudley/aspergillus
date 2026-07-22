#!/usr/bin/env python3
"""ASP-FSM-REDUNDANT: warn on enum dispatch branches with identical bodies.

Within one ``match`` statement (or if/elif chain) dispatching on a single
Enum-typed subject, two branch bodies whose location- and comment-stripped
(but not alpha-renamed) ASTs are identical are a likely sign of a redundant
state -- the exact shape of exophial's hand-found PRESERVE/FAIL defect,
where both branches were literally ``Fail(reason)``. Textual-identical-body
is a decidable PROXY for state redundancy, not a proof of behavioral
equivalence (undecidable, per Rice's theorem), so this WARNS rather than
rejects, and it deliberately never renames variables before comparing --
two branches that differ only by a local variable's name stay silent.

Usage: check_asp_fsm_redundant_branches.py <path/to/module.py> <function_name>

Checks only the named top-level function in the module (fixtures collect
multiple independent scenarios in one file) and prints one JSON object to
stdout: ``{"warning_count": <int>, "first_message": <str | null>}``.
"""

from __future__ import annotations

import ast
import json
import sys

ENUM_BASE_NAMES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"})
REDUNDANT_STATES_MESSAGE = "likely redundant states"


def _base_name(base: ast.expr) -> str | None:
    """Pure: the bare class name of a base-class expression, or None."""
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def _enum_class_names(tree: ast.Module) -> frozenset[str]:
    """Pure: names of classes in ``tree`` that subclass a known Enum base."""
    return frozenset(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(_base_name(base) in ENUM_BASE_NAMES for base in node.bases)
    )


def _is_enum_member_access(node: ast.expr, enum_names: frozenset[str]) -> bool:
    """Pure: True iff ``node`` is ``<EnumClass>.<MEMBER>`` for a known enum."""
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in enum_names
    )


def _enum_dispatch_subject(test: ast.expr, enum_names: frozenset[str]) -> str | None:
    """Pure: if ``test`` compares one side against an enum member, return the
    ``ast.dump`` of the other (subject) side; else None."""
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
        return None
    if not isinstance(test.ops[0], (ast.Eq, ast.Is)):
        return None
    left, right = test.left, test.comparators[0]
    if _is_enum_member_access(right, enum_names):
        return ast.dump(left)
    if _is_enum_member_access(left, enum_names):
        return ast.dump(right)
    return None


def _chain_elif_ids(node: ast.If) -> set[int]:
    """Pure: object ids of the If nodes in ``node``'s orelse chain (the elifs)."""
    ids: set[int] = set()
    current = node
    while len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
        current = current.orelse[0]
        ids.add(id(current))
    return ids


def _if_chain_enum_branches(
    node: ast.If, enum_names: frozenset[str]
) -> list[list[ast.stmt]] | None:
    """Pure: bodies of the if/elif branches that guard on the same enum
    subject, or None if fewer than two such branches exist."""
    branches: list[list[ast.stmt]] = []
    subject_dump: str | None = None
    current: ast.If | None = node
    while isinstance(current, ast.If):
        test_subject = _enum_dispatch_subject(current.test, enum_names)
        if test_subject is None or (subject_dump is not None and test_subject != subject_dump):
            break
        subject_dump = test_subject
        branches.append(current.body)
        current = (
            current.orelse[0]
            if len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If)
            else None
        )
    return branches if len(branches) >= 2 else None


def _match_case_enum_member(case: ast.match_case, enum_names: frozenset[str]) -> bool:
    """Pure: True iff ``case``'s pattern matches a known enum member value."""
    pattern = case.pattern
    return (
        isinstance(pattern, ast.MatchValue)
        and isinstance(pattern.value, ast.Attribute)
        and isinstance(pattern.value.value, ast.Name)
        and pattern.value.value.id in enum_names
    )


def _match_enum_branches(
    node: ast.Match, enum_names: frozenset[str]
) -> list[list[ast.stmt]] | None:
    """Pure: bodies of ``node``'s cases that match an enum member, or None if
    fewer than two such cases exist."""
    branches = [case.body for case in node.cases if _match_case_enum_member(case, enum_names)]
    return branches if len(branches) >= 2 else None


def _normalize_body(body: list[ast.stmt]) -> str:
    """Pure: canonical string for a branch body, blind to source locations
    and comments (neither survives ``ast.parse``) and to nothing else --
    variable names are kept verbatim, so a rename still differs."""
    return "\n".join(ast.dump(stmt, include_attributes=False) for stmt in body)


def _pairwise_redundant_warnings(branches: list[list[ast.stmt]]) -> list[str]:
    """Pure: one 'likely redundant states' warning per pair of branches
    whose normalized bodies are identical."""
    normalized = [_normalize_body(body) for body in branches]
    return [
        REDUNDANT_STATES_MESSAGE
        for i in range(len(normalized))
        for j in range(i + 1, len(normalized))
        if normalized[i] == normalized[j]
    ]


def find_redundant_warnings(func: ast.FunctionDef, enum_names: frozenset[str]) -> list[str]:
    """Pure: all redundant-branch warnings in ``func``'s enum dispatches."""
    handled_as_elif: set[int] = set()
    warnings: list[str] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Match):
            branches = _match_enum_branches(node, enum_names)
        elif isinstance(node, ast.If):
            if id(node) in handled_as_elif:
                continue
            handled_as_elif |= _chain_elif_ids(node)
            branches = _if_chain_enum_branches(node, enum_names)
        else:
            continue
        if branches is not None:
            warnings.extend(_pairwise_redundant_warnings(branches))
    return warnings


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    """Pure: the top-level function named ``name``, or raise ValueError."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise ValueError(f"no top-level function named {name!r}")


def main() -> int:
    """IO shell: read the fixture file, run the pure check, print the verdict."""
    fixture_path, function_name = sys.argv[1], sys.argv[2]
    with open(fixture_path, encoding="utf-8") as handle:
        source = handle.read()
    tree = ast.parse(source, filename=fixture_path)
    enum_names = _enum_class_names(tree)
    func = _find_function(tree, function_name)
    warnings = find_redundant_warnings(func, enum_names)
    print(
        json.dumps(
            {
                "warning_count": len(warnings),
                "first_message": warnings[0] if warnings else None,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
