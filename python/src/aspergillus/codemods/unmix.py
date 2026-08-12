"""Lift the logic out of a function that mixes I/O with logic.

ASP206 reports the entanglement Cockburn names: "the entanglement between
the business logic and the interaction with external entities". Reporting
it is not removing it. This codemod removes it, for the shapes where the
removal is mechanical, and REFUSES the rest by name rather than leaving a
silent residue.

The transformation, in its two forms::

    def f(a):                       def _f_core(a, x):
        x = io()                        <logic using x>
        <logic using x>     ->      def f(a):
                                        x = io()
                                        return _f_core(a, x)

    def f(a):                       def _f_core(a, x):
        x = io()                        <logic using x>
        <logic using x>     ->          return y
        io(y)                       def f(a):
                                        x = io()
                                        y = _f_core(a, x)
                                        io(y)

The first form lifts the trailing run of pure statements. The second lifts
a pure run with shell on both sides, and the core returns the bindings the
rest of the shell reads. Both leave every effect where it was, in the
order it was in.

WHY LIBCST AND NOT AST-GREP. The hard part is not matching the shape, it
is the PARAMETER LIST: the set of names the lifted logic reads that the
shell bound. That is a name-binding question, so this uses libcst's
``ScopeProvider``, which resolves each read to the assignment that binds
it. ``ast-grep`` matches patterns and holds no notion of which names a
statement binds, so it cannot construct the parameter list at all.

WHAT THIS REFUSES, AND WHY EACH REFUSAL IS A DESIGN DECISION AND NOT A
GAP. Each refusal names one thing a person must decide:

- **The pure run calls a helper the census reports as effect-bearing.**
  ``_find_io_calls`` sees the call site, not the callee, so a run that
  calls ``_write_report(...)`` looks pure and is not. Lifting it would
  move an effect INTO the core, which is the opposite of the point. The
  answer is to split the helper first, and that is a decision about the
  helper.
- **The effect's target depends on a local computation.** In
  ``Path(f"/proc/{pid}/environ").read_text()`` the computation decides
  WHAT to read. You cannot lift the result to a parameter without lifting
  the decision, so the core must return a typed description and the shell
  must execute it — a different design, not this template.
- **The run reads ``self`` or ``cls``.** A module-scope core taking
  ``self`` is not a core; whether the logic belongs on the class or off it
  is a design decision.
- **The run cannot leave the function's control flow behind** — a
  ``return``, ``yield``, ``break`` or ``continue`` that escapes the run,
  an ``await``, or a ``global``/``nonlocal`` statement.

SELF-CHECKING. A lift is kept only if ASP206 stops reporting the function
afterwards. A transformation that leaves the finding standing is reverted
and recorded as a refusal, so the tool cannot claim a conversion the rule
does not agree with.
"""

from __future__ import annotations

from dataclasses import dataclass

import libcst as cst
from libcst.metadata import Assignment, MetadataWrapper, PositionProvider, ScopeProvider

from aspergillus.rules.level2 import MixedIOAndLogic, _find_io_calls


class _UnsuppressedMixedIOAndLogic(MixedIOAndLogic):
    """ASP206 with the ``# lint-ignore`` layer off.

    A directive hides a finding from a gate. It does not unmix the
    function, so it must not hide the function from the codemod either.
    """

    def ignore_lint(self, node: cst.CSTNode) -> bool:
        return False


@dataclass(frozen=True)
class Refusal:
    """One function the codemod declined, and the decision it needs."""

    name: str
    reason: str


@dataclass(frozen=True)
class Lift:
    """One function the codemod split, and the shape of the split."""

    name: str
    core_name: str
    params: tuple[str, ...]
    returns: tuple[str, ...]
    form: str
    untyped: tuple[str, ...]


@dataclass(frozen=True)
class UnmixResult:
    """The rewritten source, what was lifted, and what was refused."""

    source: str
    lifts: tuple[Lift, ...]
    refusals: tuple[Refusal, ...]


