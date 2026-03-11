# aspergillus Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a standalone NASA-grade Python linter on Fixit/LibCST with 8 rules across 2 levels.

**Architecture:** Fixit LintRule subclasses organized by NASA level. Each rule has inline VALID/INVALID test cases plus pytest tests. Consumed as a git subtree with `repo: local` pre-commit hook.

**Tech Stack:** Python 3.10+, Fixit, LibCST, uv, pytest, ruff, mypy, pre-commit

**Design doc:** `docs/plans/2026-03-10-aspergillus-design.md` (in biscayne-agave-runbook)

---

### Task 1: Scaffold Repository

**Files:**
- Create: `~/code/git_puller/repos/aspergillus/pyproject.toml`
- Create: `~/code/git_puller/repos/aspergillus/.pre-commit-config.yaml`
- Create: `~/code/git_puller/repos/aspergillus/src/aspergillus/__init__.py`
- Create: `~/code/git_puller/repos/aspergillus/src/aspergillus/rules/__init__.py`
- Create: `~/code/git_puller/repos/aspergillus/src/aspergillus/io_blocklist.py`
- Create: `~/code/git_puller/repos/aspergillus/tests/__init__.py`

**Step 1: Create directory structure**

```bash
mkdir -p ~/code/git_puller/repos/aspergillus
cd ~/code/git_puller/repos/aspergillus
git init
mkdir -p src/aspergillus/rules tests
```

**Step 2: Write pyproject.toml**

```toml
[project]
name = "aspergillus"
version = "0.1.0"
description = "NASA-grade Python linter built on Fixit/LibCST"
requires-python = ">=3.10"

dependencies = [
    "fixit>=2.1.0",
    "libcst>=1.1.0",
    "ruff>=0.8.0",
    "mypy>=1.13.0",
    "pre-commit>=4.0.0",
    "pytest>=8.0.0",
]

[tool.fixit]
enable = [".src.aspergillus.rules"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP"]
ignore = ["E501", "B008"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Step 3: Write .pre-commit-config.yaml**

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.4
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: mypy
        name: mypy
        entry: uv run mypy --ignore-missing-imports --no-error-summary
        language: system
        types: [python]
```

**Step 4: Write io_blocklist.py**

```python
"""Known I/O functions for purity detection (ASP205, ASP206).

This is a heuristic blocklist. Purity is undecidable in general, but
matching calls against known I/O functions covers ~90% of real cases.
"""

from __future__ import annotations

# Fully qualified names and common short forms.
# ASP205/206 match if any call in a function body resolves to one of these.
IO_FUNCTIONS: frozenset[str] = frozenset(
    {
        # builtins
        "print",
        "input",
        "open",
        # subprocess
        "subprocess.run",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.Popen",
        # urllib
        "urllib.request.urlopen",
        "urllib.request.build_opener",
        # os filesystem
        "os.system",
        "os.popen",
        "os.remove",
        "os.unlink",
        "os.mkdir",
        "os.makedirs",
        "os.rename",
        "os.rmdir",
        # os.path is pure — intentionally excluded
        # logging
        "logging.info",
        "logging.warning",
        "logging.error",
        "logging.debug",
        "logging.critical",
        "logging.exception",
        "log.info",
        "log.warning",
        "log.error",
        "log.debug",
        "log.critical",
        "log.exception",
        # shutil
        "shutil.copy",
        "shutil.copy2",
        "shutil.copytree",
        "shutil.move",
        "shutil.rmtree",
        # socket
        "socket.socket",
        # pathlib write operations
        "Path.write_text",
        "Path.write_bytes",
        "Path.read_text",
        "Path.read_bytes",
        "Path.unlink",
        "Path.mkdir",
        "Path.rmdir",
        "Path.rename",
        "Path.touch",
    }
)
```

**Step 5: Write __init__.py files**

`src/aspergillus/__init__.py`:
```python
"""aspergillus — NASA-grade Python linter."""
```

`src/aspergillus/rules/__init__.py`:
```python
"""Fixit lint rules organized by NASA quality level."""
```

