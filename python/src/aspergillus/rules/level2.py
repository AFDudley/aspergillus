"""NASA Level 2 rules: pure functions + immutability."""

from __future__ import annotations

from collections.abc import Sequence

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
        Valid("class Foo:\n    def method(self):\n        pass\n"),
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
    """ASP202: Imperative-shell functions should have >=2 assertions.

    NASA Power of 10 Rule #5: High assertion density. Assertions are
    executable documentation of invariants — and the correct correctness
    mechanism for the **imperative shell**, where a runtime precondition
    guards data the type system cannot. They are NOT the mechanism for
    the **functional core**: a pure, fully-typed transform earns its
    correctness statically from the OTHER L3 rules (``mypy --strict``
    types, ``Result``-not-throw, purity ASP205/206), so demanding two
    runtime ``assert``\\ s there mis-prescribes the shell mechanism onto
    the core. This rule therefore applies its >=2-assertion requirement
    **only to functions in the imperative shell** (see
    ``_is_imperative_shell``) and exempts the pure, statically-constrained
    functional core.

    Functional-core / imperative-shell predicate (asp-da5). A function is
    in the imperative shell — and thus in scope for ASP202 — iff EITHER:

    - **it performs I/O** — its body calls a known I/O function (the SAME
      ``io_blocklist`` signal ASP205 / ASP206 use; ``_find_io_calls``).
      Side-effecting functions are the shell; preconditions on their
      inputs/environment are exactly NASA Rule #5's domain. OR
    - **it ingests dynamically-typed / untrusted data** — it has a
      parameter that is unannotated or annotated with a dynamic,
      unconstrained type (``DYNAMIC_PARAM_ANNOTATIONS`` — ``Any`` /
      ``object``). The type system cannot constrain such a value, so a
      pure function that takes it is still shell-ish: a runtime
      precondition IS the right guard (``_has_untrusted_param``).

    A PURE function whose every parameter is concretely typed is the
    functional core and is EXEMPT — this composes the existing FC/IS
    boundary (the ASP205/206 I/O signal) with the type system, rather
    than inventing a new heuristic. (Evidence, asp-da5: of the gateway's
    261-finding asp-070 residual, 255 were pure + fully-typed functional
    core — the rule mis-prescribing the shell mechanism — collapsing to
    6 genuine imperative-shell low-assertion functions; backtest 109 -> 8.)

    What counts as an assertion (NASA equivalence ``assert(cond)`` ≡
    ``if not cond: raise``):

    - ``assert`` statements (anywhere in the body, including inside
      ``if`` / ``for`` / ``with`` blocks).
    - ``raise`` statements, when ``COUNT_RAISE_STATEMENTS`` is true. A
      precondition guard (``if bad: raise ...``) enforces an invariant
      exactly as an ``assert`` does — and survives ``python -O``, which
      strips ``assert``. Parity with the TS sibling's
      ``countThrowStatements``.
    - calls to validation methods named in ``ASSERTION_METHOD_NAMES``
      regardless of receiver — ``payload.model_validate(...)``,
      ``Schema.parse(...)``, etc. These re-validate a value against a
      declared shape. Parity with the TS sibling's ``methodNames``.
    - a method decorated with a pydantic validator
      (``VALIDATION_DECORATORS`` — ``@field_validator`` /
      ``@model_validator`` / legacy ``@validator`` / ``@root_validator``)
      IS itself a precondition check, so the method is exempt; it also
      contributes one assertion to its enclosing model (below).
    - a model field declared with a *constraining* ``Field(...)`` call
      (``FIELD_CONSTRAINT_CALLEES`` whose call carries at least one
      keyword in ``FIELD_CONSTRAINT_KWARGS`` — ``Field(gt=0)``,
      ``Field(min_length=1)``, …) is a declarative precondition. Each
      such field, and each validator method, credits the model's
      methods: a method of a constrained model inherits the model's
      declared invariants and need not restate them as ``assert``.

    These were blanket-disabled in gateway/backtest because the
    original implementation counted only literal ``assert`` statements,
    false-positiving on idiomatic pydantic + ``raise``-guard Python
    (gateway: ``docs/labbook/2026-04-19-asp202-disabled-gateway.md``).

    Configurability (parity with the TS sibling
    ``aspergillus/typescript/rules/asp202-min-assertions.js`` options):
    every recognized set is an overridable class attribute, the
    idiomatic fixit tuning mechanism (cf. ``MAX_LINES`` on
    ``FunctionTooLong``). A consumer tunes by subclassing and enabling
    the subclass rather than disabling the rule wholesale::

        class ProjectASP202(LowAssertionDensity):
            ASSERTION_METHOD_NAMES = frozenset({"parse", "check_schema"})

    Exemptions: functions <=5 lines (trivial), test functions,
    ``__init__``, ``__repr__``, ``__str__``, ``__eq__``, ``__hash__``,
    pydantic-validator methods, and pure functional-core functions (no
    I/O and no dynamically-typed parameter — see the FC/IS predicate
    above).
    """

    MESSAGE = "ASP202: Function has {actual} assertions (min {min_asserts})"
    MIN_ASSERTS = 2
    EXEMPT_PREFIXES = ("test_", "__init__", "__repr__", "__str__", "__eq__", "__hash__")
    MIN_LINES_FOR_RULE = 5
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    # --- recognized-assertion configuration (parity with the TS rule) ---
    # ≡ TS countThrowStatements: NASA `assert(cond)` is `if (!cond) throw`.
    COUNT_RAISE_STATEMENTS = True
    # ≡ TS methodNames: validation methods that count regardless of receiver.
    ASSERTION_METHOD_NAMES = frozenset(
        {"model_validate", "model_validate_json", "parse", "parse_obj", "validate"}
    )
    # Decorators that mark a method as a pydantic validator (precondition).
    VALIDATION_DECORATORS = frozenset(
        {"field_validator", "model_validator", "validator", "root_validator"}
    )
    # Callees whose constraining keyword args declare a field precondition.
    FIELD_CONSTRAINT_CALLEES = frozenset({"Field"})
    # Keyword args that make a `Field(...)` a constraint (not a bare default).
    FIELD_CONSTRAINT_KWARGS = frozenset(
        {
            "gt",
            "ge",
            "lt",
            "le",
            "multiple_of",
            "min_length",
            "max_length",
            "min_items",
            "max_items",
            "pattern",
            "regex",
            "max_digits",
            "decimal_places",
            "allow_inf_nan",
            "strict",
        }
    )
    # Parameter annotations the type system cannot constrain. A function
    # taking such a value ingests untrusted data and is imperative-shell
    # even when otherwise pure (see the FC/IS predicate in the docstring).
    DYNAMIC_PARAM_ANNOTATIONS = frozenset({"Any", "object"})

    VALID = [
        Valid(
            "def transfer(a: float, b: float) -> float:\n"
            "    assert a >= 0\n"
            "    assert b > 0\n"
            "    return a - b\n"
        ),
        Valid("def tiny(): return 1"),  # too short, exempt
        Valid(
            "def test_something():\n    result = compute()\n    assert result == 42\n"
        ),  # test function, exempt
        Valid("def __init__(self, x: int):\n    self.x = x\n"),  # dunder, exempt
        # `raise` guards count: precondition enforcement ≡ assert.
        Valid(
            "def validate_range(lo: int, hi: int) -> int:\n"
            "    if lo < 0:\n"
            "        raise ValueError('lo')\n"
            "    if hi < lo:\n"
            "        raise ValueError('hi')\n"
            "    span = hi - lo\n"
            "    return span\n"
        ),
        # validation method-name calls count regardless of receiver.
        Valid(
            "def decode(raw: bytes, schema: object) -> object:\n"
            "    parsed = schema.model_validate(raw)\n"
            "    checked = schema.model_validate(parsed)\n"
            "    enriched = dict(checked)\n"
            "    return enriched\n"
        ),
        # a pydantic-validator method is itself a precondition — exempt.
        Valid(
            "class Order(BaseModel):\n"
            "    @field_validator('qty')\n"
            "    @classmethod\n"
            "    def check_qty(cls, v: int) -> int:\n"
            "        normalized = int(v)\n"
            "        doubled = normalized * 2\n"
            "        adjusted = doubled - normalized\n"
            "        return adjusted\n"
        ),
        # a constraining-Field model credits its methods' assertion count.
        Valid(
            "class Account(BaseModel):\n"
            "    balance: float = Field(gt=0)\n"
            "    limit: float = Field(ge=0)\n"
            "    def describe(self) -> str:\n"
            "        label = 'account'\n"
            "        parts = [label, str(self.balance)]\n"
            "        joined = ' '.join(parts)\n"
            "        result = joined.upper()\n"
            "        return result\n"
        ),
        # --- FC/IS predicate (asp-da5): functional core is EXEMPT ---
        # A pure, fully-typed transform earns correctness from the type
        # system, not runtime asserts. No I/O, every param concretely
        # typed -> functional core -> exempt despite 0 assertions.
        Valid(
            "def process(data: list) -> int:\n"
            "    total = 0\n"
            "    for item in data:\n"
            "        total += item.value\n"
            "    filtered = [x for x in data if x.value > 0]\n"
            "    result = sum(x.value for x in filtered)\n"
            "    return result\n"
        ),
        Valid(
            "def compute(data: list) -> int:\n"
            "    a = data[0]\n"
            "    b = data[1]\n"
            "    c = a + b\n"
            "    d = c * 2\n"
            "    e = d - a\n"
            "    return e\n"
        ),
        # A plain model's pure, typed method is functional core -> exempt.
        Valid(
            "class Plain(BaseModel):\n"
            "    name: str\n"
            "    value: int\n"
            "    def render(self) -> str:\n"
            "        a = self.name\n"
            "        b = str(self.value)\n"
            "        c = a + b\n"
            "        d = c.strip()\n"
            "        return d\n"
        ),
        # A pure, fully-typed helper with 0 assertions: functional core.
        Valid(
            "def summarize(values: tuple[int, ...]) -> int:\n"
            "    total = sum(values)\n"
            "    count = len(values)\n"
            "    scaled = total * 2\n"
            "    shifted = scaled - count\n"
            "    return shifted\n"
        ),
    ]
    INVALID = [
        # --- FC/IS predicate (asp-da5): imperative shell IS in scope ---
        # Performs I/O (io_blocklist) with <2 assertions -> shell, flagged.
        Invalid(
            "def write_log(path: str, message: str) -> None:\n"
            "    prefix = '[log] '\n"
            "    body = prefix + message\n"
            "    full = body.upper()\n"
            "    trimmed = full.strip()\n"
            "    print(trimmed)\n"
        ),
        # Pure but ingests a dynamically-typed value (`Any`) -> untrusted
        # boundary -> imperative shell, flagged at <2 assertions.
        Invalid(
            "def normalize(payload: Any) -> dict:\n"
            "    raw = payload\n"
            "    keys = list(raw)\n"
            "    first = keys[0]\n"
            "    rest = keys[1:]\n"
            "    return {first: rest}\n"
        ),
        # Unannotated parameters -> the type system cannot constrain them
        # -> untrusted boundary -> imperative shell, flagged.
        Invalid(
            "def merge(left, right) -> dict:\n"
            "    combined = {}\n"
            "    combined.update(left)\n"
            "    combined.update(right)\n"
            "    sized = len(combined)\n"
            "    return combined if sized else left\n"
        ),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Stack of per-enclosing-class declarative-assertion credit.
        self._class_credit: list[int] = []

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        self._class_credit.append(
            _class_assertion_credit(
                node,
                self.FIELD_CONSTRAINT_CALLEES,
                self.FIELD_CONSTRAINT_KWARGS,
                self.VALIDATION_DECORATORS,
            )
        )
        return True

    def leave_ClassDef(self, node: cst.ClassDef) -> None:
        self._class_credit.pop()

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        name = node.name.value
        if any(name.startswith(p) for p in self.EXEMPT_PREFIXES):
            return
        if _has_decorator_in(node, self.VALIDATION_DECORATORS):
            return

        pos = self.get_metadata(cst.metadata.PositionProvider, node)
        line_count = pos.end.line - pos.start.line + 1
        if line_count <= self.MIN_LINES_FOR_RULE:
            return

        # FC/IS predicate: ASP202 is the imperative-shell mechanism. A
        # pure, fully-typed functional-core function is exempt — its
        # correctness is enforced statically by the other L3 rules.
        if not _is_imperative_shell(node, self.DYNAMIC_PARAM_ANNOTATIONS):
            return

        assert_count = _count_assertions(
            node.body,
            self.COUNT_RAISE_STATEMENTS,
            self.ASSERTION_METHOD_NAMES,
        )
        if self._class_credit:
            assert_count += self._class_credit[-1]
        if assert_count < self.MIN_ASSERTS:
            self.report(
                node,
                self.MESSAGE.format(actual=assert_count, min_asserts=self.MIN_ASSERTS),
            )


def _iter_skip_nested(node: cst.CSTNode) -> list[cst.CSTNode]:
    """All descendants of ``node`` (incl. ``node``), not descending into
    nested function/lambda bodies — those are visited as their own units.
    """
    found: list[cst.CSTNode] = [node]
    for child in node.children:
        if isinstance(child, cst.FunctionDef | cst.Lambda):
            continue
        found.extend(_iter_skip_nested(child))
    return found


def _is_assertion_method_call(node: cst.CSTNode, method_names: frozenset[str]) -> bool:
    """True for ``recv.<method>(...)`` where ``<method>`` is recognized."""
    return (
        isinstance(node, cst.Call)
        and isinstance(node.func, cst.Attribute)
        and node.func.attr.value in method_names
    )


def _count_assertions(
    body: cst.BaseSuite,
    count_raise: bool,
    method_names: frozenset[str],
) -> int:
    """Count assertion-like constructs in a function body.

    Recurses through nested ``if`` / ``for`` / ``with`` / ``try`` blocks
    (a ``raise`` inside a guard counts) but not into nested function or
    lambda bodies. Recognized: ``assert`` statements; ``raise``
    statements when ``count_raise``; calls to ``method_names``.
    """
    if not isinstance(body, cst.IndentedBlock):
        return 0
    count = 0
    for node in _iter_skip_nested(body):
        if isinstance(node, cst.Assert):
            count += 1
        elif count_raise and isinstance(node, cst.Raise):
            count += 1
        elif _is_assertion_method_call(node, method_names):
            count += 1
    return count


def _decorator_base_name(decorator: cst.Decorator) -> str:
    """Resolve a decorator to its base callee name (``""`` if unresolved).

    ``@field_validator('x')`` and ``@pydantic.field_validator`` both
    resolve to ``field_validator``.
    """
    expr = decorator.decorator
    if isinstance(expr, cst.Call):
        expr = expr.func
    name = _resolve_call_name(expr)
    if name is None:
        return ""
    return name.rsplit(".", 1)[-1]


def _has_decorator_in(node: cst.FunctionDef, names: frozenset[str]) -> bool:
    """True if any of the function's decorators resolves into ``names``."""
    return any(_decorator_base_name(dec) in names for dec in node.decorators)


def _is_constraining_field(
    value: cst.BaseExpression | None,
    callees: frozenset[str],
    kwargs: frozenset[str],
) -> bool:
    """True for ``Field(gt=0)``-style calls: a recognized callee carrying
    at least one constraining keyword (not a bare ``Field(default=...)``).
    """
    if not isinstance(value, cst.Call):
        return False
    name = _resolve_call_name(value.func)
    if name is None or name.rsplit(".", 1)[-1] not in callees:
        return False
    return any(arg.keyword is not None and arg.keyword.value in kwargs for arg in value.args)


def _class_assertion_credit(
    node: cst.ClassDef,
    field_callees: frozenset[str],
    field_kwargs: frozenset[str],
    validator_decorators: frozenset[str],
) -> int:
    """Declarative-assertion credit a class confers on its methods.

    Counts top-level constraining ``Field(...)`` declarations plus
    validator-decorated methods in the class body. A method of a model
    whose fields/validators already declare its invariants inherits
    them and need not restate them as ``assert``.
    """
    body = node.body
    if not isinstance(body, cst.IndentedBlock):
        return 0
    credit = 0
    for stmt in body.body:
        if isinstance(stmt, cst.SimpleStatementLine):
            for item in stmt.body:
                if isinstance(item, cst.AnnAssign) and _is_constraining_field(
                    item.value, field_callees, field_kwargs
                ):
                    credit += 1
                elif isinstance(item, cst.Assign) and _is_constraining_field(
                    item.value, field_callees, field_kwargs
                ):
                    credit += 1
        elif isinstance(stmt, cst.FunctionDef) and _has_decorator_in(stmt, validator_decorators):
            credit += 1
    return credit


# Sentinel returned by `_param_annotation_basename` for a parameter with
# no annotation. Empty string is unrepresentable as a real annotation
# name, so this keeps the function total (no Optional) while letting the
# caller treat "absent" as one of the untrusted cases.
_NO_ANNOTATION = ""


def _param_annotation_basename(annotation: cst.Annotation | None) -> str:
    """Resolve a parameter annotation to a base name.

    Returns ``_NO_ANNOTATION`` (``""``) when absent; ``Any`` -> ``"Any"``;
    ``object`` -> ``"object"``; ``dict[str, int]`` -> ``"dict"``;
    ``mod.Thing`` -> ``"Thing"``. The base name is all the FC/IS predicate
    needs — it only distinguishes dynamic/unconstrained annotations from
    concrete ones.
    """
    if annotation is None:
        return _NO_ANNOTATION
    expr = annotation.annotation
    if isinstance(expr, cst.Name):
        return expr.value
    if isinstance(expr, cst.Attribute):
        return expr.attr.value
    if isinstance(expr, cst.Subscript):
        base = expr.value
        if isinstance(base, cst.Name):
            return base.value
        if isinstance(base, cst.Attribute):
            return base.attr.value
    return "<other>"


def _has_untrusted_param(node: cst.FunctionDef, dynamic_annotations: frozenset[str]) -> bool:
    """True if a parameter is unannotated or dynamically typed.

    Such a parameter carries no static guarantee, so a function taking
    it ingests untrusted data and is imperative-shell. The leading
    ``self`` / ``cls`` of a method is skipped (it is never the untrusted
    input). ``*args`` / ``**kwargs`` collectors are not considered.
    """
    params = node.params
    ordered = list(params.posonly_params) + list(params.params) + list(params.kwonly_params)
    for index, param in enumerate(ordered):
        if index == 0 and param.name.value in ("self", "cls"):
            continue
        basename = _param_annotation_basename(param.annotation)
        if basename == _NO_ANNOTATION or basename in dynamic_annotations:
            return True
    return False


def _is_imperative_shell(node: cst.FunctionDef, dynamic_annotations: frozenset[str]) -> bool:
    """True if the function is in the imperative shell (ASP202 applies).

    Shell iff it performs I/O (``_find_io_calls`` — the ASP205/206
    signal) OR ingests dynamically-typed / untrusted data
    (``_has_untrusted_param``). A pure, fully-typed function is the
    functional core and returns ``False`` (exempt). This composes the
    existing FC/IS boundary with the type system rather than inventing a
    new heuristic.
    """
    if _find_io_calls(node.body):
        return True
    return _has_untrusted_param(node, dynamic_annotations)


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
            "class Foo:\n    data: list[int] = []\n"  # class-level, not module-level
        ),
        Valid(
            "def foo():\n    cache = {}\n"  # local, not global
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
        Valid("for i in range(10):\n    print(i)\n"),
        Valid("while True:\n    data = read()\n    if not data:\n        break\n"),
        Valid("count = 0\nwhile count < 100:\n    count += 1\n"),
    ]
    INVALID = [
        Invalid("while True:\n    process()\n"),
        Invalid("while condition:\n    process()\n"),
    ]

    def visit_While(self, node: cst.While) -> None:
        if self._has_break(node.body):
            return
        if self._has_counter_pattern(node):
            return
        self.report(node, self.MESSAGE)

    @staticmethod
    def _has_counter_pattern(node: cst.While) -> bool:
        """Heuristic: condition references a name that is modified in the body."""
        cond_names = _extract_names(node.test)
        if not cond_names:
            return False
        if not isinstance(node.body, cst.IndentedBlock):
            return False
        for stmt in node.body.body:
            if isinstance(stmt, cst.SimpleStatementLine):
                for item in stmt.body:
                    if isinstance(item, cst.AugAssign) and isinstance(item.target, cst.Name):
                        if item.target.value in cond_names:
                            return True
                    if isinstance(item, cst.Assign):
                        for target in item.targets:
                            if (
                                isinstance(target.target, cst.Name)
                                and target.target.value in cond_names
                            ):
                                return True
        return False

    @staticmethod
    def _has_break(body: cst.BaseSuite) -> bool:
        """Check if body contains a Break statement (not in nested loops)."""
        if not isinstance(body, cst.IndentedBlock):
            return False
        return _find_break_in_stmts(body.body)