def unmix_source(source: str, effectful: frozenset[str] | None = None) -> UnmixResult:
    """Split every mechanically-liftable mixed function in ``source`` (pure).

    One function at a time, and one function may need several lifts: logic
    sits between effects as often as after them, and clearing ASP206 means
    lifting every pure run that computes, not the largest one.

    A function is converted only if ASP206 stops reporting it. A partial
    split that leaves the finding standing is REVERTED and recorded as a
    refusal, so a claim of conversion is never wider than the rule agrees.
    """
    known = effect_closure({"<module>": source}) if effectful is None else effectful
    lifts: list[Lift] = []
    refusals: list[Refusal] = []
    current = source
    for name in mixed_function_names(source):
        attempt, applied, refusal = _lift_until_clear(current, name, known)
        if applied and name not in mixed_function_names(attempt):
            current = attempt
            lifts.extend(applied)
            continue
        refusals.append(refusal or Refusal(name, f"{len(applied)} lift(s) left the finding"))
    return UnmixResult(source=current, lifts=tuple(lifts), refusals=tuple(refusals))


def _lift_until_clear(
    source: str, name: str, known: frozenset[str]
) -> tuple[str, list[Lift], Refusal | None]:
    """Lift one function's pure runs until ASP206 stops reporting it."""
    current = source
    applied: list[Lift] = []
    while name in mixed_function_names(current):
        outcome = _lift_one(current, name, len(applied), known)
        if isinstance(outcome, Refusal):
            return current, applied, outcome if not applied else None
        current, lift = outcome
        applied.append(lift)
    return current, applied, None


def mixed_function_names(source: str) -> tuple[str, ...]:
    """Qualified names of every function ASP206 reports in ``source`` (pure)."""
    module = cst.parse_module(source)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    rule = _UnsuppressedMixedIOAndLogic()
    wrapper.visit_batched([rule])
    lines = {v.range.start.line for v in rule._violations}
    positions = MetadataWrapper(module, unsafe_skip_copy=True).resolve(PositionProvider)
    return tuple(
        ".".join(prefix)
        for prefix, node in _iter_functions(module, ())
        if positions[node].start.line in lines
    )


def _iter_functions(
    node: cst.CSTNode, prefix: tuple[str, ...]
) -> list[tuple[tuple[str, ...], cst.FunctionDef]]:
    """Every function under ``node`` with its dotted qualified name."""
    out: list[tuple[tuple[str, ...], cst.FunctionDef]] = []
    for child in node.children:
        if isinstance(child, cst.FunctionDef):
            here = (*prefix, child.name.value)
            out.append((here, child))
            out.extend(_iter_functions(child, here))
        elif isinstance(child, cst.ClassDef):
            out.extend(_iter_functions(child, (*prefix, child.name.value)))
        else:
            out.extend(_iter_functions(child, prefix))
    return out


def _stmt_has_io(stmt: cst.BaseStatement) -> bool:
    """True if ``stmt`` performs an effect, by the tree's own predicate."""
    return bool(_find_io_calls(cst.IndentedBlock(body=[stmt])))


def _lift_one(
    source: str, name: str, ordinal: int, known: frozenset[str]
) -> tuple[str, Lift] | Refusal:
    """Plan and apply one lift, or refuse it with a stated reason."""
    module = cst.parse_module(source)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    scopes = wrapper.resolve(ScopeProvider)
    positions = wrapper.resolve(PositionProvider)
    found = [(p, n) for p, n in _iter_functions(module, ()) if ".".join(p) == name]
    if len(found) != 1:
        return Refusal(name, "the qualified name does not resolve to exactly one function")
    prefix, fn = found[0]
    if len(prefix) > 1 and not isinstance(_owner(module, fn), cst.ClassDef):
        return Refusal(name, "the function is nested inside another function")
    if not isinstance(fn.body, cst.IndentedBlock):
        return Refusal(name, "the body is a one-line suite with nothing to lift")
    plan = _plan_run(fn, name, known)
    if isinstance(plan, Refusal):
        return plan
    start, stop = plan
    return _apply(module, fn, name, start, stop, scopes, positions, ordinal)


def _owner(module: cst.Module, fn: cst.FunctionDef) -> cst.CSTNode | None:
    """The class or module statement that directly holds ``fn``."""
    for node in _walk(module):
        if isinstance(node, cst.ClassDef) and fn in _direct_functions(node):
            return node
    return None


