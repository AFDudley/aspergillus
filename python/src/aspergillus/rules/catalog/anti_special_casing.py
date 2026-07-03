"""ASP408: Anti-special-casing — a gaming DETECTOR, not an oracle.

Flags implementation-code shapes that satisfy a known verification
oracle WITHOUT real behavior — the "special-casing" / Volkswagen
defeat-device class. It is a static sibling to ASP202 (assertion
density) in the verification-integrity family: where ASP202 asks
"does this function assert its contract," ASP408 asks "does this
function fake its contract by hardcoding the tested answer."

Motivation (exophial spec-oracle, pebble ``exo-e2f.5``; parent
``exo-e2f``): a single build->run->assert oracle is a rank-1 oracle —
one enumerable input/output pair. An agent iterating against it can
special-case that one input:

    def next_state(board, move):
        if move == "UP":                       # the one tested move
            return [[0, 0, 0], [0, 1, 0], ...]  # the expected board
        return board

The gate passes; no snake logic exists. Hidden tests do not fix this
against an iterating agent (each pass/fail bit leaks). The structural
tell, however, is visible in the source: a branch that matches a
specific literal input and returns a specific literal answer, or a
branch that reads a CI/test environment variable to change behavior
under test. This rule surfaces those two tells.

**Ships without autofix** (Tier 2 per
``docs/decisions/2026-05-19-mtm-past-warn-promotion-phase.md``). There
is no mechanical rewrite of a gaming stub into a correct implementation
— the fix is to write the real behavior — so per aspergillus's engine
routing (``docs/design.md`` §"How an engine gets chosen") this is a
fixit/LibCST detection rule, NOT an ast-grep rewrite rule. The
developer/reviewer accepts the lint by replacing the hardcoded branch
with a real computation (or, for a genuine lookup table, by dismissing
the detection — hence detection-only, count-gated by the consumer's
pre-commit ratchet like ASP406/ASP407).

## Two detected shapes

1. **Hardcoded-answer branch** — ``if <x> == <literal>: return
   <literal>`` where BOTH the compared value and the returned value are
   *non-trivial* literals. "Non-trivial" excludes guard-clause
   sentinels (``None``/``True``/``False``, ``0``/``1``, ``""``, empty
   collections) on either side, so ordinary precondition guards
   (``if n == 0: return None``) do NOT trigger. The tell is a specific
   input literal mapped to a specific output literal — the shape of a
   memorised oracle answer, not a computation.

2. **Test/CI-environment defeat device** — reading a known CI/test
   environment variable (``os.getenv("CI")``, ``os.environ["PYTEST_
   CURRENT_TEST"]``, ``"CI" in os.environ``) in implementation code.
   Behaviour that changes under test is the Volkswagen shape; real
   implementation code has no reason to read these markers.

## Scope / limitations (honest)

The pebble's acceptance also names "an equality-branch on a literal
that ALSO APPEARS AS A DECLARED TEST INPUT" and "return matching an
EXPECTED ORACLE VALUE." That literal-appears-in-the-test correlation is
a *cross-file* fact (implementation file vs. test/spec file) that a
single-file CST rule cannot see. This rule detects the single-file
proxy that the correlation reduces to in the source: a non-trivial
literal input mapped to a non-trivial literal output. The cross-file
correlation (matching the branch literal against the spec's declared
inputs) belongs to the spec-oracle runner (``scripts/spec_oracle.py``),
which HAS both artifacts; this rule is the static first line that needs
no oracle at all.

Refs: ``aspergillus/docs/design.md`` §"Multi-engine architecture";
pebble ``exo-e2f.5`` / parent ``exo-e2f`` (2026-07-03 reframe: static/
AST anti-special-casing is the routine-floor rung of the gaming-
resistance ladder — NOT mutation testing, which is rejected doctrine).
"""

from __future__ import annotations

import libcst as cst
from fixit import Invalid, LintRule, Valid

# CI/test environment markers whose presence in IMPLEMENTATION code is a
# defeat-device tell. All are unambiguous test/CI signals — an app has no
# legitimate reason to branch on them. Deliberately excludes generic keys
# (e.g. "TEST", "ENV") that an app might read for non-gaming reasons.
_TEST_ENV_VARS: frozenset[str] = frozenset(
    {
        "CI",
        "CONTINUOUS_INTEGRATION",
        "GITHUB_ACTIONS",
        "GITLAB_CI",
        "JENKINS_URL",
        "TRAVIS",
        "CIRCLECI",
        "BUILDKITE",
        "TF_BUILD",
        "APPVEYOR",
        "TEAMCITY_VERSION",
        "PYTEST_CURRENT_TEST",
        "TESTING",
        "TOX_ENV_NAME",
    }
)

