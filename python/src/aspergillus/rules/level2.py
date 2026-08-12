"""NASA Level 2 rules: pure functions + immutability."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import partial

import libcst as cst
from fixit import Invalid, LintRule, Valid

_PositionOf = Callable[[cst.CSTNode], cst.metadata.CodeRange]


def positions_of(rule: LintRule) -> _PositionOf:
    """``rule``'s ``PositionProvider`` lookup, as a plain position function.

    Lets the line-counting helpers below stay pure functions of a node
    plus a position oracle — unit-testable without a fixit rule instance —
    while each rule binds its own metadata resolver once per visit.
    """
    return partial(rule.get_metadata, cst.metadata.PositionProvider)


def _noncode_line_numbers(node: cst.CSTNode, position_of: _PositionOf) -> set[int]:
    """Physical line numbers inside ``node``'s span that carry no code.

    Blank lines and comment-only lines are ``EmptyLine`` nodes in libcst;
    a trailing comment on a code line is ``TrailingWhitespace`` and is
    deliberately NOT one, so an annotated statement still counts as code.
    A docstring — any bare string-expression statement, at any depth in
    the span — is prose that happens to be a string EXPRESSION, so every
    physical line it occupies is excluded as well.
    """
    span = position_of(node)
    skip: set[int] = set()
    for descendant in _iter_all_nodes(node):
        if isinstance(descendant, cst.EmptyLine):
            skip.add(position_of(descendant).start.line)
        elif isinstance(descendant, cst.SimpleStatementLine) and len(descendant.body) == 1:
            item = descendant.body[0]
            if isinstance(item, cst.Expr) and isinstance(item.value, cst.BaseString):
                string_span = position_of(item.value)
                skip.update(range(string_span.start.line, string_span.end.line + 1))
    return {line for line in skip if span.start.line <= line <= span.end.line}


def _iter_all_nodes(node: cst.CSTNode) -> list[cst.CSTNode]:
    """``node`` and every descendant, nested functions included."""
    found: list[cst.CSTNode] = [node]
    for child in node.children:
        if isinstance(child, cst.CSTNode):
            found.extend(_iter_all_nodes(child))
    return found


def code_line_count(node: cst.CSTNode, position_of: _PositionOf) -> int:
    """Physical lines in ``node``'s span that carry code.

    The length measure for ASP201 and for ASP202's triviality exemption.
    It is the same measure ``duplicates.n_code_lines`` already applies to
    a function's span, and for the same reason recorded there: a raw span
    makes the verdict depend on how a function is DOCUMENTED rather than
    on what it does, so relocating a docstring or deleting an explanatory
    comment moves a length verdict without changing one line of behaviour.
    A gate that shortens a function by deleting its explanation has the
    incentive backwards.
    """
    span = position_of(node)
    return (span.end.line - span.start.line + 1) - len(_noncode_line_numbers(node, position_of))


class FunctionTooLong(LintRule):
    """ASP201: Functions must fit on one page (<=60 CODE lines).

    NASA Power of 10 Rule #4: Functions should fit on a single
    printed page. This improves readability and testability.

    The measure is CODE lines — the span minus its blank lines,
    comment-only lines and docstrings (``code_line_count``) — not the
    raw physical span. ``duplicates.n_code_lines`` already made exactly
    this correction for the duplicate-group floor, with the argument
    that a span "counts the docstring, which made the verdict depend on
    how a function is DOCUMENTED, not on what it does"; ASP201 measures
    the same property of the same node and owes the same answer.

    Measured on exophial's src + tests, which documents in the literate
    style: 24 functions exceeded 60 raw span lines, 3 exceeded 60 code
    lines. ``Dispatcher.__init__`` spans 139 lines of which 53 are code;
    ``ops.intake.generate_spec`` spans 125 of which 59 are code. Under
    the raw span the only way to pass is to delete the explanation,
    which is the incentive backwards.
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
        # 40 code lines carrying 40 lines of explanation: documenting a
        # function is not lengthening it.
        Valid(
            "def documented():\n"
            + "".join(f"    # explain x{i}\n    x{i} = {i}\n" for i in range(40))
            + "    return x0\n"
        ),
        # A long docstring does not make a two-statement function long.
        Valid(
            "def prose():\n"
            + '    """\n'
            + "".join(f"    line {i}\n" for i in range(80))
            + '    """\n'
            + "    return 1\n"
        ),
    ]
    INVALID = [
        Invalid(
            "def too_long():\n"
            + "".join(f"    x{i} = {i}\n" for i in range(61))
            + "    return x0\n"
        ),
        # Comments do not rescue a function that is genuinely too long.
        Invalid(
            "def too_long_documented():\n"
            + "".join(f"    # explain x{i}\n    x{i} = {i}\n" for i in range(61))
            + "    return x0\n"
        ),
    ]

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        line_count = code_line_count(node, positions_of(self))
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
        # Triviality is measured in CODE lines: a two-statement boundary
        # reader stays exempt however long its docstring is. Under the
        # raw span it lost the exemption for being documented, and its
        # only passing form was to delete the prose.
        Valid(
            "def read_config(path: str) -> str:\n"
            '    """Read the config file.\n'
            "\n"
            "    Long-form prose about where this file comes from, who\n"
            "    writes it, and why the read is unguarded here.\n"
            '    """\n'
            "    with open(path) as handle:\n"
            "        return handle.read()\n"
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

        # Triviality exemption measured in CODE lines, the same measure
        # ASP201 uses: a two-statement reader with a ten-line docstring
        # is trivial, and a raw span made it lose this exemption for
        # being documented.
        if code_line_count(node, positions_of(self)) <= self.MIN_LINES_FOR_RULE:
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
        # The counter drives the condition through a call. Same loop as
        # `while parts != PurePosixPath('.')`, same exemption.
        Valid('while str(parts) != ".":\n    parts = parts.parent\n'),
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
    """Extract all Name references from an expression.

    Recurses through a ``Call``'s arguments: ``while str(parts) != "."`` is
    the same loop as ``while parts != PurePosixPath(".")`` and the same
    ``parts`` drives it, but without this the argument was invisible, the
    name set came back empty, and ASP204's counter-pattern exemption
    short-circuited to "unbounded" for a loop whose counter it was looking
    straight at.
    """
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
    elif isinstance(node, cst.Call):
        for arg in node.args:
            names.update(_extract_names(arg.value))
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
    """Find calls to known I/O functions in a function's OWN body.

    The unit of analysis is one function, not one function plus every
    function nested inside it. ``_count_assertions`` already states that
    convention ("not descending into nested function/lambda bodies —
    those are visited as their own units"), and every rule reached from
    here — ASP202's shell predicate, ASP205, ASP206 — reports per
    ``visit_FunctionDef``, which fires for the nested def in its own
    right.

    Descending made a factory impure for the I/O its product performs::

        def make_logger(prefix: str) -> Callable[[str], None]:
            def emit(line: str) -> None:
                print(prefix, line)
            return emit

    ``make_logger`` prints nothing when called, yet was reported as
    calling ``print`` — and ``emit`` was reported for the same ``print``,
    so one I/O site produced two findings. Its only passing form was to
    lift ``emit`` to module scope, which a closure over ``prefix``
    forbids: a finding with no legal passing form. ASP206 was
    incoherent for the same reason — it sourced ``io_calls`` from any
    depth while counting logic statements only at the outer body's top
    level, so its two halves measured different functions.
    """
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
    """Recursively walk CST looking for Call nodes to I/O functions.

    Stops at a nested ``FunctionDef`` / ``Lambda``: that body belongs to
    its own function, which is visited separately (see ``_find_io_calls``).
    """
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
        if isinstance(child, cst.FunctionDef | cst.Lambda):
            continue
        if isinstance(child, cst.CSTNode):
            _walk_for_io_calls(child, found, io_functions, io_method_names)


# ASP205 (ImpureFunction) — RETIRED for Python (pebble exo-asp205, this change).
#
# ASP205 reported every function whose body called a name in
# `io_blocklist.py`. Its stated basis was "NASA Level 2: 70%+ of
# functions should be pure", and its own docstring conceded the verdict:
# "The function is not necessarily wrong — orchestrator/shell functions
# are expected to do I/O."
#
# Two defects, each fatal on its own.
#
# 1. IT REPORTED THE WRONG UNIT. Its criterion is a CORPUS RATIO — what
#    share of the program's functions are pure. Its report was PER
#    FUNCTION. A fixit rule sees one file and cannot compute a ratio, so
#    the rule substituted "this function does I/O" for "too little of
#    this program is pure". Those are different claims. The ratio is now
#    measured where it can be measured, by the corpus command
#    `aspergillus purity-ratio` (see `__main__.py`), which reports the
#    NASA Level-2 70% target as a project-wide number and exits non-zero
#    when the target is missed. On the exophial corpus that target was
#    already met by a wide margin while ASP205 still emitted 297
#    findings: 298 of 2918 functions in src/exophial call a blocklist
#    name, so 89.8% are pure against a 70% floor.
#
# 2. IT HAD NO LEGAL PASSING FORM. A boundary function exists in order
#    to perform its effect. The only edit that clears the finding is to
#    delete the effect, which deletes the function. `_find_io_calls`
#    already states this test in its own docstring, for the nested-def
#    case it fixed: "a finding with no legal passing form". exophial's
#    src carries 361 `# lint-ignore: ImpureFunction` directive lines for
#    233 functions — and 126 of those lines suppress NOTHING, because
#    the author added them by pattern rather than by measurement. A rule
#    that teaches its users to suppress it blind has stopped informing
#    anyone.
#
# THE LITERATURE DOES NOT SUPPORT THE PER-FUNCTION FORM. Every system
# that separates effect from computation TRACKS the effect and lets the
# effectful expression compute:
#
#   - Lucassen & Gifford, "Polymorphic Effect Systems", POPL 1988,
#     doi:10.1145/73560.73564. The effect is part of the type and is
#     computed for every expression. The paper's own polymorphism
#     showcase, `mapcar`, has effect `(MAXEFF (ALLOC r) (READ r) e)` and
#     a body that branches and recurses. The system's ONE restriction is
#     on generalisation, "by limiting polymorphism to expressions
#     without side-effects" — not on control flow.
#   - Peyton Jones & Wadler, "Imperative Functional Programming",
#     POPL 1993, doi:10.1145/158511.158524. "the style in which one
#     writes the functional program's internal computation is
#     unaffected."
#   - Leijen, "Koka: Programming with Row-polymorphic Effect Types",
#     arXiv:1406.2061, 2014. Its opening example is typed
#     `int -> io int` and computes: "there was no need to change the
#     original function nor to promote the expression x*x into the io
#     effect."
#
# So the effect literature licenses a rule that MARKS an effect. It
# licenses no rule that forbids the marked function from computing.
#
# WHAT STILL COVERS THE GROUND. Nothing safety-relevant is uncovered.
# `_find_io_calls` — ASP205's whole mechanism — stays live and keeps two
# consumers: ASP202's imperative-shell predicate (`_is_imperative_shell`,
# which decides where NASA Rule #5's assertion requirement applies) and
# ASP206's gate (which decides where the mixing check applies). The
# corpus ratio moves to `aspergillus purity-ratio`. The per-function
# verdict, the only thing removed, was the part the rule's own docstring
# disclaimed.
#
# STAYS IN FORCE ELSEWHERE. This retirement is scoped to Python, exactly
# as asp-80c scoped ASP301's. A language whose type system carries the
# effect — Haskell's `IO`, Koka's `io`, an ML region-and-effect
# annotation — states the same fact in the type, where it is checked
# rather than reported. Python has no effect type; a per-function lint
# was the wrong substitute for one, not a weaker version of one.


# Expression nodes that COMPUTE rather than move a value.
_COMPUTING_NODES = (
    cst.BinaryOperation,
    cst.UnaryOperation,
    cst.Comparison,
    cst.BooleanOperation,
    cst.IfExp,
    cst.ListComp,
    cst.SetComp,
    cst.DictComp,
    cst.GeneratorExp,
)


def _iter_own_nodes(node: cst.CSTNode) -> list[cst.CSTNode]:
    """Every descendant of ``node`` in the SAME function.

    A nested ``def`` / ``lambda`` / ``class`` is its own unit of
    analysis, the convention ``_find_io_calls`` states and every rule
    reached from here shares.
    """
    out: list[cst.CSTNode] = []
    stack = [node]
    while stack:
        current = stack.pop()
        for child in current.children:
            if isinstance(child, cst.FunctionDef | cst.Lambda | cst.ClassDef):
                continue
            out.append(child)
            stack.append(child)
    return out


def _derived_names(body: cst.BaseSuite) -> frozenset[str]:
    """Names the function BINDS itself — the results it derived.

    A parameter, a module attribute and a literal are INPUTS: the shell
    receives them and feeds them to its effects. A name the function
    assigned is a value the function produced. Computing over an input is
    argument construction; computing over a derived value is logic. That
    definition-use distinction is what separates
    ``os.open(p, os.O_RDWR | os.O_CREAT)`` — a POSIX flag word built from
    two module constants — from ``result = int(avg * 100)``, where ``avg``
    is a value this function computed two lines earlier. Both are
    arithmetic in call-argument position, so no purely syntactic test
    tells them apart; the binding does.
    """
    names: set[str] = set()
    for node in _iter_own_nodes(body):
        if isinstance(node, cst.Assign):
            for target in node.targets:
                names.update(_extract_names(target.target))
        elif isinstance(node, cst.AnnAssign | cst.AugAssign):
            names.update(_extract_names(node.target))
        elif isinstance(node, cst.NamedExpr):
            names.update(_extract_names(node.target))
        elif isinstance(node, cst.For):
            names.update(_extract_names(node.target))
        elif isinstance(node, cst.AsName):
            if isinstance(node.name, cst.Name | cst.Tuple | cst.List):
                names.update(_extract_names(node.name))
    return frozenset(names)


def _computes_on_derived(node: cst.CSTNode, derived: frozenset[str]) -> bool:
    """True if ``node`` computes over a value the function derived itself.

    See ``_derived_names`` for why the test is definition-use rather than
    syntactic.
    """
    for candidate in [node, *_iter_own_nodes(node)]:
        if not isinstance(candidate, _COMPUTING_NODES):
            continue
        referenced = set()
        for inner in [candidate, *_iter_own_nodes(candidate)]:
            if isinstance(inner, cst.Name):
                referenced.add(inner.value)
        if referenced & derived:
            return True
    return False


def _is_effect_error_report(stmt: cst.BaseStatement) -> bool:
    """True if ``stmt`` is an effect's own failure report, not logic.

    Shape: ``if <test>: raise ...`` with no ``else`` and nothing in the
    body but ``raise``. A subprocess's return code, an HTTP status and an
    ``errno`` are how the effect ANSWERS; converting that answer into an
    exception is part of performing the effect, not business logic laid
    on top of it. Cockburn's adapter is required to keep business logic
    out, and reporting the boundary's own failure is not business logic
    (Cockburn, "Hexagonal (Ports & Adapters) Architecture", HaT TR
    2005.02, https://alistair.cockburn.us/hexagonal-architecture/).

    The closest existing art agrees by construction:
    ``eslint-plugin-functional``'s ``no-conditional-statements`` ships
    ``allowReturningBranches: true`` in its recommended preset, for
    exactly the ``if (error) { return; }`` shape
    (https://github.com/eslint-functional/eslint-plugin-functional).

    Measured on exophial: this one exemption clears
    ``realize._run_git`` (``subprocess.run`` then
    ``if result.returncode != 0: raise``), which carried a
    ``lint-ignore`` for a finding it should never have received.
    """
    if not isinstance(stmt, cst.If) or stmt.orelse is not None:
        return False
    body = stmt.body
    if not isinstance(body, cst.IndentedBlock):
        return False
    raises: list[cst.BaseSmallStatement] = []
    for line in body.body:
        if not isinstance(line, cst.SimpleStatementLine):
            return False
        raises.extend(line.body)
    return bool(raises) and all(isinstance(item, cst.Raise) for item in raises)


class MixedIOAndLogic(LintRule):
    """ASP206: Function mixes I/O with non-trivial logic.

    The functional core / imperative shell pattern separates pure
    business logic from I/O (Gary Bernhardt, "Boundaries", 2012,
    https://www.destroyallsoftware.com/talks/boundaries). This rule
    flags a function that does both: it calls I/O (``_find_io_calls``,
    the ``io_blocklist`` signal) AND computes enough beside the I/O to
    show that business logic sits in the boundary. Cockburn states the
    same constraint for an adapter: "the entanglement between the
    business logic and the interaction with external entities" is the
    error to remove (Cockburn, "Hexagonal (Ports & Adapters)
    Architecture", HaT TR 2005.02, 2005,
    https://alistair.cockburn.us/hexagonal-architecture/).

    Threshold: I/O calls AND more than ``LOGIC_THRESHOLD`` statements
    that COMPUTE. Three statement classes are not counted, each for a
    stated reason:

    - **an assertion.** ASP202 REQUIRES at least two assertions on every
      imperative-shell function — which, by ``_is_imperative_shell``, is
      every function ASP206 examines. Counting a statement one rule
      mandates against a three-statement ceiling another rule imposes
      left one statement of headroom for the whole boundary, so the pair
      had no common satisfying form. NASA Power of 10 Rule #5 asks for
      the assertions; ASP206 must not charge for them.
    - **value threading** — ``x = call(...)``, ``return x``,
      ``return call(...)`` (``_threads_a_value``). The docstring below
      promised orchestrators pass; before this change they did not. An
      orchestrator threading four effects scored 4 assignments plus a
      return and fired, and no edit fixed it: the ``VALID`` example
      here passes on exactly three statements and fires on a fourth
      effect. That is a finding with no legal passing form, the same
      defect ``_find_io_calls`` records for the nested-def case.
    - **the effect's own error report** — ``if <test>: raise ...``
      (``_is_effect_error_report``).

    WHAT THIS RULE IS NOT. It is not "an effectful function may not
    compute". That stricter, structural form was proposed and is
    REFUTED, by the literature and by measurement:

    - Alexis King's recommended boundary function reads an environment
      variable, splits the string and branches on the parse
      ("Parse, don't validate", 2019,
      https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/).
      A parser IS logic: "a parser is just a function that consumes
      less-structured input and produces more-structured output."
      Read-then-parse is the largest class of boundary function here,
      and the strict form rejects King's own exemplar.
    - Cockburn's own published adapter contains three ``if`` statements.
      Martin's Dependency Rule governs the DIRECTION of a dependency,
      not the shape of a function ("The Clean Architecture", 2012,
      https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html).
    - Every effect system quoted in the ASP205 retirement note above
      lets an effectful expression compute.
    - Measured on exophial's src: the strict form fires on 242 of the
      298 I/O-bearing functions (81%), and still fires on
      ``realize._observe_claim_lease`` — a flock probe cited as a false
      positive — because ``os.O_RDWR | os.O_CREAT`` and
      ``fcntl.LOCK_EX | fcntl.LOCK_NB`` are arithmetic in syntax and
      POSIX flag words in meaning.

    - Bernhardt's own shell is not conditional-free. In the talk, at
      29:36: "The only conditional in the shell is the case statement
      that we saw that was choosing between keys." His screencast page
      says the design "leads to an imperative shell with FEW
      conditionals" — few, and as a consequence, not none as a
      constraint.

    IT IS ALSO NOT COMMAND-QUERY SEPARATION, and it must not borrow
    CQS's authority. CQS says a value-returning function has no effect
    (Meyer, ADFOCS 2003 Lecture 1, slide 26: "This principle excludes
    many common schemes, such as using functions for input (e.g. C's
    ``getint`` or equivalent)"; ECMA-367 2nd ed. 2006 §8.5.11, Meyer
    editing: "A command is a procedure"). This rule PERMITS an effectful
    function to return a value, because threading the effect's result
    out is how a shell function is useful. That is the exact construct
    Meyer excludes, so the rule takes the side CQS's critics defended.
    The usual ``stack.pop()`` objection to CQS therefore does not apply
    here: this rule already concedes what that objection demands.
    Eiffel's own CQS lint rule, CA004, likewise constrains only what a
    value-returning function may CALL, never whether it may branch.

    The closest NAMED relative is the Humble Object pattern (Feathers,
    "The Humble Dialog Box", Object Mentor, 2002; Meszaros, "Humble
    Object", xunitpatterns.com), whose criterion is "so simple that we
    often don't bother writing tests for it". That is testability, not
    syntax, and Feathers' own untested humble dialog contains a ``for``
    loop. Treat this rule as a decidable proxy for the Humble Object
    property, not as a statement any of these authors made.

    WHY THE THRESHOLD IS 3. It is anchored, not tuned. Cockburn's
    published adapter, ``MockRateRepository.getRate``, has exactly three
    ``if`` statements and is presented as the pattern with no caveat, so
    three is the largest count the cited exemplar requires to pass. A
    fourth logic statement is past every published example of a boundary
    in this tradition.

    ``_is_imperative_shell`` is deliberately NOT consulted here. It
    returns ``True`` whenever ``_find_io_calls`` is non-empty, which is
    already this rule's gate, so the call would be a no-op — the same
    circularity that made it useless to ASP205. It earns its keep in
    ASP202 alone, where the ``_has_untrusted_param`` disjunct reaches a
    population ``_find_io_calls`` does not: measured on exophial's src,
    393 functions are in ASP202's scope against 298 I/O-bearing ones.
    """

    MESSAGE = (
        "ASP206: Function mixes I/O ({io_calls}) with {logic_count} computing statements"
        " — consider functional core / imperative shell"
    )
    LOGIC_THRESHOLD = 3
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    VALID = [
        Valid("def orchestrator():\n    data = fetch()\n    save(data)\n    return data\n"),
        # The same orchestrator threading FIVE effects. Before the
        # value-threading exemption this fired at 6 counted statements and
        # had no passing form, contradicting the docstring's promise.
        Valid(
            "def orchestrate_more():\n"
            "    a = fetch()\n"
            "    b = enrich(a)\n"
            "    c = shape(b)\n"
            "    print(c)\n"
            "    d = persist(c)\n"
            "    return d\n"
        ),
        Valid(
            "def pure_logic(items: list) -> int:\n"
            "    assert len(items) > 0\n"
            "    assert all(x > 0 for x in items)\n"
            "    total = sum(items)\n"
            "    avg = total / len(items)\n"
            "    return int(avg)\n"
        ),
        # Same unit-of-analysis rule ``_find_io_calls`` states: the
        # enclosing factory is not mixing I/O with logic — its product
        # does the I/O.
        Valid(
            "def make_writer(prefix: str):\n"
            "    tag = prefix.strip()\n"
            "    upper = tag.upper()\n"
            "    width = len(upper)\n"
            "    return lambda line: print(upper, width, line)\n"
        ),
        # REAL CODE, src/exophial/realize.py:269 `_run_git` — a subprocess
        # boundary whose only branch raises on the return code. It carried a
        # `# lint-ignore: MixedIOAndLogic` for a finding it should never have
        # received: two ASP202-mandated asserts + one threading assignment +
        # the effect's own error report + one threading return.
        Valid(
            "def _run_git(cwd: Path, *args: str) -> str:\n"
            '    assert cwd, "_run_git needs a real cwd"\n'
            '    assert args, "_run_git needs at least one git argument"\n'
            "    result = subprocess.run(\n"
            '        ["git", "-C", str(cwd), *args], capture_output=True, text=True\n'
            "    )\n"
            "    if result.returncode != 0:\n"
            '        raise RuntimeError(f"git failed in {cwd}: {result.stderr}")\n'
            "    return result.stdout.strip()\n"
        ),
        # REAL CODE, src/exophial/realize.py:418 `_observe_claim_lease` — a
        # non-blocking flock probe. The two `|` expressions are POSIX flag
        # words in argument position, and the try/except IS the probe's
        # held-vs-not-held answer.
        Valid(
            "def _observe_claim_lease(repo: Path, pebble_id: str) -> str:\n"
            '    assert repo, "needs a bus root"\n'
            '    assert pebble_id, "needs a non-empty pebble id"\n'
            "    lock_path = bus.lock_path(repo, PebbleId(pebble_id))\n"
            "    lock_path.parent.mkdir(parents=True, exist_ok=True)\n"
            "    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)\n"
            "    try:\n"
            "        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
            "    except OSError:\n"
            '        return "held"\n'
            "    else:\n"
            "        fcntl.flock(fd, fcntl.LOCK_UN)\n"
            '        return "not_held"\n'
            "    finally:\n"
            "        os.close(fd)\n"
        ),
    ]
    INVALID = [
        # REAL CODE, src/exophial/odc.py:151 `read_odc_close` (abridged to the
        # shape that fires; the real body is 36 lines). It shells out to `pb`,
        # then scans every comment for the last ODC marker and reshapes it.
        # The scan is a pure fold over a list the effect already returned, so
        # the split is mechanical: keep the `subprocess.run` here, move the
        # scan to a `_latest_odc_marker(comments)` core.
        Invalid(
            "def read_odc_close(repo: Path, pebble_id: str) -> dict[str, str] | None:\n"
            '    assert pebble_id, "reading ODC fields needs the pebble id"\n'
            "    proc = subprocess.run(\n"
            '        ["pb", "show", "--json", pebble_id], capture_output=True, text=True\n'
            "    )\n"
            "    if proc.returncode != 0:\n"
            "        return None\n"
            "    data = json.loads(proc.stdout)\n"
            "    if not isinstance(data, dict):\n"
            "        return None\n"
            '    comments = data.get("comments") or []\n'
            "    fields: dict[str, str] | None = None\n"
            "    for comment in comments:\n"
            '        body = comment.get("body", "")\n'
            "        if not body.startswith(_ODC_MARKER_PREFIX):\n"
            "            continue\n"
            "        fields = {str(k): str(v) for k, v in json.loads(body).items()}\n"
            "    return fields\n"
        ),
        # REAL CODE, src/exophial/generators/generate_domain_types.py:203
        # `load_declarations` (abridged). Read-then-parse-then-classify is the
        # largest class of mixed function in this corpus: the glob and the
        # `read_text` are the effect, and the discriminator that decides which
        # declaration is a machine is a pure fold over the parsed values.
        Invalid(
            "def load_declarations() -> dict[str, dict[str, Any]]:\n"
            "    machines: dict[str, dict[str, Any]] = {}\n"
            "    skipped: list[str] = []\n"
            '    for path in sorted(DECL_DIR.glob("*.json")):\n'
            '        decl = json.loads(path.read_text(encoding="utf-8"))\n'
            '        if not isinstance(decl, dict) or not isinstance(decl.get("aspects"), list):\n'
            "            continue\n"
            '        if "decision_invariants" not in decl:\n'
            "            skipped.append(path.name)\n"
            "            continue\n"
            "        machines[path.name] = decl\n"
            "    if FIRST_DECLARATION not in machines:\n"
            '        raise SystemExit(f"{FIRST_DECLARATION} is missing")\n'
            "    for name in skipped:\n"
            '        print(f"  skipped {name}: no decision_invariants")\n'
            "    ordered = [FIRST_DECLARATION] + sorted(\n"
            "        n for n in machines if n != FIRST_DECLARATION\n"
            "    )\n"
            "    return {n: machines[n] for n in ordered}\n"
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
        """Count top-level statements that carry LOGIC.

        A statement carries logic when it computes over a value the
        function derived itself (``_derived_names``,
        ``_computes_on_derived``), or when it is control flow that is not
        the effect's own failure report (``_is_effect_error_report``). An
        assertion is never counted: ASP202 mandates two on every function
        this rule examines. See the class docstring for why each
        exemption removes a miscount rather than weakening the rule.
        """
        count = 0
        if not isinstance(body, cst.IndentedBlock):
            return count
        derived = _derived_names(body)
        for stmt in body.body:
            if isinstance(stmt, cst.SimpleStatementLine):
                for item in stmt.body:
                    if isinstance(item, cst.Assert):
                        continue
                    if isinstance(item, cst.AugAssign):
                        count += 1
                    elif _computes_on_derived(item, derived):
                        count += 1
            elif isinstance(stmt, cst.If | cst.For | cst.While | cst.Match):
                if not _is_effect_error_report(stmt):
                    count += 1
        return count