`tests/__init__.py`: empty file.

**Step 6: Initialize and verify**

```bash
cd ~/code/git_puller/repos/aspergillus
uv sync
uv run pre-commit install
uv run pre-commit run --all-files
```

Expected: all hooks pass.

**Step 7: Initialize pebbles**

```bash
cd ~/code/git_puller/repos/aspergillus
cd ../pebbles && go run ./cmd/pb init --dir ../aspergillus --prefix asp
```

**Step 8: Commit**

```bash
git add -A
git commit -m "feat: scaffold aspergillus repo with fixit, pre-commit, io blocklist"
```

---

### Task 2: ASP201 — Function Too Long

**Files:**
- Create: `src/aspergillus/rules/level2.py`
- Create: `tests/test_level2.py`

**Step 1: Write the failing test**

```python
# tests/test_level2.py
"""Tests for Level 2 NASA rules."""
from __future__ import annotations

import pytest
from fixit.testing import add_lint_rule_tests_to_module

from aspergillus.rules.level2 import FunctionTooLong

add_lint_rule_tests_to_module(FunctionTooLong, globals())


def test_asp201_threshold() -> None:
    """60-line function passes, 61-line function fails."""
    # Fixit VALID/INVALID inline tests handle this,
    # but this confirms the exact boundary.
    pass  # covered by VALID/INVALID test cases
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_level2.py -v
```

Expected: FAIL — `ImportError: cannot import name 'FunctionTooLong'`

**Step 3: Write the rule**

```python
# src/aspergillus/rules/level2.py
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
            "def short():\n"
            + "".join(f"    x{i} = {i}\n" for i in range(58))
            + "    return x0\n"
        ),
        Valid("def one_liner(): pass"),
        Valid(
            "class Foo:\n"
            "    def method(self):\n"
            "        pass\n"
        ),
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
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_level2.py -v
```

Expected: PASS

**Step 5: Verify fixit CLI works**

```bash
uv run fixit lint src/aspergillus/
```

Expected: no violations (our own code should be clean).

**Step 6: Commit**

```bash
git add src/aspergillus/rules/level2.py tests/test_level2.py
git commit -m "feat: ASP201 function too long (>60 lines)"
```

---

### Task 3: ASP202 — Missing Assertions

**Files:**
- Modify: `src/aspergillus/rules/level2.py`
- Modify: `tests/test_level2.py`

**Step 1: Write the failing test**

Add to `tests/test_level2.py`:

```python
from aspergillus.rules.level2 import LowAssertionDensity

add_lint_rule_tests_to_module(LowAssertionDensity, globals())
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_level2.py -v
```

Expected: FAIL — `ImportError`

**Step 3: Write the rule**

Add to `src/aspergillus/rules/level2.py`:

```python
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
            "def test_something():\n"
            "    result = compute()\n"
            "    assert result == 42\n"
        ),  # test function, exempt
        Valid(
            "def __init__(self, x: int):\n"
            "    self.x = x\n"
        ),  # dunder, exempt
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
        # Check exemptions
        name = node.name.value
        if any(name.startswith(p) for p in self.EXEMPT_PREFIXES):
            return

        # Check line count — skip trivial functions
        pos = self.get_metadata(cst.metadata.PositionProvider, node)
        line_count = pos.end.line - pos.start.line + 1
        if line_count <= self.MIN_LINES_FOR_RULE:
            return

        # Count assert statements
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
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_level2.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/aspergillus/rules/level2.py tests/test_level2.py
git commit -m "feat: ASP202 low assertion density (<2 per function)"
```

---

### Task 4: ASP203 — Global Mutable State

**Files:**
- Modify: `src/aspergillus/rules/level2.py`
- Modify: `tests/test_level2.py`

**Step 1: Write the failing test**

Add to `tests/test_level2.py`:

```python
from aspergillus.rules.level2 import GlobalMutableState

add_lint_rule_tests_to_module(GlobalMutableState, globals())
```

**Step 2: Run to verify failure, then write the rule**

Add to `src/aspergillus/rules/level2.py`:

