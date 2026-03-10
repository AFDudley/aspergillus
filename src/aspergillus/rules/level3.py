"""NASA Level 3 rules: type safety + explicit error handling."""

from __future__ import annotations

import libcst as cst
from fixit import Invalid, LintRule, Valid


class RaiseInsteadOfResult(LintRule):
    """ASP301: Function raises AND returns — consider Result type.

    Functions that have both a normal return path and a raise path
    are using exceptions for control flow. Consider returning a
    Result/Either type instead, making the error explicit in the
    type signature.

    Exempt: __init__ (commonly raises ValueError/TypeError),
    test functions, and functions that only raise (no return).
    """

    MESSAGE = "ASP301: Function has both `raise` and `return` — consider Result type"

    VALID = [
        Valid(
            "def divide(a: float, b: float) -> float:\n"
            "    assert b != 0\n"
            "    assert isinstance(a, (int, float))\n"
            "    return a / b\n"
        ),
        Valid("def fail_always() -> None:\n" "    raise NotImplementedError\n"),
        Valid(
            "def __init__(self, x: int) -> None:\n"
            "    if x < 0:\n"
            "        raise ValueError\n"
            "    self.x = x\n"
        ),
    ]
    INVALID = [
        Invalid(
            "def parse(s: str) -> int:\n"
            "    assert isinstance(s, str)\n"
            "    assert len(s) > 0\n"
            "    if not s.isdigit():\n"
            "        raise ValueError('not a number')\n"
            "    return int(s)\n"
        ),
    ]

    EXEMPT_PREFIXES = ("test_", "__init__")

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        name = node.name.value
        if any(name.startswith(p) for p in self.EXEMPT_PREFIXES):
            return

        has_raise = _has_node_type(node.body, cst.Raise)
        has_return = _has_return_value(node.body)

        if has_raise and has_return:
            self.report(node, self.MESSAGE)


def _has_node_type(body: cst.BaseSuite, node_type: type[cst.CSTNode]) -> bool:
    """Check if body contains a node of given type (not in nested functions)."""
    if not isinstance(body, cst.IndentedBlock):
        return False
    return _search_for_type(body, node_type)


def _search_for_type(node: cst.CSTNode, node_type: type[cst.CSTNode]) -> bool:
    if isinstance(node, node_type):
        return True
    # Don't descend into nested functions
    if isinstance(node, cst.FunctionDef) and not isinstance(node, cst.BaseSuite):
        return False
    for child in node.children:
        if isinstance(child, cst.CSTNode):
            # Skip nested function defs
            if isinstance(child, cst.FunctionDef):
                continue
            if _search_for_type(child, node_type):
                return True
    return False


def _has_return_value(body: cst.BaseSuite) -> bool:
    """Check for `return <expr>` (not bare `return` or `return None`)."""
    if not isinstance(body, cst.IndentedBlock):
        return False
    return _search_for_return(body)


def _search_for_return(node: cst.CSTNode) -> bool:
    if isinstance(node, cst.Return):
        if node.value is not None:
            # Exclude `return None`
            if not (isinstance(node.value, cst.Name) and node.value.value == "None"):
                return True
        return False
    for child in node.children:
        if isinstance(child, cst.CSTNode):
            if isinstance(child, cst.FunctionDef):
                continue
            if _search_for_return(child):
                return True
    return False