_MSG_HARDCODED = (
    "ASP408: Hardcoded-answer branch — `if x == <literal>: return "
    "<literal>` maps a specific input literal to a specific output "
    "literal. This is the special-casing tell (a memorised oracle "
    "answer, not a computation). Compute the result, or remove the "
    "special case."
)
_MSG_ENV = (
    "ASP408: Implementation code branches on a CI/test environment "
    "variable — the Volkswagen defeat-device shape (behaviour changes "
    "under test). Remove the test-environment branch; production and "
    "test must run the same code path."
)


class AntiSpecialCasing(LintRule):
    """ASP408: gaming detector — hardcoded-answer branches and
    CI/test-env defeat devices in implementation code.

    Detection-only (no autofix): the fix is to write real behaviour.
    """

    MESSAGE = _MSG_HARDCODED

    VALID = [
        # Real computation from inputs — no literal-in/literal-out branch.
        Valid(
            "def next_state(board, move):\n"
            "    head = board[0]\n"
            "    dx, dy = move\n"
            "    new_head = (head[0] + dx, head[1] + dy)\n"
            "    return [new_head, *board[:-1]]\n"
        ),
        # Ordinary guard: return side is a trivial sentinel (None).
        Valid("def f(n):\n    if n == 42:\n        return None\n    return g(n)\n"),
        # Ordinary guard: compared side is a trivial boundary (0).
        Valid("def f(x):\n    if x == 0:\n        return compute(x)\n    return h(x)\n"),
        # Dispatch on a literal but the branch COMPUTES (returns a call),
        # not a hardcoded literal — legitimate.
        Valid(
            "def route(status):\n"
            '    if status == "active":\n'
            "        return build_profile(status)\n"
            "    return default()\n"
        ),
        # Reading a NON-test env var is normal configuration.
        Valid('def cfg():\n    return os.getenv("DATABASE_URL")\n'),
        # Comparing to None (identity-ish guard) — trivial both ways.
        Valid("def f(x):\n    if x == None:\n        return False\n    return True\n"),
    ]
    INVALID = [
        # The load-bearing snake-gaming stub: hardcoded board for the
        # one tested move.
        Invalid(
            "def next_state(board, move):\n"
            '    if move == "UP":\n'
            "        return [[0, 0, 0], [0, 1, 0], [0, 0, 0]]\n"
            "    return board\n"
        ),
        # One-liner branch form (SimpleStatementSuite), tuple input ->
        # list-literal answer.
        Invalid(
            "def step(board, move):\n"
            "    if move == (1, 0): return [[1, 0], [0, 0]]\n"
            "    return board\n"
        ),
        # Non-trivial number in, non-trivial string out.
        Invalid(
            'def lookup(code):\n    if code == 404:\n        return "canned"\n    return real(code)\n'
        ),
        # Defeat device: os.getenv on a CI marker.
        Invalid('def compute(x):\n    if os.getenv("CI"):\n        return 42\n    return x * x\n'),
        # Defeat device: os.environ subscript on a test marker.
        Invalid(
            'def compute(x):\n    marker = os.environ["PYTEST_CURRENT_TEST"]\n    return marker\n'
        ),
        # Defeat device: membership test against os.environ.
        Invalid('def compute(x):\n    if "CI" in os.environ:\n        return 0\n    return x\n'),
    ]

    def visit_If(self, node: cst.If) -> None:
        if not _eq_against_nontrivial_literal(node.test):
            return
        if _branch_returns_nontrivial_literal(node.body):
            self.report(node, _MSG_HARDCODED)

    def visit_Call(self, node: cst.Call) -> None:
        if _env_getter_key(node) in _TEST_ENV_VARS:
            self.report(node, _MSG_ENV)

    def visit_Subscript(self, node: cst.Subscript) -> None:
        if _environ_subscript_key(node) in _TEST_ENV_VARS:
            self.report(node, _MSG_ENV)

    def visit_Comparison(self, node: cst.Comparison) -> None:
        if _in_environ_key(node) in _TEST_ENV_VARS:
            self.report(node, _MSG_ENV)


# --- literal classification -------------------------------------------------


def _is_nontrivial_number(node: cst.BaseExpression) -> bool:
    """A numeric literal that is not a guard boundary (0 or 1)."""
    if isinstance(node, cst.Integer):
        try:
            return int(node.value, 0) not in (0, 1)
        except ValueError:
            return True
    return isinstance(node, (cst.Float, cst.Imaginary))