def _direct_functions(node: cst.CSTNode) -> list[cst.FunctionDef]:
    body = getattr(node, "body", None)
    inner = getattr(body, "body", ())
    return [item for item in inner if isinstance(item, cst.FunctionDef)]


def _walk(node: cst.CSTNode) -> list[cst.CSTNode]:
    out: list[cst.CSTNode] = []
    stack = [node]
    while stack:
        current = stack.pop()
        for child in current.children:
            out.append(child)
            stack.append(child)
    return out


def _walk_own(node: cst.CSTNode) -> list[cst.CSTNode]:
    """Every descendant in the same function — nested defs are their own."""
    out: list[cst.CSTNode] = []
    stack = [node]
    while stack:
        current = stack.pop()
        for child in current.children:
            out.append(child)
            if not isinstance(child, cst.FunctionDef | cst.Lambda):
                stack.append(child)
    return out


_LOGIC_NODES = (
    cst.BinaryOperation,
    cst.UnaryOperation,
    cst.Comparison,
    cst.BooleanOperation,
    cst.IfExp,
    cst.ListComp,
    cst.SetComp,
    cst.DictComp,
    cst.GeneratorExp,
    cst.If,
    cst.For,
    cst.While,
    cst.Try,
)


def _logic_statements(run: list[cst.BaseStatement]) -> int:
    """How many statements in the run compute rather than name a value.

    ``machines: dict = {}`` is a declaration, not logic. A run of
    declarations moves no logic out of the boundary.
    """
    return sum(1 for stmt in run if any(isinstance(n, _LOGIC_NODES) for n in _walk_own(stmt)))


def _plan_run(fn: cst.FunctionDef, name: str, known: frozenset[str]) -> tuple[int, int] | Refusal:
    """Choose the run of pure statements to lift, or refuse.

    The trailing run is tried first: that is the template's own shape, and
    it needs no return of intermediate bindings. A middle run is the
    fallback, and it is tried longest first.

    A run must carry at least two computing statements. One is a
    THRESHOLD SHAVE: ASP206 fires above three, so moving a single
    statement out clears the finding while the boundary stays as mixed as
    it was. A count that falls because the detector stopped looking is
    the evasion this codemod must not automate.
    """
    assert isinstance(fn.body, cst.IndentedBlock)
    stmts = list(fn.body.body)
    if not any(_stmt_has_io(stmt) for stmt in stmts):
        return Refusal(name, "the function performs no effect this predicate can see")
    floor = 1 if _is_docstring(stmts[0]) else 0
    runs = [
        span
        for span in _pure_runs(stmts, floor)
        if not (span[0] == floor and span[1] == len(stmts))
        and _logic_statements(stmts[span[0] : span[1]]) >= 2
    ]
    if not runs:
        return Refusal(name, "no run beside the effects carries two computing statements")
    runs.sort(key=lambda span: (span[1] != len(stmts), span[0] - span[1]))
    first: Refusal | None = None
    for span in runs:
        guard = _guard_run(stmts[span[0] : span[1]], name, known, span[1] == len(stmts))
        if guard is None:
            return span
        first = first or guard
    assert first is not None
    return first


def _is_docstring(stmt: cst.BaseStatement) -> bool:
    """True if ``stmt`` is a function's leading docstring.

    A docstring performs no effect, so it opens the first pure run and
    would be lifted with it, leaving the shell undocumented and the core
    carrying prose about a function it is not.
    """
    if not isinstance(stmt, cst.SimpleStatementLine) or len(stmt.body) != 1:
        return False
    first = stmt.body[0]
    return isinstance(first, cst.Expr) and isinstance(first.value, cst.BaseString)


