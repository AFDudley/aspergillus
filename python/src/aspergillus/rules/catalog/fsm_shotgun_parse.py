"""ASP417: shotgun parsing — validate all input before acting on any of it.

FSM-verification-integrity family; sibling to ASP408 anti-special-casing,
ASP409 shell-to-self, ASP410 in-process-e2e, ASP411 fsm-redundant-branches,
ASP412 fsm-edge-duration, ASP413 fsm-enum-dispatch-exhaustive, ASP414
fsm-stringly-dispatch, and ASP416 fsm-validate-not-parse. ASP416 guards the
parse boundary itself: the function's signature. ASP417 guards the seam one
step later: the parse boundary's own body, where a function that can reject
its input must finish checking the whole input before it acts on any part
of it.

Momot, Bratus, Hallberg, and Patterson's "The Seven Turrets of Babel: A
Taxonomy of LangSec Errors and How to Expunge Them" (2016) [1] names the
anti-pattern this rule enforces (process.md step 3.3 in this pack's own
doctrine, alongside Alexis King's "Parse, don't validate" (2019) [2]):
shotgun parsing. A shotgun parser interleaves input validation with the
action the input drives. It commits a side effect on an early, unchecked
part of the input, then finds a later part invalid and stops partway
through. The action already ran; there is no way to undo it. The correct
shape checks the whole input first, then acts on the proven-good result.

Trigger (heuristic proxy over the function body; no full dataflow)
--------------------------------------------------------------------
Within one function body, the rule flags a REJECTION statement (a `raise`,
or a `return` of a refusal/`None` arm) that is preceded, anywhere earlier
in the same function — the same block or an enclosing one — by a
SIDE-EFFECTING statement. "Preceded" means lexical order, not full
control-flow reachability. This keeps the check decidable from the CST
alone, at the cost of a false positive on an effect and a rejection that
provably sit on mutually exclusive branches.

A statement counts as side-effecting when it is:

- a call to a method whose name is in a small effect set: `append`,
  `extend`, `add`, `update`, `write`, `writelines`, `save`, `send`,
  `commit`, `execute`, `executemany`, `insert`, `delete`, `put`, `post`,
  `flush`, `close`, `mkdir`, `unlink`, `remove`;
- a call to `subprocess.run`/`.call`/`.Popen`/`.check_output`/
  `.check_call`, or a bare `open(...)`/`print(...)` call; or
- an assignment to a subscript or attribute of one of the function's own
  parameters (`param[...] = ...` / `param.attr = ...`).

A function that rejects all its input before its first effect — parse,
then act — never trips this rule: the rejection came first, so no effect
lexically precedes it. A pure function with no effect and no rejection
never trips it either.

Result-check exemption
----------------------
A rejection does NOT count, even with an earlier effect, when its
nearest guarding `if` test reads only names bound from that effect's own
result: the call's own return value (`result = subprocess.run(...)`), a
method call's receiver (`cursor` in `cursor.execute(...)`), or a name
assigned from either (`out = result.stdout`, `position =
cursor.lastrowid`). Checking an operation's own outcome is not shotgun
parsing. Only a rejection whose condition reads the function's input --
a parameter, or a value derived from one -- after an effect on that same
input trips the rule.

Escape hatch
------------
A function carrying a `# asp-fsm: boundary-parse` comment anywhere in its
body is exempt, matching ASP414's and ASP416's marker exactly. A genuine
boundary parser may legitimately mix validation and action by design (for
example, a streaming decoder that must consume bytes before it can tell
whether the rest of them are even well-formed).

**Ships without autofix** (Tier 2, detection-only, per
`docs/decisions/2026-05-19-severity-graduation.md`). Moving a function's
checks ahead of its actions is a judgment call — which checks guard which
action, and whether an action is safe to defer — that the rule cannot make
mechanically.

[1] Falcon Darkstar Momot, Sergey Bratus, Sven M. Hallberg, and Meredith L.
Patterson, "The Seven Turrets of Babel: A Taxonomy of LangSec Errors and
How to Expunge Them", IEEE Cybersecurity Development (SecDev), 2016.
[2] Alexis King, "Parse, don't validate", 2019.
https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/
"""

from __future__ import annotations

import libcst as cst
from fixit import Invalid, LintRule, Valid
from libcst.metadata import PositionProvider

#: Comment marker that silences this rule for the function it appears in,
#: matching ASP414's and ASP416's `BOUNDARY_MARKER` exactly.
BOUNDARY_MARKER = "asp-fsm: boundary-parse"