def _find_break_in_stmts(stmts: Sequence[cst.BaseStatement]) -> bool:
    """Recursively search for break, skipping nested loops."""
    for stmt in stmts:
        if isinstance(stmt, cst.SimpleStatementLine):
            for item in stmt.body:
                if isinstance(item, cst.Break):
                    return True
        elif isinstance(stmt, cst.If):
            if isinstance(stmt.body, cst.IndentedBlock) and _find_break_in_stmts(stmt.body.body):
                return True
            orelse = stmt.orelse
            if isinstance(orelse, cst.Else) and isinstance(orelse.body, cst.IndentedBlock):
                if _find_break_in_stmts(orelse.body.body):
                    return True
            elif isinstance(orelse, cst.If):
                if _find_break_in_stmts((orelse,)):
                    return True
        elif isinstance(stmt, cst.While | cst.For):
            # Don't descend into nested loops — their breaks don't count
            pass
        elif isinstance(stmt, cst.Try | cst.TryStar):
            if isinstance(stmt.body, cst.IndentedBlock) and _find_break_in_stmts(stmt.body.body):
                return True
    return False


def _extract_names(node: cst.BaseExpression) -> set[str]:
    """Extract all Name references from an expression."""
    names: set[str] = set()
    if isinstance(node, cst.Name):
        names.add(node.value)
    elif isinstance(node, cst.Comparison):
        names.update(_extract_names(node.left))
        for target in node.comparisons:
            names.update(_extract_names(target.comparator))
    elif isinstance(node, cst.BooleanOperation):
        names.update(_extract_names(node.left))
        names.update(_extract_names(node.right))
    elif isinstance(node, cst.UnaryOperation):
        names.update(_extract_names(node.expression))
    return names


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


