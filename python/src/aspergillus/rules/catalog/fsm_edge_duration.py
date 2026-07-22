"""ASP412: FSM edge duration — no unbounded work inside a transition body.

Ported from the standalone ASP-FSM-EDGE-DURATION probe (pebble ``asp-fef``),
which satisfied its own fixture-level acceptance but enforced nothing — no
gate ran it. This rule lifts the same invariant into
the ``aspergillus.rules`` corpus so ``fixit lint`` (and therefore any
consumer's commit gate, per ``[tool.fixit] enable = ["aspergillus.rules"]``)
actually catches the shape.

Sibling to the other ASP-FSM rules (``FsmEnumDispatchExhaustive``,
``FsmRedundantBranches``, ``FsmStringlyDispatch``) ported alongside it under
pebble ``asp-fd1``; this is the only member of the set that inspects edge
BODIES rather than dispatch case ANALYSIS.

Motivation (exophial incident, 2026-07-22, pebble ``exo-2e2`` / ``exo-d1b.2``)
--------------------------------------------------------------------------
Classical FSM contract: time is spent in STATES; transitions are
instantaneous. An edge whose body runs an LLM/subprocess call, drives
another state machine's full run/drive entrypoint, or spins an unbounded
retry loop is a real, occupied state the machine failed to declare —
unobservable (no bus mark, no log line; exists only in the call stack),
blocks the interpreter (exophial's single-threaded reducer froze all
dispatch for ~5 min per occurrence), invisible to liveness sweeps (which
watch workers, not edges), and has accidental crash/resume semantics. This
is the dual of exophial doctrine's "an exit transition you left implicit is
a state you failed to handle": an edge with duration is a state you failed
to declare. The correct shape is for an edge to write a durable marker and
return; the outer interpreter re-enters later via a declared state.

**Reject-severity, not severity-graduated.** Unlike the Tier 2
detection-only catalog rules (ASP406-410, which land at ``warn`` and
promote to ``error`` once a consumer's tree is clean, per
``docs/decisions/2026-05-19-mtm-past-warn-promotion-phase.md``), this rule
ships as an immediate hard failure — the same class of blocking violation
ASP410 already produces through the real ``fixit lint`` CLI. The
motivating defects (exo-2e2, exo-d1b.2) were both live production
incidents, not stylistic smells with a mechanically uncertain fix; there is
no grace period during which an edge is allowed to embed unbounded work.

Edge recognition (heuristic, same two shapes as the standalone checker)
-------------------------------------------------------------------------
A function is recognized as an edge body if it either:

  (a) dispatches on an Enum-typed subject via an if/elif chain (or
      ``match``) that compares against a member of a class subclassing
      ``Enum``, with at least one branch performing a call (the
      transition's terminal action); or
  (b) carries an explicit ``# asp-fsm: edge`` comment directly above the
      ``def``.

Honest limits (state plainly, per exo-011's discipline)
---------------------------------------------------------
This is a heuristic, scoped checker: it does not attempt semantic analysis
of whether some other call is unbounded, and it does not trace calls
through an intermediate helper function — indirection (a helper wrapping
the call) defeats detection by design; only direct calls inside the
identified edge body are flagged.
"""

from __future__ import annotations

from collections.abc import Sequence

import libcst as cst
from fixit import Invalid, LintRule, Valid

_ENUM_BASE_NAMES: frozenset[str] = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"})
_EDGE_MARKER_COMMENT = "# asp-fsm: edge"
_UNBOUNDED_ATTR_NAMES: frozenset[str] = frozenset({"complete", "run", "drive"})
_SUBPROCESS_ATTR_NAMES: frozenset[str] = frozenset(
    {"run", "call", "Popen", "check_output", "check_call"}
)

# Own-scope traversal stops descending past these — composition through a
# nested function/class/lambda is invisible to the scan by design
# (indirection defeats detection).
_SCOPE_BOUNDARY_TYPES = (cst.FunctionDef, cst.ClassDef, cst.Lambda)