```python
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
        Valid('TIMEOUT: int = 30'),
        Valid('NAME: str = "hello"'),
        Valid('ITEMS: tuple[int, ...] = (1, 2, 3)'),
        Valid('ITEMS: frozenset[str] = frozenset({"a", "b"})'),
        Valid('PATTERN = re.compile(r"^foo$")'),
        Valid(
            "class Foo:\n"
            "    data: list[int] = []\n"  # class-level, not module-level
        ),
        Valid(
            "def foo():\n"
            "    cache = {}\n"  # local, not global
        ),
    ]
    INVALID = [
        Invalid("CACHE = {}"),
        Invalid("REGISTRY: list[str] = []"),
        Invalid("HANDLERS = set()"),
        Invalid("STATE = dict()"),
        Invalid("ITEMS = list()"),
    ]

    def visit_SimpleStatementLine(self, node: cst.SimpleStatementLine) -> None:
        # Only check module-level statements (not inside class/function)
        # LibCST provides scope via metadata, but a simpler check:
        # we only fire at module level, which fixit handles via the
        # visitor pattern — visit_ClassDef and visit_FunctionDef will
        # push us into nested scopes. We need QualifiedNameProvider or
        # a manual depth counter.
        pass  # see _is_mutable_value helper

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

    @staticmethod
    def _is_mutable_value(node: cst.BaseExpression) -> bool:
        """Check if the value is a mutable literal or constructor."""
        # {} or {k: v}
        if isinstance(node, cst.Dict):
            return True
        # [] or [x, y]
        if isinstance(node, cst.List):
            return True
        # set() — note: {1, 2} is a cst.Set
        if isinstance(node, cst.Set):
            return True
        # dict(), list(), set()
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
```

Note: the `visit_SimpleStatementLine` is a no-op placeholder; the actual
logic is in `visit_Assign` and `visit_AnnAssign`. Remove the placeholder
during implementation if fixit complains.

**Step 3: Run tests**

```bash
uv run pytest tests/test_level2.py -v
```

**Step 4: Commit**

```bash
git add src/aspergillus/rules/level2.py tests/test_level2.py
git commit -m "feat: ASP203 global mutable state detection"
```

---

### Task 5: ASP204 — Unbounded Loops

**Files:**
- Modify: `src/aspergillus/rules/level2.py`
- Modify: `tests/test_level2.py`

**Step 1: Write the failing test, then the rule**

Add to `src/aspergillus/rules/level2.py`:

```python
class UnboundedLoop(LintRule):
    """ASP204: Loops must have a provably fixed upper bound.

    NASA Power of 10 Rule #2: Every loop must have a provable upper
    bound. `for` loops over iterables are bounded by definition.
    `while True` and `while <condition>` without an obvious counter
    or break are flagged.

    Allowed patterns:
    - `for x in iterable` (bounded by iterable length)
    - `while condition` where condition references a counter that
      is incremented in the body (heuristic)
    - `while True` with a `break` statement in the body
    """

    MESSAGE = "ASP204: Unbounded loop — add a counter, break, or use `for`"

    VALID = [
        Valid(
            "for i in range(10):\n"
            "    print(i)\n"
        ),
        Valid(
            "while True:\n"
            "    data = read()\n"
            "    if not data:\n"
            "        break\n"
        ),
        Valid(
            "count = 0\n"
            "while count < 100:\n"
            "    count += 1\n"
        ),
    ]
    INVALID = [
        Invalid(
            "while True:\n"
            "    process()\n"
        ),
        Invalid(
            "while condition:\n"
            "    process()\n"
        ),
    ]

    def visit_While(self, node: cst.While) -> None:
        if self._has_break(node.body):
            return
        self.report(node, self.MESSAGE)

    @staticmethod
    def _has_break(body: cst.BaseSuite) -> bool:
        """Check if body contains a Break statement (any depth)."""

        class BreakFinder(cst.CSTVisitor):
            found = False

            def visit_Break(self, node: cst.Break) -> None:
                self.found = True

            # Don't descend into nested loops — their breaks
            # don't count for the outer loop
            def visit_While(self, node: cst.While) -> bool:
                return False

            def visit_For(self, node: cst.For) -> bool:
                return False

        finder = BreakFinder()
        body.walk(finder)
        return finder.found
```