def _find_io_calls(body: cst.BaseSuite) -> set[str]:
    """Find calls to known I/O functions in a function body."""
    from aspergillus.io_blocklist import IO_FUNCTIONS, IO_METHOD_NAMES

    found: set[str] = set()
    if not isinstance(body, cst.IndentedBlock):
        return found
    _walk_for_io_calls(body, found, IO_FUNCTIONS, IO_METHOD_NAMES)
    return found


# pandas `DataFrame.rename` / `Series.rename` keyword arguments. A bare
# `.rename(...)` carrying any of these is a pure in-memory pandas transform,
# NOT a filesystem rename (asp-108). `pathlib.Path.rename(target)` takes a
# single positional `target` and none of these.
_PANDAS_RENAME_KWARGS: frozenset[str] = frozenset(
    {"columns", "index", "mapper", "axis", "inplace", "level", "errors", "copy"}
)


def _is_pandas_rename(node: cst.Call) -> bool:
    """True for a pandas `DataFrame`/`Series.rename(...)` (pure), not a
    filesystem `Path.rename(target)` (I/O).

    Two by-shape signals distinguish the pure pandas transform from a
    filesystem rename without type resolution (asp-108):

    - a pandas-`rename` keyword argument (``columns=`` / ``index=`` /
      ``mapper=`` / ``axis=`` …); ``Path.rename`` takes only a positional
      ``target``; OR
    - a COMPUTED receiver — ``(np.log(a) - b).rename("spread")``,
      ``(s / sd).rename("z")`` — you cannot filesystem-rename the result of
      an arithmetic / chained expression; ``Path.rename`` is called on a
      name or attribute (``p.rename(...)`` / ``self.path.rename(...)``).

    The residual ambiguous case — ``s.rename("x")`` on a simple Series name
    with a single positional — is indistinguishable from ``p.rename(target)``
    by shape alone and is left matching (conservative: a real rename is not
    silently dropped).
    """
    if not isinstance(node.func, cst.Attribute):
        return False
    for arg in node.args:
        if arg.keyword is not None and arg.keyword.value in _PANDAS_RENAME_KWARGS:
            return True
    receiver = node.func.value
    return not isinstance(receiver, cst.Name | cst.Attribute)


