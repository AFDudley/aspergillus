"""ASP410: in-process construction masquerading as an e2e test.

Verification-integrity family; sibling to ASP408 anti-special-casing and
ASP409 shell-to-self. Where ASP408 guards against special-casing the value
under test and ASP409 guards the *implementation* seam (self-shelling),
ASP410 guards the *test* seam: it flags a test file that constructs the
system-under-test directly IN-PROCESS and drives its loop, then implicitly
claims to be a genuine e2e — the fake-gate shape a real e2e (one crossing a
real subprocess / installed-CLI / network boundary) is supposed to prevent.

Motivation (exophial ``scripts/check_no_inprocess_e2e.py``, pebble
``exo-2b2c`` / generalized in ``asp-6b0``): exophial removed a set of fake
e2e gates that drove its reducer in-process (``Dispatcher(...).tick()`` /
``.dispatch_ready()``) against a scripted stand-in, then attested
``mocks_in_path: false`` while entering the pipeline in the middle. A fake
gate left in the tree is a loaded gun: the next run can re-close a pebble
against it. exophial's standing invariant kept that removal STANDING as a
local stdlib-``ast`` script; this rule lifts the same invariant into the
aspergillus corpus so any consumer with an e2e-test-honesty concern gets it.

The invariant, stated once
--------------------------
A file that BOTH (1) constructs a configured system-under-test class
in-process AND (2) calls a configured loop-drive method is the signature of
an in-process e2e. A genuine e2e drives the SHIPPED artifact across a real
process/CLI/network boundary (``subprocess.run(["mytool", ...])``), so it
never constructs the SUT in its own address space. A file that merely
imports the SUT, names it in a docstring/comment/string, or uses only ONE of
the two call shapes (a unit test of the SUT's core) is NOT an in-process e2e
and is not flagged.

AST, not text (mirrors exophial's exo-8e0)
------------------------------------------
Detection is over the LibCST tree, so only real ``cst.Call`` nodes count. A
docstring, comment, or string literal that merely NAMES ``Dispatcher()`` /
``.tick()`` — e.g. an installed-CLI e2e documenting what it FORBIDS — is
invisible to the invariant.

Configuration (the one real design decision)
--------------------------------------------
exophial's script hardcodes ``Dispatcher`` + ``{tick, dispatch_ready}`` and
scans only ``tests/e2e/``. A corpus rule cannot hardcode one consumer's
symbols, so all three are **overridable class attributes** — the idiomatic
fixit tuning mechanism (cf. ``MAX_LINES`` on ``FunctionTooLong``,
``MIN_ASSERTS`` on ASP202, ``own_package`` on ASP409). A consumer retargets
by subclassing and enabling the subclass::

    class ProjectInProcessE2E(InProcessE2E):
        CONSTRUCT_CLASS_NAMES = frozenset({"MyServer"})
        DRIVE_METHOD_NAMES = frozenset({"serve", "run_once"})
        E2E_PATH_PATTERN = "*/tests/e2e/*"

This is deliberately NOT the ``[tool.aspergillus] extra_io_functions`` TOML
mechanism, which pebble ``asp-b72`` found is inert (referenced as an escape
hatch but never read by any rule); class-attribute-by-subclass is the
mechanism aspergillus rules actually honor.

The **default** configuration reproduces the motivating exophial invariant
(``Dispatcher`` + ``{tick, dispatch_ready}``, all paths) so the rule is
immediately testable and demonstrable; a consumer whose SUT differs overrides
the attributes. Leaving ``CONSTRUCT_CLASS_NAMES`` empty makes the rule a
no-op (nothing to construct) — configure it for your SUT to activate it.

``E2E_PATH_PATTERN`` restricts the check to files whose POSIX path matches
the ``fnmatch`` glob (e.g. ``*/tests/e2e/*``, exophial's own scope). The
default (``""``) matches every file — the rule then fires wherever the
construct+drive pair appears, and the consumer narrows the scope by setting
the pattern.

**Ships without autofix** (Tier 2, detection-only, per
``aspergillus/docs/decisions/2026-05-19-severity-graduation.md`` and
``docs/decisions/2026-05-19-mtm-past-warn-promotion-phase.md``). Lands at
**warn** and promotes to error once a consumer's tree is clean. The fix —
which subprocess / installed-CLI call replaces the in-process construction —
requires human/agent judgment (same category as ASP409's no-autofix
rationale), so the rule reports the opportunity without a ``replacement=``.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

import libcst as cst
from fixit import Invalid, LintRule, Valid
from libcst.metadata import FilePathProvider


class InProcessE2E(LintRule):
    """ASP410: in-process construction of the SUT masquerading as an e2e —
    a real e2e drives the shipped artifact across a process/CLI boundary.

    Detection-only (no autofix); the fix — which real boundary call replaces
    the in-process construction — is human/agent judgment.
    """

    METADATA_DEPENDENCIES = (FilePathProvider,)

    #: Names of system-under-test classes whose IN-PROCESS construction is the
    #: smell. Matched bare (``Dispatcher(...)``) or dotted
    #: (``mod.Dispatcher(...)``). Empty = the rule is a no-op.
    CONSTRUCT_CLASS_NAMES: frozenset[str] = frozenset({"Dispatcher"})

    #: Method names that drive the SUT's loop (``.tick()`` /
    #: ``.dispatch_ready()``). The second half of the in-process-e2e shape.
    DRIVE_METHOD_NAMES: frozenset[str] = frozenset({"tick", "dispatch_ready"})

    #: ``fnmatch`` glob against the file's POSIX path. Only matching files are
    #: checked; ``""`` (default) matches every file. exophial sets
    #: ``"*/tests/e2e/*"`` to reproduce its ``tests/e2e/``-only scope.
    E2E_PATH_PATTERN: str = ""

    MESSAGE = (
        "ASP410: in-process construction masquerading as an e2e — this file "
        "constructs the system-under-test in-process (a configured class) and "
        "calls a loop-drive method on it. A genuine e2e drives the SHIPPED "
        "artifact across a real subprocess / installed-CLI / network boundary; "
        "an in-process construction that attests to be an e2e is a fake gate. "
        "Drive the real boundary, or don't call this an e2e."
    )

    #: Construct-call nodes seen in the current module (report anchors).
    _constructs: list[cst.Call]
    #: Whether a loop-drive call has been seen in the current module.
    _has_drive: bool

    def visit_Module(self, node: cst.Module) -> None:
        # Reset per-file accumulators — a rule instance may be reused across
        # files by the fixit engine.
        self._constructs = []
        self._has_drive = False

    def visit_Call(self, node: cst.Call) -> None:
        if self._is_construct(node):
            self._constructs.append(node)
        elif self._is_drive(node):
            self._has_drive = True

    def leave_Module(self, node: cst.Module) -> None:
        # The in-process-e2e signature is BOTH shapes present in one file.
        if not self._constructs or not self._has_drive:
            return
        if not self._path_matches(node):
            return
        self.report(self._constructs[0], self.MESSAGE)

    def _is_construct(self, node: cst.Call) -> bool:
        """True iff ``node`` constructs a configured SUT class — bare
        ``Dispatcher(...)`` (``cst.Name``) or dotted ``mod.Dispatcher(...)``
        (``cst.Attribute``)."""
        func = node.func
        if isinstance(func, cst.Name):
            return func.value in self.CONSTRUCT_CLASS_NAMES
        if isinstance(func, cst.Attribute):
            return func.attr.value in self.CONSTRUCT_CLASS_NAMES
        return False

    def _is_drive(self, node: cst.Call) -> bool:
        """True iff ``node`` is a method call whose attribute drives the SUT
        loop (``.tick()`` / ``.dispatch_ready()``)."""
        func = node.func
        return isinstance(func, cst.Attribute) and func.attr.value in self.DRIVE_METHOD_NAMES

    def _path_matches(self, node: cst.Module) -> bool:
        """True iff the file's POSIX path matches ``E2E_PATH_PATTERN``; an
        empty pattern matches every file (no path gating)."""
        if not self.E2E_PATH_PATTERN:
            return True
        path = self.get_metadata(FilePathProvider, node)
        return fnmatch.fnmatch(Path(path).as_posix(), self.E2E_PATH_PATTERN)

    VALID = [
        # Construct only — a unit test of the SUT's core, no loop drive.
        Valid("d = Dispatcher(spawn)\nassert d is not None\n"),
        # Loop drive only — no in-process SUT construction (e.g. a real
        # client handle returned by a boundary call).
        Valid("client.tick()\n"),
        # A DIFFERENT class constructed and driven — not a configured SUT.
        Valid("Other(cfg).tick()\n"),
        # The genuine e2e: drive the shipped artifact across a real process
        # boundary. No in-process construction, no loop-drive method.
        Valid('subprocess.run(["exophial", "run", "--once"])\nassert True\n'),
        # AST, not text — naming the forbidden shape in a docstring is
        # invisible to the invariant (an installed-CLI e2e may document it).
        Valid('"""Forbids Dispatcher().tick() in-process."""\nx = 1\n'),
        # Merely importing the SUT is fine.
        Valid("from app import Dispatcher\n"),
    ]
    INVALID = [
        # The load-bearing shape: construct the SUT in-process, drive its loop.
        Invalid("d = Dispatcher(spawn)\nd.tick()\n"),
        # dispatch_ready is the other configured drive method.
        Invalid("d = Dispatcher(spawn)\nd.dispatch_ready()\n"),
        # Dotted construction (``mod.Dispatcher(...)``) + drive.
        Invalid("d = app.Dispatcher(cfg)\nd.tick()\n"),
        # Fluent one-liner: construct and drive in a single expression.
        Invalid("Dispatcher(cfg).tick()\n"),
    ]