def _pure_runs(stmts: list[cst.BaseStatement], floor: int = 0) -> list[tuple[int, int]]:
    """Maximal half-open spans of consecutive statements with no effect."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, stmt in list(enumerate(stmts))[floor:]:
        if _stmt_has_io(stmt):
            if start is not None:
                runs.append((start, index))
                start = None
            continue
        if start is None:
            start = index
    if start is not None:
        runs.append((start, len(stmts)))
    return [span for span in runs if span[1] > span[0]]


_ESCAPES = (cst.Return, cst.Yield, cst.Global, cst.Nonlocal, cst.Await)


def _guard_run(
    run: list[cst.BaseStatement], name: str, known: frozenset[str], trailing: bool
) -> Refusal | None:
    """Refuse a run whose lift needs a decision rather than a rewrite."""
    reads = {node.value for stmt in run for node in _walk_own(stmt) if isinstance(node, cst.Name)}
    if reads & {"self", "cls"}:
        return Refusal(name, "the logic reads `self` or `cls`; a module-scope core cannot take it")
    reached = _called_names(run) & known
    if reached:
        called = ", ".join(sorted(reached))
        return Refusal(name, f"the logic calls {called}, which reaches an effect")
    if not trailing:
        escaping = [n for stmt in run for n in _walk_own(stmt) if isinstance(n, _ESCAPES)]
        if escaping:
            return Refusal(name, "the logic returns or awaits, so it cannot be lifted out of place")
        if _has_free_loop_exit(run):
            return Refusal(name, "the logic breaks or continues an enclosing loop")
    return None


def _has_free_loop_exit(run: list[cst.BaseStatement]) -> bool:
    """True if a break/continue in ``run`` escapes every loop inside it."""
    for stmt in run:
        if isinstance(stmt, cst.For | cst.While):
            continue
        for node in _walk_own(stmt):
            if isinstance(node, cst.Break | cst.Continue):
                return True
    return False


def _called_names(nodes: list[cst.BaseStatement] | cst.CSTNode) -> frozenset[str]:
    """The last dotted segment of every call target in ``nodes``.

    ``bus.write_reducer_comment(...)`` yields ``write_reducer_comment``.
    The bare segment is what the closure below is keyed on.
    """
    walk = nodes if isinstance(nodes, list) else [nodes]
    out: set[str] = set()
    for item in walk:
        for node in _walk_own(item):
            if not isinstance(node, cst.Call):
                continue
            func = node.func
            if isinstance(func, cst.Name):
                out.add(func.value)
            elif isinstance(func, cst.Attribute):
                out.add(func.attr.value)
    return frozenset(out)


#: Calls that observe the world without appearing in ``io_blocklist``.
#:
#: The census must reproduce ASP205's finding set exactly, so
#: ``io_blocklist`` cannot grow without changing what ASP202 and ASP206
#: measure. The codemod has the other job — never move an effect into a
#: core — and for that job a filesystem probe IS an effect. So the codemod
#: guards with a WIDER list than the census reports on, and says so.
#: ``Path.is_dir()`` in a precondition is the case that made this
#: necessary: it reads the filesystem and no rule in this tree sees it.
_PROBE_CALLS: frozenset[str] = frozenset(
    {
        "exists",
        "is_dir",
        "is_file",
        "is_symlink",
        "iterdir",
        "glob",
        "rglob",
        "stat",
        "lstat",
        "samefile",
        "readlink",
        "resolve",
        "expanduser",
        "cwd",
        "home",
        "chmod",
        "symlink_to",
        "getenv",
        "which",
        "listdir",
        "walk",
        "getcwd",
        "isatty",
    }
)


def effect_closure(sources: dict[str, str]) -> frozenset[str]:
    """Every function name in the tree that REACHES an effect.

    The census reports a function that performs an effect ITSELF. A run
    that calls ``_write_report(...)`` performs one too, and
    ``_find_io_calls`` cannot see it: it reads the call site, not the
    callee. Lifting such a run would move an effect INTO the core, which
    is the opposite of the point, so the closure is the codemod's guard.

    Keyed on the BARE function name, so two functions sharing a name are
    treated as one. That OVER-approximates, and deliberately: a refusal
    costs one named entry in the residue, while a permission that is
    wrong writes an effect into a core.
    """
    direct: set[str] = set()
    calls: dict[str, set[str]] = {}
    for source in sources.values():
        module = cst.parse_module(source)
        for prefix, fn in _iter_functions(module, ()):
            bare = prefix[-1]
            if _find_io_calls(fn.body) or _called_names(fn) & _PROBE_CALLS:
                direct.add(bare)
            calls.setdefault(bare, set()).update(_called_names(fn))
    closure = set(direct)
    growing = True
    while growing:
        growing = False
        for caller, callees in calls.items():
            if caller not in closure and callees & closure:
                closure.add(caller)
                growing = True
    return frozenset(closure) | _PROBE_CALLS


def _core_name(function_name: str, ordinal: int) -> str:
    """The sibling core's name. A second lift on one function is numbered."""
    base = f"_{function_name.lstrip('_')}_core"
    return base if ordinal == 0 else f"{base}{ordinal + 1}"


