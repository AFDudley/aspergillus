#!/usr/bin/env python3
"""ASP-FSM-EXHAUSTIVE: enum if/elif dispatch must be checkable for exhaustiveness.

mypy's ``exhaustive-match`` error code only fires inside ``match`` /
``assert_never`` forms. An if/elif chain that dispatches on a single
Enum-typed subject (comparing it with ``is``/``==`` against Enum members)
silently opts out of that check — a new enum member added later falls
through unnoticed. This script rejects that shape unless it is either
written as a ``match`` statement, or its if/elif chain terminates in
``else: assert_never(subject)``.

Usage: check_asp_fsm_enum_dispatch.py <path/to/module.py> <function_name>

Checks only the named top-level function in the module (fixtures collect
multiple independent scenarios in one file) and prints one JSON object
to stdout: ``{"violation_count": <int>}``.
"""

from __future__ import annotations

import ast
import json
import sys

ENUM_BASE_NAMES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"})


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


def _is_assert_never_call(stmt: ast.stmt, subject_dump: str) -> bool:
    """Pure: True iff ``stmt`` is exactly ``assert_never(<subject>)``."""
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    call = stmt.value
    func = call.func
    name = None
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    if name != "assert_never" or len(call.args) != 1:
        return False
    return ast.dump(call.args[0]) == subject_dump


def _final_else(node: ast.If) -> list[ast.stmt]:
    """Pure: walk an if/elif chain (elif == single-If orelse) to its final else body."""
    current = node
    while len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
        current = current.orelse[0]
    return current.orelse


def _chain_elif_ids(node: ast.If) -> set[int]:
    """Pure: object ids of the If nodes in ``node``'s orelse chain (the elifs)."""
    ids: set[int] = set()
    current = node
    while len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
        current = current.orelse[0]
        ids.add(id(current))
    return ids


def _is_violation(node: ast.If, enum_names: frozenset[str]) -> bool:
    """Pure: True iff ``node`` heads an unguarded enum if/elif dispatch."""
    subject_dump = _enum_dispatch_subject(node.test, enum_names)
    if subject_dump is None:
        return False  # not an enum-typed dispatch at all -- out of scope
    final_else = _final_else(node)
    if len(final_else) == 1 and _is_assert_never_call(final_else[0], subject_dump):
        return False
    return True


def count_violations(func: ast.FunctionDef, enum_names: frozenset[str]) -> int:
    """Pure: number of unguarded enum if/elif dispatches in ``func``'s body."""
    handled_as_elif: set[int] = set()
    violations = 0
    for node in ast.walk(func):
        if not isinstance(node, ast.If) or id(node) in handled_as_elif:
            continue
        handled_as_elif |= _chain_elif_ids(node)
        if _is_violation(node, enum_names):
            violations += 1
    return violations


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
    violation_count = count_violations(func, enum_names)
    print(json.dumps({"violation_count": violation_count}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
