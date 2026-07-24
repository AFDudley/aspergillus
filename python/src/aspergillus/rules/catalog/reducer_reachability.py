"""ASP415: reducer/daemon-start reachable from test or script code outside
the container fixture.

Verification-integrity family; sibling to ASP408 anti-special-casing, ASP409
shell-to-self, and ASP410 in-process-e2e. Where ASP410 flags a test that
constructs its SUT in-process and drives it, ASP415 flags a narrower and more
dangerous shape: a test or script file that reaches a call which starts a
REAL, long-lived reducer/daemon process, with no sanctioned container fixture
between the call and the file's top level.

Motivation (exophial 2026-07-24): two of exophial's acceptance probes started
a real ``exophiald`` reducer on the HOST — via ``run_cli_dispatch(repo,
pebble_id, ...)`` inside a ``tempfile.TemporaryDirectory()`` — instead of the
project's own container e2e harness (an image that runs the reducer in an
isolated container and reaps it on container exit). When the owning session
died, one such probe orphaned: a host reducer holding a host
``.exophial/exophiald.lock`` plus a poller stuck in a sleep loop, reparented
to ``systemd --user``, running ~37h with no reaper, leaving an uncleaned
``/tmp`` temp repo. A ``timeout 60`` wrapper could not kill it (no ``-k`` /
``SIGTERM`` ignored). A runtime guard in the daemon's own start path (``if
PYTEST_CURRENT_TEST: raise``) would be test logic leaking into the production
reducer path AND bypassable (subprocess the CLI, construct the dispatcher
directly) — a tripwire, not enforcement. This rule instead rejects the
pattern at the commit boundary, entirely in the lint layer, touching no
production code.

Configuration (the one real design decision, cf. ASP410's
``CONSTRUCT_CLASS_NAMES`` / ``DRIVE_METHOD_NAMES``)
----------------------------------------------------
A consumer's reducer-start symbols, watched paths, and exemption markers are
never aspergillus's to hardcode, so every one of them is an overridable class
attribute — the idiomatic fixit tuning mechanism this pack already uses.
A consumer retargets by subclassing::

    class ProjectReducerReachability(ReducerReachability):
        WATCHED_PATH_PATTERNS = frozenset({"*/e2e_probes/*"})
        REACHABLE_CALLS = frozenset({"boot_worker", "supervisor.launch"})
        CONSTRUCT_CLASS_NAMES = frozenset({"Supervisor"})
        DRIVE_METHOD_NAMES = frozenset({"serve"})
        SUBPROCESS_DOTTED_NAMES = frozenset({"subprocess.run", "subprocess.Popen"})
        SUBPROCESS_ARGV_MARKERS = frozenset({"myworkerd"})
        EXEMPTION_DECORATORS = frozenset({"requires_container_worker"})
        EXEMPTION_IMPORT_MODULES = frozenset({"container_harness"})

The **default** configuration reproduces the motivating exophial invariant's
symbol/marker/exemption names (``run_cli_dispatch``; ``daemon.start`` /
``dispatcher.run`` dotted calls; the ``Dispatcher(...).run()`` fluent
construct+drive shape; ``subprocess.run`` / ``Popen`` whose argv contains a
dispatch/daemon marker; exempted by ``@requires_container_reducer`` or an
import of a ``container_harness`` module) so the rule is immediately
testable and demonstrable. ``WATCHED_PATH_PATTERNS`` defaults to EMPTY,
which means "no path restriction — every file is in scope" (mirroring
ASP410's ``E2E_PATH_PATTERN`` default of ``""``, its own "match everything"
convention) rather than exophial's real ``tests/**`` / ``scripts/**``
narrowing; a consumer narrows scope by setting it, exactly as exophial's own
config does. This is the opposite convention from the symbol-set attributes
below (``REACHABLE_CALLS`` etc.), where empty means "no-op, matches
nothing" — each field states its own empty-value semantics.

Detection shape
----------------
A file is IN SCOPE if its POSIX path matches any ``WATCHED_PATH_PATTERNS``
glob. Within an in-scope file, a call reaches a reducer/daemon start if it is
ANY of:

1. A bare or dotted call whose reconstructed dotted name (``Name``/
   ``Attribute`` chains only) equals, or ends at a ``.`` boundary with, an
   entry in ``REACHABLE_CALLS`` (``run_cli_dispatch``; ``daemon.start``;
   ``dispatcher.run``).
2. The fluent one-liner ``ConstructClass(...).drive_method()`` — a call whose
   func is an ``Attribute`` on a ``Call`` to a configured
   ``CONSTRUCT_CLASS_NAMES`` entry, with an attr in ``DRIVE_METHOD_NAMES``.
3. A call to a configured ``SUBPROCESS_DOTTED_NAMES`` entry (``subprocess.run``
   / ``subprocess.Popen``) whose arguments contain a string literal
   substring-matching a configured ``SUBPROCESS_ARGV_MARKERS`` entry.

A matched call is exempt — not reported — if EITHER:

- it lexically nests inside a ``def`` (at any depth) whose decorator list
  names a configured ``EXEMPTION_DECORATORS`` entry, or
- the enclosing file imports a module whose dotted name equals, or ends at a
  ``.`` boundary with, a configured ``EXEMPTION_IMPORT_MODULES`` entry (the
  sanctioned container-harness fixture module) — this exempts the whole file.

AST, not text: only real ``cst.Call`` / ``cst.Decorator`` / ``cst.Import``
nodes count, mirroring ASP410's AST-not-text discipline (exo-8e0).

HONEST LIMIT: static reachability has the usual holes — dynamic dispatch,
aliased imports (``import subprocess as sp``), string-built argv are
invisible to this rule. Acceptable: the probes this rule exists to prevent
write the call straightforwardly, so the rule catches honest code, which is
the regression vector.

**Ships without autofix** (Tier 2, detection-only, per
``docs/decisions/2026-05-19-mtm-past-warn-promotion-phase.md``). The fix —
which container fixture replaces the bare call — is human/agent judgment.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

import libcst as cst
from fixit import Invalid, LintRule, Valid
from libcst.metadata import FilePathProvider


def _dotted_string(node: cst.BaseExpression) -> str | None:
    """The dotted ``a.b.c`` string for a pure ``Name``/``Attribute`` chain,
    else ``None`` (e.g. the base is a ``Call``, as in ``Dispatcher(...).run``,
    which is handled separately by the construct+drive shape)."""
    if isinstance(node, cst.Name):
        return node.value
    if isinstance(node, cst.Attribute):
        base = _dotted_string(node.value)
        if base is None:
            return None
        return f"{base}.{node.attr.value}"
    return None


def _matches_dotted_suffix(dotted: str, configured: frozenset[str]) -> bool:
    """True iff ``dotted`` equals, or ends at a ``.`` boundary with, any
    entry in ``configured`` (so ``daemon.start`` matches both bare
    ``daemon.start(...)`` and dotted ``exophial.daemon.start(...)``)."""
    return any(dotted == entry or dotted.endswith(f".{entry}") for entry in configured)


def _iter_string_literals(node: cst.BaseExpression) -> list[str]:
    """String literal values reachable from ``node`` — the node itself, or
    (recursively) elements of a ``List``/``Tuple`` literal — covering both
    ``subprocess.run("exophiald")`` and ``subprocess.run(["exophiald", ...])``."""
    if isinstance(node, (cst.SimpleString, cst.ConcatenatedString)):
        value = node.evaluated_value
        return [value] if isinstance(value, str) else []
    if isinstance(node, (cst.List, cst.Tuple)):
        literals: list[str] = []
        for element in node.elements:
            literals.extend(_iter_string_literals(element.value))
        return literals
    return []


class ReducerReachability(LintRule):
    """ASP415: a test/script file reaches a reducer/daemon-start call with no
    sanctioned container fixture between the call and the file's top level.

    Detection-only (no autofix); the fix — which container fixture replaces
    the bare call — is human/agent judgment.
    """

    METADATA_DEPENDENCIES = (FilePathProvider,)

    #: ``fnmatch`` globs against the file's POSIX path; a file is in scope if
    #: it matches ANY entry. Empty (default) = no restriction, every file is
    #: in scope. A consumer narrows scope by setting this (exophial's own
    #: value: ``frozenset({"*/tests/*", "*/scripts/*"})``).
    WATCHED_PATH_PATTERNS: frozenset[str] = frozenset()

    #: Dotted-suffix call names that directly start a reducer/daemon (bare
    #: function calls or ``module.func`` / ``obj.method`` calls whose base is
    #: a ``Name``/``Attribute`` chain, not a ``Call``).
    REACHABLE_CALLS: frozenset[str] = frozenset(
        {"run_cli_dispatch", "daemon.start", "dispatcher.run"}
    )

    #: Class names whose in-process construction, immediately followed by a
    #: ``DRIVE_METHOD_NAMES`` call in the same expression (``Dispatcher(...)
    #: .run()``), is the fluent construct+drive reducer-start shape.
    CONSTRUCT_CLASS_NAMES: frozenset[str] = frozenset({"Dispatcher"})

    #: Method names that, called fluently on a ``CONSTRUCT_CLASS_NAMES``
    #: construction, drive the reducer/daemon.
    DRIVE_METHOD_NAMES: frozenset[str] = frozenset({"run"})

    #: Dotted-suffix subprocess entry points checked for a daemon-launching
    #: argv (``subprocess.run`` / ``subprocess.Popen``).
    SUBPROCESS_DOTTED_NAMES: frozenset[str] = frozenset({"subprocess.run", "subprocess.Popen"})

    #: Substrings that, found in any string-literal argument to a
    #: ``SUBPROCESS_DOTTED_NAMES`` call, mark it as launching the reducer/daemon.
    SUBPROCESS_ARGV_MARKERS: frozenset[str] = frozenset(
        {"exophial dispatch", "exophiald", "exophial start"}
    )

    #: Decorator names that exempt every call lexically nested (at any depth)
    #: inside the decorated function — the sanctioned container fixture marker.
    EXEMPTION_DECORATORS: frozenset[str] = frozenset({"requires_container_reducer"})

    #: Dotted-suffix module names whose import exempts the WHOLE file (the
    #: known container-harness fixture module).
    EXEMPTION_IMPORT_MODULES: frozenset[str] = frozenset({"container_harness"})

    MESSAGE = (
        "ASP415: reducer/daemon-start reachable outside the container fixture "
        "— this file calls a configured reducer/daemon-start symbol with no "
        "sanctioned container fixture (decorator or harness import) guarding "
        "it. A bare host-started reducer can orphan (no reaper, holds a host "
        "lock) if the owning process dies. Route this through the container "
        "e2e fixture instead."
    )

    #: Whether the current file's path matches ``WATCHED_PATH_PATTERNS``.
    _in_scope: bool
    #: Whether the whole file is exempt via a container-harness import.
    _file_exempt: bool
    #: Count of enclosing ``def``s (innermost first) carrying an exemption
    #: decorator; a call is exempt while this is > 0.
    _exempt_depth: int

    def visit_Module(self, node: cst.Module) -> None:
        # Reset per-file state -- a rule instance may be reused across files.
        self._in_scope = self._path_matches(node)
        self._file_exempt = False
        self._exempt_depth = 0

    def visit_Import(self, node: cst.Import) -> None:
        for alias in node.names:
            dotted = _dotted_string(alias.name)
            if dotted and _matches_dotted_suffix(dotted, self.EXEMPTION_IMPORT_MODULES):
                self._file_exempt = True

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        module = node.module
        dotted = _dotted_string(module) if module is not None else None
        if dotted and _matches_dotted_suffix(dotted, self.EXEMPTION_IMPORT_MODULES):
            self._file_exempt = True

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        if self._has_exemption_decorator(node):
            self._exempt_depth += 1

    def leave_FunctionDef(self, node: cst.FunctionDef) -> None:
        if self._has_exemption_decorator(node):
            self._exempt_depth -= 1

    def visit_Call(self, node: cst.Call) -> None:
        if not self._in_scope or self._file_exempt or self._exempt_depth > 0:
            return
        if (
            self._is_reachable_call(node)
            or self._is_fluent_construct_drive(node)
            or self._is_marked_subprocess(node)
        ):
            self.report(node, self.MESSAGE)

    def _has_exemption_decorator(self, node: cst.FunctionDef) -> bool:
        for decorator in node.decorators:
            dotted = _dotted_string(decorator.decorator)
            if dotted is not None and dotted.split(".")[-1] in self.EXEMPTION_DECORATORS:
                return True
        return False

    def _is_reachable_call(self, node: cst.Call) -> bool:
        dotted = _dotted_string(node.func)
        return dotted is not None and _matches_dotted_suffix(dotted, self.REACHABLE_CALLS)

    def _is_fluent_construct_drive(self, node: cst.Call) -> bool:
        func = node.func
        if not isinstance(func, cst.Attribute) or func.attr.value not in self.DRIVE_METHOD_NAMES:
            return False
        inner = func.value
        if not isinstance(inner, cst.Call):
            return False
        inner_name = _dotted_string(inner.func)
        return inner_name is not None and inner_name.split(".")[-1] in self.CONSTRUCT_CLASS_NAMES

    def _is_marked_subprocess(self, node: cst.Call) -> bool:
        dotted = _dotted_string(node.func)
        if dotted is None or not _matches_dotted_suffix(dotted, self.SUBPROCESS_DOTTED_NAMES):
            return False
        literals: list[str] = []
        for arg in node.args:
            literals.extend(_iter_string_literals(arg.value))
        return any(
            marker in literal for literal in literals for marker in self.SUBPROCESS_ARGV_MARKERS
        )

    def _path_matches(self, node: cst.Module) -> bool:
        if not self.WATCHED_PATH_PATTERNS:
            return True
        path = self.get_metadata(FilePathProvider, node)
        posix_path = Path(path).as_posix()
        return any(fnmatch.fnmatch(posix_path, pattern) for pattern in self.WATCHED_PATH_PATTERNS)

    VALID = [
        # A call that isn't any of the three reachable shapes.
        Valid("other_thing()\n"),
        # Guarded by the sanctioned decorator.
        Valid(
            "@requires_container_reducer\ndef test_x():\n    run_cli_dispatch('repo', 'pebble')\n"
        ),
        # Guarded by the container-harness import (whole file exempt).
        Valid(
            "from tests.e2e.container_harness import spawn\n\n\n"
            "def test_x():\n    run_cli_dispatch('repo', 'pebble')\n"
        ),
        # Construct without the drive method -- not the fluent shape.
        Valid("Dispatcher(spawn)\n"),
        # A DIFFERENT class's fluent call -- not a configured construct.
        Valid("Other(cfg).run()\n"),
        # subprocess.run with no daemon-launching argv marker.
        Valid("subprocess.run(['ls', '-la'])\n"),
        # Naming the forbidden call in a docstring is invisible (AST, not text).
        Valid('"""Forbids run_cli_dispatch() bare."""\nx = 1\n'),
    ]
    INVALID = [
        # The load-bearing shape: a bare reachable call.
        Invalid("run_cli_dispatch('repo', 'pebble')\n"),
        # Dotted reachable call (module-qualified daemon.start).
        Invalid("exophial.daemon.start(repo)\n"),
        # Bare-variable drive call (dispatcher.run), the other dotted entry.
        Invalid("dispatcher.run()\n"),
        # The fluent construct+drive one-liner.
        Invalid("Dispatcher(cfg).run()\n"),
        # subprocess.run whose argv carries a daemon-launching marker.
        Invalid("subprocess.run(['exophiald', '--once'])\n"),
    ]