#: Method names treated as side-effecting regardless of receiver.
_EFFECT_METHOD_NAMES: frozenset[str] = frozenset(
    {
        "append",
        "extend",
        "add",
        "update",
        "write",
        "writelines",
        "save",
        "send",
        "commit",
        "execute",
        "executemany",
        "insert",
        "delete",
        "put",
        "post",
        "flush",
        "close",
        "mkdir",
        "unlink",
        "remove",
    }
)

#: `subprocess.<name>(...)` calls treated as side-effecting.
_SUBPROCESS_ATTR_NAMES: frozenset[str] = frozenset(
    {"run", "call", "Popen", "check_output", "check_call"}
)

#: Bare (no-receiver) calls treated as side-effecting.
_BARE_EFFECT_CALL_NAMES: frozenset[str] = frozenset({"open", "print"})

# Own-scope traversal stops descending past these -- composition through a
# nested function/class/lambda is invisible to the scan by design
# (indirection defeats detection, matching ASP412's own-scope walk).
_SCOPE_BOUNDARY_TYPES = (cst.FunctionDef, cst.ClassDef, cst.Lambda)

_MESSAGE = (
    "ASP417: shotgun parsing — this function commits a side effect, then "
    "later rejects its input on a condition testing the input itself, "
    "not the effect's own result (a `raise`, or a refusal/`None` "
    "`return`). The action already ran before the whole input was proven "
    "valid (Momot, Bratus, Hallberg, and Patterson, 'The Seven Turrets of "
    "Babel', 2016). Validate all of the input before acting on any of it, "
    "or add '# asp-fsm: boundary-parse' if this is a genuine boundary "
    "parser."
)


def _param_names(node: cst.FunctionDef) -> frozenset[str]:
    """Pure: the bare names of every one of `node`'s parameters, across
    positional-only, positional-or-keyword, keyword-only, `*args`, and
    `**kwargs` params."""
    params = node.params
    all_params = [*params.posonly_params, *params.params, *params.kwonly_params]
    for star in (params.star_arg, params.star_kwarg):
        if isinstance(star, cst.Param):
            all_params.append(star)
    return frozenset(p.name.value for p in all_params)


def _is_effect_call(call: cst.Call) -> bool:
    """Pure: True iff `call` is a direct call to a method in the small
    effect set, a `subprocess.*` call, or a bare `open`/`print` call."""
    func = call.func
    if isinstance(func, cst.Attribute):
        if func.attr.value in _EFFECT_METHOD_NAMES:
            return True
        base = func.value
        return (
            isinstance(base, cst.Name)
            and base.value == "subprocess"
            and func.attr.value in _SUBPROCESS_ATTR_NAMES
        )
    if isinstance(func, cst.Name):
        return func.value in _BARE_EFFECT_CALL_NAMES
    return False


def _base_name(expr: cst.BaseExpression) -> str | None:
    """Pure: the root `Name` a chain of attribute/subscript access resolves
    to, e.g. `param.a[0].b` -> `"param"`."""
    if isinstance(expr, cst.Name):
        return expr.value
    if isinstance(expr, (cst.Attribute, cst.Subscript)):
        return _base_name(expr.value)
    return None


def _assignment_targets(node: cst.CSTNode) -> list[cst.BaseExpression]:
    """Pure: every target expression `node` assigns to, or `[]` if `node`
    isn't an assignment."""
    if isinstance(node, cst.Assign):
        return [t.target for t in node.targets]
    if isinstance(node, (cst.AugAssign, cst.AnnAssign)):
        return [node.target]
    return []


def _is_param_mutation(node: cst.CSTNode, param_names: frozenset[str]) -> bool:
    """Pure: True iff `node` assigns to a subscript or attribute of one of
    `param_names` (`param[...] = ...` / `param.attr = ...`)."""
    for target in _assignment_targets(node):
        if isinstance(target, (cst.Attribute, cst.Subscript)) and _base_name(target) in param_names:
            return True
    return False


def _is_refusal_return(node: cst.Return) -> bool:
    """Pure: True iff `node` returns nothing (bare `return`) or returns the
    literal `None`."""
    return node.value is None or (isinstance(node.value, cst.Name) and node.value.value == "None")


_LITERAL_NAMES: frozenset[str] = frozenset({"None", "True", "False"})


def _referenced_base_names(node: cst.CSTNode) -> frozenset[str]:
    """Pure: the base name of every value `node` reads -- the root `Name`
    of each `Name`/`Attribute`/`Call` chain, skipping attribute-name and
    keyword-argument leaves (never loads) and the `None`/`True`/`False`
    literals. Used to test what a rejection's guarding `if` test actually
    depends on."""
    names: set[str] = set()
    _referenced_base_names_into(node, names)
    return frozenset(names)