def _walk_for_io_calls(
    node: cst.CSTNode,
    found: set[str],
    io_functions: frozenset[str],
    io_method_names: frozenset[str],
) -> None:
    """Recursively walk CST looking for Call nodes to I/O functions."""
    if isinstance(node, cst.Call):
        name = _resolve_call_name(node.func)
        if name and name in io_functions:
            found.add(name)
        # Match bare method names on untyped receivers:
        # `path_obj.read_text()` → Attribute(attr=Name("read_text"))
        elif isinstance(node.func, cst.Attribute):
            method_name = node.func.attr.value
            # `rename` collides with pandas DataFrame/Series.rename, a pure
            # in-memory transform — exclude those shapes (asp-108).
            if method_name in io_method_names and not (
                method_name == "rename" and _is_pandas_rename(node)
            ):
                found.add(method_name)
    for child in node.children:
        if isinstance(child, cst.CSTNode):
            _walk_for_io_calls(child, found, io_functions, io_method_names)


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
        # asp-108: pandas DataFrame.rename(columns=...) is a pure in-memory
        # transform, NOT filesystem I/O — the `columns=` kwarg distinguishes
        # it from `Path.rename(target)`.
        Valid(
            "def normalize_df(df: object) -> object:\n"
            "    renamed = df.rename(columns={'old': 'new'})\n"
            "    return renamed\n"
        ),
        # asp-108: Series.rename on a COMPUTED receiver (arithmetic result)
        # is pure — you cannot filesystem-rename an expression result.
        Valid(
            "def label_spread(a: object, b: object) -> object:\n"
            "    spread = (a - b).rename('spread')\n"
            "    return spread\n"
        ),
    ]
    INVALID = [
        Invalid(
            "def save(data: str) -> None:\n"
            "    assert data\n"
            "    assert isinstance(data, str)\n"
            "    print(data)\n"
        ),
        Invalid(
            "def load(path: object) -> str:\n"
            "    assert path is not None\n"
            "    assert hasattr(path, 'read_text')\n"
            "    return path.read_text()\n",
        ),
        # asp-108: a filesystem `Path.rename(target)` — simple-name receiver,
        # single positional, no pandas kwarg — STILL counts as I/O.
        Invalid(
            "def move(p: object, q: object) -> None:\n"
            "    assert p is not None\n"
            "    assert q is not None\n"
            "    p.rename(q)\n"
        ),
    ]

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        io_calls = _find_io_calls(node.body)
        if io_calls:
            self.report(
                node,
                self.MESSAGE.format(calls=", ".join(sorted(io_calls))),
            )


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

    MESSAGE = (
        "ASP206: Function mixes I/O ({io_calls}) with {logic_count} logic statements"
        " — consider functional core / imperative shell"
    )
    LOGIC_THRESHOLD = 3
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    VALID = [
        Valid("def orchestrator():\n    data = fetch()\n    save(data)\n    return data\n"),
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
            "    data = urllib.request.urlopen(url)\n"
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
        io_calls = _find_io_calls(node.body)
        if not io_calls:
            return

        logic_count = self._count_logic_statements(node.body)
        if logic_count > self.LOGIC_THRESHOLD:
            self.report(
                node,
                self.MESSAGE.format(
                    io_calls=", ".join(sorted(io_calls)),
                    logic_count=logic_count,
                ),
            )

    @staticmethod
    def _count_logic_statements(body: cst.BaseSuite) -> int:
        """Count non-trivial logic statements (assignments, returns, ifs, loops)."""
        count = 0
        if isinstance(body, cst.IndentedBlock):
            for stmt in body.body:
                if isinstance(stmt, cst.SimpleStatementLine):
                    for item in stmt.body:
                        if isinstance(
                            item,
                            cst.Assign | cst.AnnAssign | cst.AugAssign | cst.Return | cst.Assert,
                        ):
                            count += 1
                elif isinstance(stmt, cst.If | cst.For | cst.While):
                    count += 1
        return count