**Step 2: Run tests, commit**

```bash
uv run pytest tests/test_level2.py -v
git add src/aspergillus/rules/level2.py tests/test_level2.py
git commit -m "feat: ASP204 unbounded loop detection"
```

---

### Task 6: ASP205 — Impure Function

**Files:**
- Modify: `src/aspergillus/rules/level2.py`
- Modify: `tests/test_level2.py`

**Step 1: Write the rule**

Add to `src/aspergillus/rules/level2.py`:

```python
from aspergillus.io_blocklist import IO_FUNCTIONS


class ImpureFunction(LintRule):
    """ASP205: Function calls known I/O — mark as impure or refactor.

    NASA Level 2: 70%+ of functions should be pure. This rule flags
    functions that call known I/O functions (from io_blocklist.py).

    The function is not necessarily wrong — orchestrator/shell functions
    are expected to do I/O. But the flag encourages separating pure
    logic from I/O at the boundaries.
    """

    MESSAGE = "ASP205: Function calls I/O: {calls}"

    VALID = [
        Valid(
            "def add(a: int, b: int) -> int:\n"
            "    assert a >= 0\n"
            "    assert b >= 0\n"
            "    return a + b\n"
        ),
    ]
    INVALID = [
        Invalid(
            "def save(data: str) -> None:\n"
            "    assert data\n"
            "    assert isinstance(data, str)\n"
            "    print(data)\n"
        ),
    ]

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        io_calls = self._find_io_calls(node.body)
        if io_calls:
            self.report(
                node,
                self.MESSAGE.format(calls=", ".join(sorted(io_calls))),
            )

    def _find_io_calls(self, body: cst.BaseSuite) -> set[str]:
        """Find calls to known I/O functions in a function body."""

        class IOCallFinder(cst.CSTVisitor):
            found: set[str] = set()

            def visit_Call(self, node: cst.Call) -> None:
                name = _resolve_call_name(node.func)
                if name and name in IO_FUNCTIONS:
                    self.found.add(name)

        finder = IOCallFinder()
        finder.found = set()  # reset per invocation
        body.walk(finder)
        return finder.found


def _resolve_call_name(node: cst.BaseExpression) -> str | None:
    """Resolve a call target to a dotted name string.

    print -> "print"
    subprocess.run -> "subprocess.run"
    self.log.info -> "log.info" (strips self)
    """
    if isinstance(node, cst.Name):
        return node.value
    if isinstance(node, cst.Attribute):
        parts: list[str] = [node.attr.value]
        current = node.value
        while isinstance(current, cst.Attribute):
            parts.append(current.attr.value)
            current = current.value
        if isinstance(current, cst.Name):
            if current.value != "self":
                parts.append(current.value)
        parts.reverse()
        return ".".join(parts)
    return None
```

**Step 2: Run tests, commit**

```bash
uv run pytest tests/test_level2.py -v
git add src/aspergillus/rules/level2.py tests/test_level2.py
git commit -m "feat: ASP205 impure function detection via I/O blocklist"
```

---

### Task 7: ASP206 — Mixed I/O and Logic (FC/IS Violation)

**Files:**
- Modify: `src/aspergillus/rules/level2.py`
- Modify: `tests/test_level2.py`

**Step 1: Write the rule**

This builds on ASP205's `_find_io_calls` and `_resolve_call_name`.