def _apply(
    module: cst.Module,
    fn: cst.FunctionDef,
    name: str,
    start: int,
    stop: int,
    scopes: object,
    positions: object,
    ordinal: int,
) -> tuple[str, Lift] | Refusal:
    """Build the core, rewrite the shell, and render the new module."""
    assert isinstance(fn.body, cst.IndentedBlock)
    stmts = list(fn.body.body)
    run, before, after = stmts[start:stop], stmts[:start], stmts[stop:]
    params = _parameters(fn, before, run, scopes)
    returns = _returned(run, after, scopes)
    trailing = not after
    if not trailing and not returns:
        return Refusal(name, "the lifted logic binds nothing the rest of the function reads")
    core_name = _core_name(fn.name.value, ordinal)
    if core_name in _module_level_names(module):
        return Refusal(name, f"the core name {core_name} is already taken at module scope")
    core = _build_core(core_name, fn, params, run, returns, trailing)
    call = _build_call(core_name, params, returns, trailing)
    shell = fn.with_changes(body=fn.body.with_changes(body=[*before, call, *after]))
    new_module = _splice(module, fn, shell, core)
    untyped = tuple(p for p, annotation in params if annotation is None)
    lift = Lift(
        name=name,
        core_name=core_name,
        params=tuple(p for p, _a in params),
        returns=returns,
        form="suffix" if trailing else "middle",
        untyped=untyped if trailing else (*untyped, "->"),
    )
    return new_module.code, lift


def _module_level_names(module: cst.Module) -> frozenset[str]:
    names: set[str] = set()
    for stmt in module.body:
        if isinstance(stmt, cst.FunctionDef | cst.ClassDef):
            names.add(stmt.name.value)
    return frozenset(names)


def _parameters(
    fn: cst.FunctionDef,
    before: list[cst.BaseStatement],
    run: list[cst.BaseStatement],
    scopes: object,
) -> list[tuple[str, cst.Annotation | None]]:
    """The names the run reads that the shell bound, in signature order.

    ``ScopeProvider`` resolves each read in the run to the assignment that
    binds it. A read that resolves to an assignment in the shell — a
    parameter of ``fn`` or a statement above the run — is a parameter of
    the core. A read that resolves to an import, a module constant or a
    builtin is not: the core sees those the same way the shell does.
    """
    own = [p.name.value for p in _all_params(fn)]
    bound = _binding_nodes(before) | {id(p) for p in _all_params(fn)}
    needed: list[str] = []
    for node in [n for stmt in run for n in _walk_own(stmt) if isinstance(n, cst.Name)]:
        scope = scopes.get(node)  # type: ignore[attr-defined]
        if scope is None or node.value in needed:
            continue
        for assignment in scope[node.value]:
            if isinstance(assignment, Assignment) and id(assignment.node) in bound:
                needed.append(node.value)
                break
    ordered = [n for n in own if n in needed] + [n for n in needed if n not in own]
    return [(n, _annotation_for(n, fn, before)) for n in ordered]


def _all_params(fn: cst.FunctionDef) -> list[cst.Param]:
    p = fn.params
    return [*p.posonly_params, *p.params, *p.kwonly_params]


def _binding_nodes(stmts: list[cst.BaseStatement]) -> frozenset[int]:
    """Ids of every node in ``stmts`` that can bind a name."""
    ids: set[int] = set()
    for stmt in stmts:
        for node in _walk(stmt):
            if isinstance(node, cst.Name | cst.FunctionDef | cst.ClassDef | cst.Param):
                ids.add(id(node))
    return frozenset(ids)