def _referenced_base_names_into(node: cst.CSTNode, names: set[str]) -> None:
    """Pure (mutates only the passed-in accumulator): see
    `_referenced_base_names`."""
    if isinstance(node, cst.Name):
        if node.value not in _LITERAL_NAMES:
            names.add(node.value)
        return
    if isinstance(node, cst.Attribute):
        _referenced_base_names_into(node.value, names)
        return
    if isinstance(node, cst.Call):
        _referenced_base_names_into(node.func, names)
        for arg in node.args:
            _referenced_base_names_into(arg.value, names)
        return
    for child in node.children:
        _referenced_base_names_into(child, names)


def _rhs_is_effect_derived(rhs: cst.BaseExpression, effect_names: set[str]) -> bool:
    """Pure: True iff `rhs` is itself a side-effecting call, or an
    attribute/subscript chain rooted at a name already bound from one --
    the shape `out = result.stdout` after `result = subprocess.run(...)`,
    or `position = cursor.lastrowid` after `cursor.execute(...)`."""
    if isinstance(rhs, cst.Call) and _is_effect_call(rhs):
        return True
    base = _base_name(rhs)
    return base is not None and base in effect_names


def _scan_shotgun_violations(func: cst.FunctionDef) -> list[cst.CSTNode]:
    """Pure: every rejection node (`raise EXPR`, or a refusal/`None`
    `return`) in `func`'s own scope that follows a side-effecting
    statement earlier in the same scan, EXCEPT one whose nearest guarding
    `if` test reads only names bound from that effect's own result -- the
    call's return value, a method call's receiver, or a name derived from
    either. Checking an operation's own outcome isn't shotgun parsing;
    only a rejection that tests the function's input after an effect on
    that input is. A bare `raise` (no exception expression) never counts:
    it re-raises the exception an `except` handler is already handling,
    not a rejection of the function's input."""
    param_names = _param_names(func)
    violations: list[cst.CSTNode] = []
    effect_names: set[str] = set()
    effect_seen = [False]
    _scan_shotgun_violations_into(
        func.body, param_names, effect_names, effect_seen, frozenset(), violations
    )
    return violations


def _scan_shotgun_violations_into(
    node: cst.CSTNode,
    param_names: frozenset[str],
    effect_names: set[str],
    effect_seen: list[bool],
    guard_names: frozenset[str],
    violations: list[cst.CSTNode],
) -> None:
    """Pure (mutates only `effect_names`, `effect_seen`, and `violations`):
    the recursive own-scope walk behind `_scan_shotgun_violations`, in
    source order -- composition through a nested function/class/lambda
    stays invisible by design (indirection defeats detection, matching
    ASP412's own-scope walk). `guard_names` is the base names read by the
    nearest enclosing `if`'s test: the condition a rejection directly
    beneath it is checking."""
    if isinstance(node, _SCOPE_BOUNDARY_TYPES):
        return
    if isinstance(node, cst.Call) and _is_effect_call(node):
        effect_seen[0] = True
        if isinstance(node.func, cst.Attribute):
            receiver = _base_name(node.func.value)
            if receiver is not None:
                effect_names.add(receiver)
    elif isinstance(node, (cst.Assign, cst.AugAssign, cst.AnnAssign)) and _is_param_mutation(
        node, param_names
    ):
        effect_seen[0] = True
    elif isinstance(node, cst.Assign) and _rhs_is_effect_derived(node.value, effect_names):
        for target in _assignment_targets(node):
            if isinstance(target, cst.Name):
                effect_names.add(target.value)
    elif effect_seen[0] and isinstance(node, cst.Raise):
        if node.exc is not None and not (guard_names and guard_names <= effect_names):
            violations.append(node)
    elif effect_seen[0] and isinstance(node, cst.Return) and _is_refusal_return(node):
        if not (guard_names and guard_names <= effect_names):
            violations.append(node)

    if isinstance(node, cst.If):
        test_names = _referenced_base_names(node.test)
        _scan_shotgun_violations_into(
            node.test, param_names, effect_names, effect_seen, guard_names, violations
        )
        _scan_shotgun_violations_into(
            node.body, param_names, effect_names, effect_seen, test_names, violations
        )
        if node.orelse is not None:
            _scan_shotgun_violations_into(
                node.orelse, param_names, effect_names, effect_seen, test_names, violations
            )
        return

    for child in node.children:
        _scan_shotgun_violations_into(
            child, param_names, effect_names, effect_seen, guard_names, violations
        )