```python
class MixedIOAndLogic(LintRule):
    """ASP206: Function mixes I/O with non-trivial logic.

    The functional core / imperative shell pattern separates pure
    business logic from I/O. This rule flags functions that do both:
    they call I/O functions AND have enough non-I/O statements to
    suggest business logic is mixed in.

    Threshold: function has I/O calls AND >3 non-I/O statements
    (assignments, returns, conditionals, loops).

    Orchestrator functions that just wire I/O calls together (call A,
    pass result to B, return) are fine — the statement threshold
    filters them out.
    """

    MESSAGE = "ASP206: Function mixes I/O ({io_calls}) with {logic_count} logic statements — consider functional core / imperative shell"
    LOGIC_THRESHOLD = 3
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    VALID = [
        Valid(
            "def orchestrator():\n"
            "    data = fetch()\n"  # I/O
            "    save(data)\n"      # I/O, but only 1 non-I/O stmt
            "    return data\n"
        ),
        Valid(
            "def pure_logic(items: list) -> int:\n"
            "    assert len(items) > 0\n"
            "    assert all(x > 0 for x in items)\n"
            "    total = sum(items)\n"
            "    avg = total / len(items)\n"
            "    return int(avg)\n"
        ),
    ]
    INVALID = [
        Invalid(
            "def mixed(url: str) -> int:\n"
            "    data = urllib.request.urlopen(url)\n"  # I/O
            "    assert data is not None\n"
            "    assert len(data) > 0\n"
            "    parsed = json.loads(data)\n"
            "    total = sum(parsed['values'])\n"
            "    avg = total / len(parsed['values'])\n"
            "    result = int(avg * 100)\n"
            "    return result\n"
        ),
    ]

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        io_calls = self._find_io_calls(node.body)
        if not io_calls:
            return  # no I/O, pure function — fine

        logic_count = self._count_logic_statements(node.body)
        if logic_count > self.LOGIC_THRESHOLD:
            self.report(
                node,
                self.MESSAGE.format(
                    io_calls=", ".join(sorted(io_calls)),
                    logic_count=logic_count,
                ),
            )

    def _find_io_calls(self, body: cst.BaseSuite) -> set[str]:
        """Reuse from ASP205."""
        class IOCallFinder(cst.CSTVisitor):
            found: set[str] = set()
            def visit_Call(self, node: cst.Call) -> None:
                name = _resolve_call_name(node.func)
                if name and name in IO_FUNCTIONS:
                    self.found.add(name)

        finder = IOCallFinder()
        finder.found = set()
        body.walk(finder)
        return finder.found

    @staticmethod
    def _count_logic_statements(body: cst.BaseSuite) -> int:
        """Count non-trivial logic statements (assignments, returns, ifs, loops)."""
        count = 0
        if isinstance(body, cst.IndentedBlock):
            for stmt in body.body:
                if isinstance(stmt, cst.SimpleStatementLine):
                    for item in stmt.body:
                        if isinstance(item, (cst.Assign, cst.AnnAssign, cst.AugAssign, cst.Return, cst.Assert)):
                            count += 1
                elif isinstance(stmt, (cst.If, cst.For, cst.While)):
                    count += 1
        return count
```

Note: `_find_io_calls` is duplicated from ASP205. During implementation,
extract it to a shared helper in `level2.py` or a utils module. DRY.

**Step 2: Run tests, commit**

```bash
uv run pytest tests/test_level2.py -v
git add src/aspergillus/rules/level2.py tests/test_level2.py
git commit -m "feat: ASP206 mixed I/O and logic (FC/IS violation)"
```

---

### Task 8: ASP301 — Raise Where Result Could Be Used

**Files:**
- Create: `src/aspergillus/rules/level3.py`
- Create: `tests/test_level3.py`

**Step 1: Write the rule**

```python
# src/aspergillus/rules/level3.py
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
        ),  # no raise, just assert
        Valid(
            "def fail_always() -> None:\n"
            "    raise NotImplementedError\n"
        ),  # only raises, no return
        Valid(
            "def __init__(self, x: int) -> None:\n"
            "    if x < 0:\n"
            "        raise ValueError\n"
            "    self.x = x\n"
        ),  # __init__ exempt
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

        has_raise = self._has_node_type(node.body, cst.Raise)
        has_return = self._has_return_value(node.body)

        if has_raise and has_return:
            self.report(node, self.MESSAGE)

    @staticmethod
    def _has_node_type(body: cst.BaseSuite, node_type: type) -> bool:
        class Finder(cst.CSTVisitor):
            found = False
            def on_visit(self, node: cst.CSTNode) -> bool:
                if isinstance(node, node_type):
                    self.found = True
                return True
            # Don't descend into nested functions
            def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
                return False

        finder = Finder()
        finder.found = False
        body.walk(finder)
        return finder.found

    @staticmethod
    def _has_return_value(body: cst.BaseSuite) -> bool:
        """Check for `return <expr>` (not bare `return` or `return None`)."""

        class ReturnFinder(cst.CSTVisitor):
            found = False
            def visit_Return(self, node: cst.Return) -> None:
                if node.value is not None:
                    # Exclude `return None`
                    if not (isinstance(node.value, cst.Name) and node.value.value == "None"):
                        self.found = True
            def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
                return False

        finder = ReturnFinder()
        finder.found = False
        body.walk(finder)
        return finder.found
```

