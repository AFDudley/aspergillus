#!/usr/bin/env python3
"""ASP-FSM-EDGE-DURATION: an FSM transition (edge) body must not embed unbounded work.

Classical FSM contract: time is spent in STATES, transitions are instantaneous.
An edge whose body runs an LLM/subprocess call, drives another state machine's
run/drive entrypoint, or spins an unbounded retry loop is a real, occupied
state the machine failed to declare. The correct shape is for an edge to write
a durable marker and return; the outer interpreter re-enters later via a
declared state.

A function is recognized as an edge body if it either:
  (a) dispatches on an Enum-typed subject via an if/elif chain (or `match`)
      that compares against a member of a class subclassing Enum, with at
      least one branch performing a call (the transition's terminal action);
  (b) carries an explicit `# asp-fsm: edge` comment directly above the `def`.

This is a heuristic, scoped checker: it does not attempt semantic analysis of
whether some other call is unbounded, and it does not trace calls through an
intermediate helper function -- indirection (a helper wrapping the call)
defeats detection by design; only direct calls inside the identified edge
body are flagged.

Usage: read a Python module from stdin, print one JSON object to stdout:
``{"flagged": <bool>, "violations": [{"function": str, "reason": str}, ...]}``
"""

from __future__ import annotations

import ast
import json
import sys

ENUM_BASE_NAMES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"})
EDGE_MARKER_COMMENT = "# asp-fsm: edge"
UNBOUNDED_ATTR_NAMES = frozenset({"complete", "run", "drive"})
SUBPROCESS_ATTR_NAMES = frozenset({"run", "call", "Popen", "check_output", "check_call"})


def _base_name(base: ast.expr) -> str | None:
    """Pure: the bare class name of a base-class expression, or None."""
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def _enum_class_names(tree: ast.Module) -> frozenset[str]:
    """Pure: names of classes in `tree` that subclass a known Enum base."""
    return frozenset(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(_base_name(base) in ENUM_BASE_NAMES for base in node.bases)
    )


def _is_enum_member_access(node: ast.expr, enum_names: frozenset[str]) -> bool:
    """Pure: True iff `node` is `<EnumClass>.<MEMBER>` for a known enum."""
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in enum_names
    )


def _is_enum_dispatch_test(test: ast.expr, enum_names: frozenset[str]) -> bool:
    """Pure: True iff `test` compares something against a known enum member."""
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
        return False
    if not isinstance(test.ops[0], (ast.Eq, ast.Is)):
        return False
    left, right = test.left, test.comparators[0]
    return _is_enum_member_access(right, enum_names) or _is_enum_member_access(left, enum_names)


def _match_case_is_enum(pattern: ast.pattern, enum_names: frozenset[str]) -> bool:
    """Pure: True iff a `match` case pattern matches a known enum member."""
    return isinstance(pattern, ast.MatchValue) and _is_enum_member_access(pattern.value, enum_names)


def _own_scope_nodes(root: ast.AST) -> list[ast.AST]:
    """Pure: `root` plus all descendants, not descending into nested
    function/class/lambda bodies -- composition through a helper is
    invisible to this scan by design (indirection defeats detection)."""
    result: list[ast.AST] = [root]
    stack = list(ast.iter_child_nodes(root))
    while stack:
        node = stack.pop()
        result.append(node)
        if node is not root and isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            continue
        stack.extend(ast.iter_child_nodes(node))
    return result


def _has_call(stmts: list[ast.stmt]) -> bool:
    """Pure: True iff any statement's own scope contains a Call."""
    return any(isinstance(node, ast.Call) for stmt in stmts for node in _own_scope_nodes(stmt))


def _has_enum_dispatch_action(func: ast.FunctionDef, enum_names: frozenset[str]) -> bool:
    """Pure: True iff `func` dispatches on an enum member (if/elif or match)
    with at least one branch performing a call."""
    for node in _own_scope_nodes(func):
        if isinstance(node, ast.If) and _is_enum_dispatch_test(node.test, enum_names):
            if _has_call(node.body) or _has_call(node.orelse):
                return True
        if isinstance(node, ast.Match):
            for case in node.cases:
                if _match_case_is_enum(case.pattern, enum_names) and _has_call(case.body):
                    return True
    return False


def _has_marker_comment(func: ast.FunctionDef, lines: list[str]) -> bool:
    """Pure: True iff `# asp-fsm: edge` appears directly above `def`."""
    idx = func.lineno - 2
    while idx >= 0:
        stripped = lines[idx].strip()
        if not stripped:
            idx -= 1
            continue
        return stripped == EDGE_MARKER_COMMENT
    return False


def _is_edge_function(
    func: ast.FunctionDef, enum_names: frozenset[str], lines: list[str]
) -> bool:
    """Pure: True iff `func` is recognized as an FSM transition body."""
    return _has_marker_comment(func, lines) or _has_enum_dispatch_action(func, enum_names)


def _unbounded_call_reason(call: ast.Call) -> str | None:
    """Pure: reason string if `call` is a direct LLM/subprocess/FSM-drive
    invocation, else None."""
    func = call.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr in UNBOUNDED_ATTR_NAMES:
        return f"direct call to .{func.attr}(...) inside edge body"
    if (
        isinstance(func.value, ast.Name)
        and func.value.id == "subprocess"
        and func.attr in SUBPROCESS_ATTR_NAMES
    ):
        return f"direct subprocess.{func.attr}(...) call inside edge body"
    return None


def _is_unbounded_retry_loop(node: ast.While) -> bool:
    """Pure: True iff `node` is a `while True:` loop."""
    return isinstance(node.test, ast.Constant) and node.test.value is True


def _scan_edge_violations(func: ast.FunctionDef) -> list[str]:
    """Pure: unbounded-work violations found directly inside `func`'s own scope."""
    violations: list[str] = []
    for node in _own_scope_nodes(func):
        if isinstance(node, ast.Call):
            reason = _unbounded_call_reason(node)
            if reason is not None:
                violations.append(reason)
        elif isinstance(node, ast.While) and _is_unbounded_retry_loop(node):
            violations.append("unbounded 'while True' retry/convergence loop inside edge body")
    return violations


def analyze(source: str) -> dict[str, object]:
    """Pure: analyze `source`, returning the flagged verdict and violations."""
    tree = ast.parse(source)
    lines = source.splitlines()
    enum_names = _enum_class_names(tree)
    violations = []
    for func in tree.body:
        if not isinstance(func, ast.FunctionDef):
            continue
        if not _is_edge_function(func, enum_names, lines):
            continue
        for reason in _scan_edge_violations(func):
            violations.append({"function": func.name, "reason": reason})
    return {"flagged": bool(violations), "violations": violations}


def main() -> int:
    """IO shell: read source from stdin, run the pure analysis, print the verdict."""
    source = sys.stdin.read()
    print(json.dumps(analyze(source)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
