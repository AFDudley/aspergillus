"""NASA Level 2 rules: pure functions + immutability."""

from __future__ import annotations

import libcst as cst
from fixit import Invalid, LintRule, Valid


class FunctionTooLong(LintRule):
    """ASP201: Functions must fit on one page (<=60 lines).

    NASA Power of 10 Rule #4: Functions should fit on a single
    printed page. This improves readability and testability.
    """

    MESSAGE = "ASP201: Function has {actual} lines (max {max_lines})"
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)
    MAX_LINES = 60

    VALID = [
        Valid(
            "def short():\n" + "".join(f"    x{i} = {i}\n" for i in range(58)) + "    return x0\n"
        ),
        Valid("def one_liner(): pass"),
        Valid("class Foo:\n" "    def method(self):\n" "        pass\n"),
    ]
    INVALID = [
        Invalid(
            "def too_long():\n"
            + "".join(f"    x{i} = {i}\n" for i in range(61))
            + "    return x0\n"
        ),
    ]

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        pos = self.get_metadata(cst.metadata.PositionProvider, node)
        line_count = pos.end.line - pos.start.line + 1
        if line_count > self.MAX_LINES:
            self.report(
                node,
                self.MESSAGE.format(actual=line_count, max_lines=self.MAX_LINES),
            )


class LowAssertionDensity(LintRule):
    """ASP202: Functions should have >=2 assertions.

    NASA Power of 10 Rule #5: High assertion density. Minimum of
    2 assertions per function to verify assumptions. Assertions are
    executable documentation of invariants.

    Exemptions: functions <=5 lines (trivial), test functions,
    __init__, __repr__, __str__.
    """

    MESSAGE = "ASP202: Function has {actual} assertions (min {min_asserts})"
    MIN_ASSERTS = 2
    EXEMPT_PREFIXES = ("test_", "__init__", "__repr__", "__str__", "__eq__", "__hash__")
    MIN_LINES_FOR_RULE = 5
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    VALID = [
        Valid(
            "def transfer(a: float, b: float) -> float:\n"
            "    assert a >= 0\n"
            "    assert b > 0\n"
            "    return a - b\n"
        ),
        Valid("def tiny(): return 1"),  # too short, exempt
        Valid(
            "def test_something():\n" "    result = compute()\n" "    assert result == 42\n"
        ),  # test function, exempt
        Valid("def __init__(self, x: int):\n" "    self.x = x\n"),  # dunder, exempt
    ]
    INVALID = [
        Invalid(
            "def process(data: list) -> int:\n"
            "    total = 0\n"
            "    for item in data:\n"
            "        total += item.value\n"
            "    filtered = [x for x in data if x.value > 0]\n"
            "    result = sum(x.value for x in filtered)\n"
            "    return result\n"
        ),
    ]

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        name = node.name.value
        if any(name.startswith(p) for p in self.EXEMPT_PREFIXES):
            return

        pos = self.get_metadata(cst.metadata.PositionProvider, node)
        line_count = pos.end.line - pos.start.line + 1
        if line_count <= self.MIN_LINES_FOR_RULE:
            return

        assert_count = self._count_asserts(node.body)
        if assert_count < self.MIN_ASSERTS:
            self.report(
                node,
                self.MESSAGE.format(actual=assert_count, min_asserts=self.MIN_ASSERTS),
            )

    def _count_asserts(self, body: cst.BaseSuite) -> int:
        """Count assert statements in a function body (non-recursive)."""
        count = 0
        if isinstance(body, cst.IndentedBlock):
            for stmt in body.body:
                if isinstance(stmt, cst.SimpleStatementLine):
                    for item in stmt.body:
                        if isinstance(item, cst.Assert):
                            count += 1
        return count


class GlobalMutableState(LintRule):
    """ASP203: No global mutable state.

    NASA Power of 10 Rule #3 (adapted): No mutable state at module scope.
    Module-level assignments to mutable types (list, dict, set literals)
    create shared mutable state that is hard to reason about and test.

    Allowed: frozenset, tuple, str, int, float, bool, None, re.compile,
    type aliases, constants (ALL_CAPS with immutable values).
    """

    MESSAGE = "ASP203: Global mutable state: {name} = {type}"

    VALID = [
        Valid("TIMEOUT: int = 30"),
        Valid('NAME: str = "hello"'),
        Valid("ITEMS: tuple[int, ...] = (1, 2, 3)"),
        Valid('ITEMS: frozenset[str] = frozenset({"a", "b"})'),
        Valid('PATTERN = re.compile(r"^foo$")'),
        Valid(
            "class Foo:\n" "    data: list[int] = []\n"  # class-level, not module-level
        ),
        Valid(
            "def foo():\n" "    cache = {}\n"  # local, not global
        ),
    ]
    INVALID = [
        Invalid("CACHE = {}"),
        Invalid("REGISTRY: list[str] = []"),
        Invalid("HANDLERS = set()"),
        Invalid("STATE = dict()"),
        Invalid("ITEMS = list()"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._depth = 0

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        self._depth += 1
        return True

    def leave_FunctionDef(self, node: cst.FunctionDef) -> None:
        self._depth -= 1

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        self._depth += 1
        return True

    def leave_ClassDef(self, node: cst.ClassDef) -> None:
        self._depth -= 1

    def visit_Assign(self, node: cst.Assign) -> None:
        """Catch: CACHE = {}"""
        if self._depth > 0:
            return
        if self._is_mutable_value(node.value):
            name = self._extract_name(node.targets[0].target)
            self.report(
                node,
                self.MESSAGE.format(name=name, type=self._mutable_type(node.value)),
            )

    def visit_AnnAssign(self, node: cst.AnnAssign) -> None:
        """Catch: CACHE: dict[str, int] = {}"""
        if self._depth > 0:
            return
        if node.value is not None and self._is_mutable_value(node.value):
            name = self._extract_name(node.target)
            self.report(
                node,
                self.MESSAGE.format(name=name, type=self._mutable_type(node.value)),
            )

    @staticmethod
    def _is_mutable_value(node: cst.BaseExpression) -> bool:
        """Check if the value is a mutable literal or constructor."""
        if isinstance(node, cst.Dict):
            return True
        if isinstance(node, cst.List):
            return True
        if isinstance(node, cst.Set):
            return True
        if isinstance(node, cst.Call):
            func = node.func
            if isinstance(func, cst.Name) and func.value in ("dict", "list", "set"):
                return True
        return False

    @staticmethod
    def _mutable_type(node: cst.BaseExpression) -> str:
        if isinstance(node, cst.Dict):
            return "dict literal"
        if isinstance(node, cst.List):
            return "list literal"
        if isinstance(node, cst.Set):
            return "set literal"
        if isinstance(node, cst.Call) and isinstance(node.func, cst.Name):
            return f"{node.func.value}() call"
        return "mutable"

    @staticmethod
    def _extract_name(node: cst.BaseAssignTargetExpression) -> str:
        if isinstance(node, cst.Name):
            return node.value
        return "<complex>"