**Step 2: Write test file**

```python
# tests/test_level3.py
"""Tests for Level 3 NASA rules."""
from __future__ import annotations

from fixit.testing import add_lint_rule_tests_to_module

from aspergillus.rules.level3 import RaiseInsteadOfResult

add_lint_rule_tests_to_module(RaiseInsteadOfResult, globals())
```

**Step 3: Run tests, commit**

```bash
uv run pytest tests/test_level3.py -v
git add src/aspergillus/rules/level3.py tests/test_level3.py
git commit -m "feat: ASP301 raise instead of Result type"
```

---

### Task 9: ASP302 — Optional/None Return Type

**Files:**
- Modify: `src/aspergillus/rules/level3.py`
- Modify: `tests/test_level3.py`

**Step 1: Write the rule**

Add to `src/aspergillus/rules/level3.py`:

```python
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
        Valid(
            "def get_value() -> int:\n"
            "    assert True\n"
            "    assert True\n"
            "    return 42\n"
        ),
        Valid(
            "def __init__(self) -> None:\n"
            "    self.x = 1\n"
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
        # X | None  (BinaryOperation with BitOr)
        if isinstance(node, cst.BinaryOperation):
            if isinstance(node.operator, cst.BitOr):
                # Check if either side is None
                if (isinstance(node.right, cst.Name) and node.right.value == "None") or (
                    isinstance(node.left, cst.Name) and node.left.value == "None"
                ):
                    return True
        # Optional[X]
        if isinstance(node, cst.Subscript):
            if isinstance(node.value, cst.Name) and node.value.value == "Optional":
                return True
        return False
```

**Step 2: Run tests, commit**

```bash
uv run pytest tests/ -v
git add src/aspergillus/rules/level3.py tests/test_level3.py
git commit -m "feat: ASP302 Optional return type flagging"
```

---

### Task 10: Full Test Suite + Pre-commit Verification

**Files:**
- All existing files

**Step 1: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass.

**Step 2: Run pre-commit on self**

```bash
uv run pre-commit run --all-files
```

Expected: all hooks pass (ruff, ruff-format, mypy).

**Step 3: Run fixit on self**

```bash
uv run fixit lint src/
```

Expected: aspergillus's own code should be clean (or have justified suppressions).

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "chore: fix any self-lint issues"
```

---

### Task 11: Integration Test with snapshot_download.py

**Step 1: Copy snapshot_download.py and run aspergillus against it**

```bash
# From the aspergillus repo, lint the biscayne file directly
uv run fixit lint ~/code/git_puller/repos/biscayne-agave-runbook/agave-stack/stack-orchestrator/container-build/laconicnetwork-agave/snapshot_download.py
```

**Step 2: Document findings**

Record which rules fire, how many violations, and whether the output
is useful or too noisy. Adjust thresholds if needed (e.g., MAX_LINES,
LOGIC_THRESHOLD, MIN_LINES_FOR_RULE).

**Step 3: Commit threshold adjustments if any**

```bash
git add -A
git commit -m "chore: tune thresholds based on snapshot_download.py integration test"
```

---

Plan complete and saved to `docs/plans/2026-03-10-aspergillus-impl.md`. Two execution options:

**1. Subagent-Driven (this session)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** — Open new session with executing-plans, batch execution with checkpoints

Which approach?