def _annotation_for(
    target: str, fn: cst.FunctionDef, before: list[cst.BaseStatement]
) -> cst.Annotation | None:
    """The annotation the shell already states for ``target``, if any."""
    for param in _all_params(fn):
        if param.name.value == target:
            return param.annotation
    for stmt in before:
        for node in _walk(stmt):
            if isinstance(node, cst.AnnAssign) and isinstance(node.target, cst.Name):
                if node.target.value == target:
                    return node.annotation
    return None


def _returned(
    run: list[cst.BaseStatement], after: list[cst.BaseStatement], scopes: object
) -> tuple[str, ...]:
    """Names the run binds that the rest of the shell reads, in order."""
    bound = _binding_nodes(run)
    out: list[str] = []
    for node in [n for stmt in after for n in _walk_own(stmt) if isinstance(n, cst.Name)]:
        scope = scopes.get(node)  # type: ignore[attr-defined]
        if scope is None or node.value in out:
            continue
        for assignment in scope[node.value]:
            if isinstance(assignment, Assignment) and id(assignment.node) in bound:
                out.append(node.value)
                break
    return tuple(out)


def _without_leading_blanks(run: list[cst.BaseStatement]) -> list[cst.BaseStatement]:
    """Drop the blank lines that separated the run from the effects above it.

    They were separation inside one body. At the top of the core's own body
    they are a stray blank line the formatter would remove anyway.
    """
    if not run:
        return run
    head = run[0]
    if not isinstance(head, cst.SimpleStatementLine | cst.BaseCompoundStatement):
        return run
    kept = [line for line in head.leading_lines if line.comment is not None]
    return [head.with_changes(leading_lines=kept), *run[1:]]


def _build_core(
    core_name: str,
    fn: cst.FunctionDef,
    params: list[tuple[str, cst.Annotation | None]],
    run: list[cst.BaseStatement],
    returns: tuple[str, ...],
    trailing: bool,
) -> cst.FunctionDef:
    """The lifted core: the run, plus a return of what the shell needs."""
    body = _without_leading_blanks(list(run))
    if not trailing:
        body.append(cst.parse_statement(f"return {_tuple_text(returns)}"))
    signature = ", ".join(
        name
        if annotation is None
        else f"{name}: {cst.Module([]).code_for_node(annotation.annotation)}"
        for name, annotation in params
    )
    suffix = ""
    if trailing and fn.returns is not None:
        suffix = f" -> {cst.Module([]).code_for_node(fn.returns.annotation)}"
    header = cst.parse_statement(f"def {core_name}({signature}){suffix}:\n    pass\n")
    assert isinstance(header, cst.FunctionDef)
    return header.with_changes(body=cst.IndentedBlock(body=body))


def _build_call(
    core_name: str,
    params: list[tuple[str, cst.Annotation | None]],
    returns: tuple[str, ...],
    trailing: bool,
) -> cst.BaseStatement:
    """The statement that replaces the lifted run in the shell."""
    args = ", ".join(name for name, _a in params)
    if trailing:
        return cst.parse_statement(f"return {core_name}({args})")
    return cst.parse_statement(f"{_tuple_text(returns)} = {core_name}({args})")


def _tuple_text(names: tuple[str, ...]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names)


def _splice(
    module: cst.Module, fn: cst.FunctionDef, shell: cst.FunctionDef, core: cst.FunctionDef
) -> cst.Module:
    """Replace ``fn`` with ``shell`` and put ``core`` above its top statement."""
    replaced = module.deep_replace(fn, shell)
    assert isinstance(replaced, cst.Module)
    body: list[cst.BaseStatement] = []
    for index, stmt in enumerate(replaced.body):
        if index == _top_index(module, fn):
            body.append(core.with_changes(leading_lines=[cst.EmptyLine(), cst.EmptyLine()]))
            body.append(stmt)
            continue
        body.append(stmt)
    return replaced.with_changes(body=body)


def _top_index(module: cst.Module, fn: cst.FunctionDef) -> int:
    """Index of the top-level statement that contains ``fn``."""
    for index, stmt in enumerate(module.body):
        if stmt is fn or fn in _walk(stmt):
            return index
    raise AssertionError("the function is not inside this module")