class FsmShotgunParse(LintRule):
    """ASP417: a function commits a side effect, then later rejects its
    input instead of validating the whole input first -- shotgun parsing
    (Momot, Bratus, Hallberg, and Patterson, 2016; King, 2019).

    Detection-only (no autofix): reordering checks ahead of actions is a
    judgment call.
    """

    MESSAGE = _MESSAGE
    METADATA_DEPENDENCIES = (PositionProvider,)

    #: The current file's source, split into lines (1-indexed by callers).
    _source_lines: list[str]

    VALID = [
        # Pure function: no effect, no rejection.
        Valid("def add(a, b):\n    return a + b\n"),
        # Parse-then-act: a first pass rejects every bad element before a
        # second pass acts on the now-proven-good input.
        Valid(
            "def process(items, sink):\n"
            "    for item in items:\n"
            "        if item < 0:\n"
            '            raise ValueError("negative item")\n'
            "    for item in items:\n"
            "        sink.append(item)\n"
        ),
        # Rejects before its only effect: the guard runs first.
        Valid(
            "def apply(config, value):\n"
            "    if value is None:\n"
            '        raise ValueError("value required")\n'
            "    config.value = value\n"
        ),
        # The escape hatch: an otherwise-flagged shape, exempted.
        Valid(
            "def process(items, sink):\n"
            "    # asp-fsm: boundary-parse\n"
            "    for item in items:\n"
            "        sink.append(item)\n"
            "        if item < 0:\n"
            '            raise ValueError("negative item")\n'
        ),
        # Result-check exemption: the rejection tests the effect's own
        # bound return value (a SQLite cursor's `lastrowid`), not the
        # input.
        Valid(
            "def insert_row(cursor, row):\n"
            '    cursor.execute("INSERT INTO t VALUES (?)", (row,))\n'
            "    position = cursor.lastrowid\n"
            "    if position is None:\n"
            '        raise MalformedRow("insert did not return a rowid")\n'
            "    return position\n"
        ),
        # Result-check exemption: the rejection tests the effect's own
        # exit-code result.
        Valid(
            "def run_tool(args):\n"
            "    result = subprocess.run(args)\n"
            "    if result.returncode != 0:\n"
            "        return None\n"
            "    return result\n"
        ),
        # Result-check exemption: the rejection tests a value derived from
        # the effect's own result (the subprocess's stdout).
        Valid(
            "def run_ape(ape, args):\n"
            "    result = subprocess.run([ape, *args])\n"
            "    out = result.stdout\n"
            "    if 'error' in out or not out.strip():\n"
            '        raise AceRefused("ape refused the input")\n'
            "    return out\n"
        ),
        # Bare-re-raise exemption: the `except` handler runs a cleanup
        # effect (the rollback), then a bare `raise` re-propagates the
        # exception already being handled. A bare `raise` never rejects
        # the function's input, so it never counts as a rejection.
        Valid(
            "def append(cursor, record):\n"
            '    cursor.execute("BEGIN")\n'
            "    try:\n"
            "        cursor.execute(INSERT, record)\n"
            '        cursor.execute("COMMIT")\n'
            "    except BaseException:\n"
            '        cursor.execute("ROLLBACK")\n'
            "        raise\n"
            "    return record\n"
        ),
    ]
    INVALID = [
        # The motivating shape: append to a sink inside a loop, then raise
        # on a later, invalid element in the same loop body.
        Invalid(
            "def process(items, sink):\n"
            "    for item in items:\n"
            "        sink.append(item)\n"
            "        if item < 0:\n"
            '            raise ValueError("negative item")\n'
        ),
        # Writes to a parameter's attribute, then returns None on a bad
        # condition discovered afterward.
        Invalid(
            "def apply(config, value):\n"
            "    config.value = value\n"
            "    if value is None:\n"
            "        return None\n"
        ),
        # Real shotgun parse: the effect acts on one input value, the
        # rejection tests a different input value -- not the effect's
        # own result.
        Invalid(
            "def process(items, other, sink):\n"
            "    sink.append(items[0])\n"
            "    if other < 0:\n"
            '        raise ValueError("bad other")\n'
        ),
    ]

    def visit_Module(self, node: cst.Module) -> None:
        # Reset per-file state -- a rule instance may be reused across
        # files by the fixit engine.
        self._source_lines = node.code.splitlines()

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        pos = self.get_metadata(PositionProvider, node)
        lines = self._source_lines[pos.start.line - 1 : pos.end.line]
        if any(BOUNDARY_MARKER in line for line in lines):
            return
        for offending in _scan_shotgun_violations(node):
            self.report(offending, self.MESSAGE)
