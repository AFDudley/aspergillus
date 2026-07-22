#!/usr/bin/env python3
"""Warn when if/elif or match dispatch on string literals shadows a same-module Enum.

Reads Python source from stdin, prints a single JSON object to stdout:
{"warning_count": int, "first_message": str | None}
"""

from __future__ import annotations

import ast
import json
import sys

WARNING_MESSAGE = (
    "stringly-typed dispatch; dispatch on the Enum so exhaustiveness checking applies"
)
ENUM_BASE_NAMES = {"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"}
BOUNDARY_MARKER = "asp-fsm: boundary-parse"

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def _base_name(base: ast.expr) -> str | None:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def _is_enum_class(node: ast.ClassDef) -> bool:
    return any(_base_name(base) in ENUM_BASE_NAMES for base in node.bases)


def _add_str_constant(value: ast.expr | None, values: set[str]) -> None:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        values.add(value.value)


def collect_enum_string_values(tree: ast.Module) -> set[str]:
    """Collect string values assigned by Enum members defined anywhere in the module."""
    values: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or not _is_enum_class(node):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                _add_str_constant(stmt.value, values)
            elif isinstance(stmt, ast.AnnAssign):
                _add_str_constant(stmt.value, values)
    return values


def _is_boundary_marked(node: FunctionNode, source_lines: list[str]) -> bool:
    end = node.end_lineno or node.lineno
    return any(BOUNDARY_MARKER in source_lines[lineno - 1] for lineno in range(node.lineno, end + 1))


def _string_eq_literals(test: ast.expr) -> set[str]:
    """String literals compared via `==` (directly, or `or`-ed together) in a boolean test."""
    literals: set[str] = set()
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq):
        for operand in (test.left, test.comparators[0]):
            _add_str_constant(operand, literals)
    elif isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
        for value in test.values:
            literals |= _string_eq_literals(value)
    return literals


def _match_pattern_literals(pattern: ast.pattern) -> set[str]:
    literals: set[str] = set()
    if isinstance(pattern, ast.MatchValue):
        _add_str_constant(pattern.value, literals)
    elif isinstance(pattern, ast.MatchOr):
        for sub in pattern.patterns:
            literals |= _match_pattern_literals(sub)
    return literals


def _nested_blocks(stmt: ast.stmt) -> list[list[ast.stmt]]:
    blocks: list[list[ast.stmt]] = []
    for field in ("body", "orelse", "finalbody"):
        block = getattr(stmt, field, None)
        if isinstance(block, list):
            blocks.append(block)
    for handler in getattr(stmt, "handlers", []):
        blocks.append(handler.body)
    return blocks


def _process_if_chain(node: ast.If, sites: list[set[str]]) -> None:
    """Collect one dispatch site for a whole if/elif/.../else chain, then recurse into branches."""
    literals: set[str] = set()
    branch_bodies: list[list[ast.stmt]] = []
    current = node
    while True:
        literals |= _string_eq_literals(current.test)
        branch_bodies.append(current.body)
        if len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
            current = current.orelse[0]
            continue
        if current.orelse:
            branch_bodies.append(current.orelse)
        break
    if literals:
        sites.append(literals)
    for body in branch_bodies:
        _scan_block(body, sites)


def _scan_block(stmts: list[ast.stmt], sites: list[set[str]]) -> None:
    for stmt in stmts:
        if isinstance(stmt, ast.If):
            _process_if_chain(stmt, sites)
        elif isinstance(stmt, ast.Match):
            for case in stmt.cases:
                literals = _match_pattern_literals(case.pattern)
                if literals:
                    sites.append(literals)
                _scan_block(case.body, sites)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        else:
            for block in _nested_blocks(stmt):
                _scan_block(block, sites)


def find_warnings(source: str) -> list[str]:
    tree = ast.parse(source)
    enum_values = collect_enum_string_values(tree)
    if not enum_values:
        return []

    source_lines = source.splitlines()
    messages: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _is_boundary_marked(node, source_lines):
            continue
        sites: list[set[str]] = []
        _scan_block(node.body, sites)
        for literals in sites:
            if literals & enum_values:
                messages.append(WARNING_MESSAGE)
    return messages


def main() -> None:
    source = sys.stdin.read()
    messages = find_warnings(source)
    result = {
        "warning_count": len(messages),
        "first_message": messages[0] if messages else None,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