_MESSAGE_PREFIX = (
    "ASP412: FSM edge body embeds unbounded work ({reason}) — a transition "
    "must be instantaneous. Write a durable marker and return; let the "
    "outer interpreter re-enter later via a declared state."
)


class FsmEdgeDuration(LintRule):
    """ASP412: FSM edge body embeds unbounded work (LLM/subprocess call,
    another FSM's run/drive entrypoint, or an unbounded retry loop) instead
    of writing a durable marker and returning.

    Reject-severity: ships as an immediate blocking violation, not
    severity-graduated. Detection-only (no autofix) — the fix is to move
    the unbounded work behind a declared state, which requires human/agent
    judgment.
    """

    MESSAGE = _MESSAGE_PREFIX.format(reason="...")

    _enum_names: frozenset[str]
    _module_header: Sequence[cst.EmptyLine]
    _first_statement: cst.CSTNode | None

    def visit_Module(self, node: cst.Module) -> None:
        # Reset per-file state — a rule instance may be reused across files.
        self._enum_names = _collect_enum_names(node)
        # A marker comment on the module's very first statement attaches to
        # `Module.header`, not that statement's own `leading_lines` — LibCST
        # reserves `leading_lines` for lines between prior sibling statements.
        self._module_header = node.header
        self._first_statement = node.body[0] if node.body else None

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        header_fallback = self._module_header if node is self._first_statement else ()
        if not _is_edge_function(node, self._enum_names, header_fallback):
            return
        for offending, reason in _scan_edge_violations(node):
            self.report(offending, _MESSAGE_PREFIX.format(reason=reason))

    VALID = [
        # The corrected shape: write a durable marker and return, instead
        # of calling the LLM inline (exo-2e2's fix).
        Valid(
            "from enum import Enum\n"
            "\n"
            "class Status(Enum):\n"
            "    NEEDS_SPEC = 1\n"
            "    READY = 2\n"
            "\n"
            "def integrate_edge(status: Status, ctx):\n"
            "    if status == Status.NEEDS_SPEC:\n"
            '        ctx.bus.write_marker("needs_spec_bounce")\n'
            "        return\n"
            "    elif status == Status.READY:\n"
            "        ctx.mark_integrated(None)\n"
        ),
        # A plain helper — no enum dispatch, no edge marker — is not
        # recognized as an edge body even though it makes an unbounded call.
        Valid(
            "def helper_utility(ctx):\n"
            '    result = Transport().complete(prompt="derive spec")\n'
            "    return result\n"
        ),
        # Indirection through a helper function defeats detection by
        # design: the edge only calls a bare-name helper, not the LLM
        # directly.
        Valid(
            "from enum import Enum\n"
            "\n"
            "class Status(Enum):\n"
            "    NEEDS_SPEC = 1\n"
            "    READY = 2\n"
            "\n"
            "def _call_llm(ctx):\n"
            '    return Transport().complete(prompt="derive spec")\n'
            "\n"
            "def integrate_edge(status: Status, ctx):\n"
            "    if status == Status.NEEDS_SPEC:\n"
            "        result = _call_llm(ctx)\n"
            "        ctx.mark_integrated(result)\n"
            "    elif status == Status.READY:\n"
            "        ctx.mark_integrated(None)\n"
        ),
    ]
    INVALID = [
        # The load-bearing motivating case: an enum-dispatch edge directly
        # invoking Transport().complete(...) (exo-2e2's needs-spec bounce).
        Invalid(
            "from enum import Enum\n"
            "\n"
            "class Status(Enum):\n"
            "    NEEDS_SPEC = 1\n"
            "    READY = 2\n"
            "\n"
            "def integrate_edge(status: Status, ctx):\n"
            "    if status == Status.NEEDS_SPEC:\n"
            '        result = Transport().complete(prompt="derive spec")\n'
            "        ctx.mark_integrated(result)\n"
            "    elif status == Status.READY:\n"
            "        ctx.mark_integrated(None)\n"
        ),
        # Opt-in marker on a helper with no enum dispatch: flagged because
        # of the explicit `# asp-fsm: edge` annotation.
        Invalid(
            "# asp-fsm: edge\n"
            "def dispatch_helper(ctx):\n"
            '    result = Transport().complete(prompt="derive spec")\n'
            "    return result\n"
        ),
        # Direct call into another FSM's run entrypoint (exo-d1b.2's
        # SPECIFY-at-dispatch shape).
        Invalid(
            "from enum import Enum\n"
            "\n"
            "class Status(Enum):\n"
            "    NEEDS_SPEC = 1\n"
            "    READY = 2\n"
            "\n"
            "def integrate_edge(status: Status, ctx):\n"
            "    if status == Status.NEEDS_SPEC:\n"
            "        SpecifyMachine().run(ctx)\n"
            "        ctx.mark_integrated(None)\n"
            "    elif status == Status.READY:\n"
            "        ctx.mark_integrated(None)\n"
        ),
        # Unbounded `while True` retry/convergence loop inside the edge.
        Invalid(
            "from enum import Enum\n"
            "\n"
            "class Status(Enum):\n"
            "    NEEDS_SPEC = 1\n"
            "    READY = 2\n"
            "\n"
            "def integrate_edge(status: Status, ctx):\n"
            "    if status == Status.NEEDS_SPEC:\n"
            "        while True:\n"
            "            if ctx.try_converge():\n"
            "                break\n"
            "        ctx.mark_integrated(None)\n"
            "    elif status == Status.READY:\n"
            "        ctx.mark_integrated(None)\n"
        ),
    ]