def _is_nontrivial_literal(node: cst.BaseExpression) -> bool:
    """True iff ``node`` is a *specific* constant answer/input — a
    non-empty string, a number other than 0/1, or a non-empty
    collection literal. Names (``None``/``True``/``False``/anything),
    f-strings, and empty/sentinel literals are trivial (return False)
    so ordinary guard clauses do not trip the rule.
    """
    if isinstance(node, (cst.Integer, cst.Float, cst.Imaginary)):
        return _is_nontrivial_number(node)
    if isinstance(node, cst.SimpleString):
        return node.evaluated_value not in ("", b"")
    if isinstance(node, cst.ConcatenatedString):
        value = node.evaluated_value
        return value is None or value not in ("", b"")
    if isinstance(node, (cst.List, cst.Tuple, cst.Set, cst.Dict)):
        return len(node.elements) > 0
    return False


# --- hardcoded-answer branch (detector A) -----------------------------------


def _eq_against_nontrivial_literal(test: cst.BaseExpression) -> bool:
    """True iff ``test`` is a single ``==`` comparison with a
    non-trivial literal on either side.
    """
    if not isinstance(test, cst.Comparison):
        return False
    if len(test.comparisons) != 1:
        return False
    target = test.comparisons[0]
    if not isinstance(target.operator, cst.Equal):
        return False
    return _is_nontrivial_literal(test.left) or _is_nontrivial_literal(target.comparator)


def _branch_returns_nontrivial_literal(body: cst.BaseSuite) -> bool:
    """True iff the immediate branch body contains ``return <literal>``
    with a non-trivial literal. Handles both the indented block and the
    one-line ``if x: return y`` suite; does not descend into nested
    compound statements.
    """
    small_stmts: list[cst.BaseSmallStatement] = []
    if isinstance(body, cst.IndentedBlock):
        for line in body.body:
            if isinstance(line, cst.SimpleStatementLine):
                small_stmts.extend(line.body)
    elif isinstance(body, cst.SimpleStatementSuite):
        small_stmts.extend(body.body)
    for stmt in small_stmts:
        if (
            isinstance(stmt, cst.Return)
            and stmt.value is not None
            and _is_nontrivial_literal(stmt.value)
        ):
            return True
    return False


# --- CI/test-env defeat device (detector B) ---------------------------------
#
# The key-extraction helpers return ``str`` (not ``str | None``): the empty
# string is the "no key here" sentinel. That is unambiguous — the empty
# string is never a valid environment-variable name and is never a member of
# ``_TEST_ENV_VARS`` — so callers test ``key in _TEST_ENV_VARS`` directly with
# no Optional in the return type (ASP302).


def _string_value(node: cst.BaseExpression) -> str:
    """The value of a plain string literal, or "" if ``node`` is not one."""
    if isinstance(node, cst.SimpleString):
        value = node.evaluated_value
        if isinstance(value, str):
            return value
    return ""


def _is_environ_ref(node: cst.BaseExpression) -> bool:
    """True iff ``node`` is ``os.environ`` or a bare ``environ``."""
    if isinstance(node, cst.Name):
        return node.value == "environ"
    if isinstance(node, cst.Attribute):
        return (
            isinstance(node.value, cst.Name)
            and node.value.value == "os"
            and node.attr.value == "environ"
        )
    return False


def _first_string_arg(call: cst.Call) -> str:
    """The first positional arg as a string literal, or "" if absent/non-string."""
    if not call.args:
        return ""
    first = call.args[0]
    if first.keyword is not None or first.star:
        return ""
    return _string_value(first.value)


def _env_getter_key(call: cst.Call) -> str:
    """The env-var key read by ``os.getenv(k)`` / ``getenv(k)`` /
    ``os.environ.get(k)`` / ``environ.get(k)``, or "" if this call is none.
    """
    func = call.func
    if isinstance(func, cst.Name) and func.value == "getenv":
        return _first_string_arg(call)
    if isinstance(func, cst.Attribute):
        if func.attr.value == "getenv" and _is_module_name(func.value, "os"):
            return _first_string_arg(call)
        if func.attr.value == "get" and _is_environ_ref(func.value):
            return _first_string_arg(call)
    return ""


def _is_module_name(node: cst.BaseExpression, name: str) -> bool:
    return isinstance(node, cst.Name) and node.value == name


def _environ_subscript_key(node: cst.Subscript) -> str:
    """The key of ``os.environ["K"]`` / ``environ["K"]``, or "" otherwise."""
    if not _is_environ_ref(node.value):
        return ""
    if len(node.slice) != 1:
        return ""
    element = node.slice[0]
    if not isinstance(element.slice, cst.Index):
        return ""
    return _string_value(element.slice.value)


def _in_environ_key(node: cst.Comparison) -> str:
    """The key of ``"K" in os.environ`` / ``"K" in environ``, or "" otherwise."""
    if len(node.comparisons) != 1:
        return ""
    target = node.comparisons[0]
    if not isinstance(target.operator, cst.In):
        return ""
    if not _is_environ_ref(target.comparator):
        return ""
    return _string_value(node.left)