# --- enum-class discovery (whole-module pass) -------------------------------


def _base_name(arg: cst.Arg) -> str | None:
    """Pure: the bare class name of a base-class expression, or None."""
    value = arg.value
    if isinstance(value, cst.Name):
        return value.value
    if isinstance(value, cst.Attribute):
        return value.attr.value
    return None


def _collect_enum_names(module: cst.Module) -> frozenset[str]:
    """Pure: names of classes anywhere in `module` that subclass a known
    Enum base."""
    names: set[str] = set()
    _collect_enum_names_into(module, names)
    return frozenset(names)


def _collect_enum_names_into(node: cst.CSTNode, names: set[str]) -> None:
    """Pure (mutates only the passed-in accumulator): recursive whole-tree
    walk, unlike `_own_scope_nodes` below — enum classes may be declared
    anywhere in the module, not just at the top level of the function
    that dispatches on them."""
    if isinstance(node, cst.ClassDef) and any(
        _base_name(base) in _ENUM_BASE_NAMES for base in node.bases
    ):
        names.add(node.name.value)
    for child in node.children:
        _collect_enum_names_into(child, names)


# --- edge-body recognition ---------------------------------------------------


def _is_enum_member_access(node: cst.BaseExpression, enum_names: frozenset[str]) -> bool:
    """Pure: True iff `node` is `<EnumClass>.<MEMBER>` for a known enum."""
    return (
        isinstance(node, cst.Attribute)
        and isinstance(node.value, cst.Name)
        and node.value.value in enum_names
    )


def _is_enum_dispatch_test(test: cst.BaseExpression, enum_names: frozenset[str]) -> bool:
    """Pure: True iff `test` compares something against a known enum member."""
    if not isinstance(test, cst.Comparison) or len(test.comparisons) != 1:
        return False
    target = test.comparisons[0]
    if not isinstance(target.operator, (cst.Equal, cst.Is)):
        return False
    return _is_enum_member_access(target.comparator, enum_names) or _is_enum_member_access(
        test.left, enum_names
    )


def _match_case_is_enum(pattern: cst.MatchPattern, enum_names: frozenset[str]) -> bool:
    """Pure: True iff a `match` case pattern matches a known enum member."""
    return isinstance(pattern, cst.MatchValue) and _is_enum_member_access(pattern.value, enum_names)


def _own_scope_nodes(root: cst.CSTNode) -> list[cst.CSTNode]:
    """Pure: `root` plus all descendants, not descending into nested
    function/class/lambda bodies -- composition through a helper is
    invisible to this scan by design (indirection defeats detection)."""
    result: list[cst.CSTNode] = [root]
    stack: list[cst.CSTNode] = list(root.children)
    while stack:
        node = stack.pop()
        result.append(node)
        if node is not root and isinstance(node, _SCOPE_BOUNDARY_TYPES):
            continue
        stack.extend(node.children)
    return result


def _suite_has_call(suite: cst.CSTNode | None) -> bool:
    """Pure: True iff `suite`'s own scope contains a Call."""
    if suite is None:
        return False
    return any(isinstance(n, cst.Call) for n in _own_scope_nodes(suite))


def _has_enum_dispatch_action(func: cst.FunctionDef, enum_names: frozenset[str]) -> bool:
    """Pure: True iff `func` dispatches on an enum member (if/elif or
    match) with at least one branch performing a call."""
    for node in _own_scope_nodes(func):
        if isinstance(node, cst.If) and _is_enum_dispatch_test(node.test, enum_names):
            if _suite_has_call(node.body) or _suite_has_call(node.orelse):
                return True
        if isinstance(node, cst.Match):
            for case in node.cases:
                if _match_case_is_enum(case.pattern, enum_names) and _suite_has_call(case.body):
                    return True
    return False


def _has_marker_comment(func: cst.FunctionDef, header_fallback: Sequence[cst.EmptyLine]) -> bool:
    """Pure: True iff `# asp-fsm: edge` is the closest comment/blank line
    directly above `def`, skipping blank lines the same way the original
    text-based checker skipped them. Falls back to the module header when
    `func` is the module's first statement (see `visit_Module`)."""
    lines = func.leading_lines or header_fallback
    for line in reversed(lines):
        if line.comment is not None:
            return line.comment.value.strip() == _EDGE_MARKER_COMMENT
    return False


def _is_edge_function(
    func: cst.FunctionDef, enum_names: frozenset[str], header_fallback: Sequence[cst.EmptyLine]
) -> bool:
    """Pure: True iff `func` is recognized as an FSM transition body."""
    return _has_marker_comment(func, header_fallback) or _has_enum_dispatch_action(func, enum_names)


# --- unbounded-work detection -------------------------------------------------


def _unbounded_call_reason(call: cst.Call) -> str | None:
    """Pure: reason string if `call` is a direct LLM/subprocess/FSM-drive
    invocation, else None."""
    func = call.func
    if not isinstance(func, cst.Attribute):
        return None
    attr = func.attr.value
    if attr in _UNBOUNDED_ATTR_NAMES:
        return f"direct call to .{attr}(...) inside edge body"
    if (
        isinstance(func.value, cst.Name)
        and func.value.value == "subprocess"
        and attr in _SUBPROCESS_ATTR_NAMES
    ):
        return f"direct subprocess.{attr}(...) call inside edge body"
    return None


def _is_unbounded_retry_loop(node: cst.While) -> bool:
    """Pure: True iff `node` is a `while True:` loop."""
    return isinstance(node.test, cst.Name) and node.test.value == "True"


def _scan_edge_violations(func: cst.FunctionDef) -> Sequence[tuple[cst.CSTNode, str]]:
    """Pure: (offending node, reason) pairs found directly inside `func`'s
    own scope."""
    violations: list[tuple[cst.CSTNode, str]] = []
    for node in _own_scope_nodes(func):
        if isinstance(node, cst.Call):
            reason = _unbounded_call_reason(node)
            if reason is not None:
                violations.append((node, reason))
        elif isinstance(node, cst.While) and _is_unbounded_retry_loop(node):
            violations.append((node, "unbounded 'while True' retry/convergence loop"))
    return violations
