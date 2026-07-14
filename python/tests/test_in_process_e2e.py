"""Tests for ASP410 in-process-e2e (verification-integrity family).

Mirrors the catalog-move test shape: ``add_lint_rule_tests_to_module``
consumes the rule's ``VALID``/``INVALID`` cases and generates one test
method per case. Standalone contract tests assert the load-bearing
properties directly, independent of the generated cases:

- the construct+drive pair FIRES, construct-only / drive-only stays clean;
- ``E2E_PATH_PATTERN`` gates by file path;
- the SUT symbols are CONFIGURABLE (a subclass retargets them), so the rule
  is not hardcoded to exophial's ``Dispatcher``;
- the rule is DISCOVERABLE via fixit's ``aspergillus.rules`` walk (the
  registration seam every enabled rule depends on).
"""

from __future__ import annotations

from pathlib import Path

from fixit import LintRule
from fixit.config import collect_rules, generate_config
from fixit.engine import LintRunner
from fixit.ftypes import Config, LintViolation
from fixit.testing import add_lint_rule_tests_to_module

# Imported under an alias: ``add_lint_rule_tests_to_module`` injects a
# ``unittest.TestCase`` named after the rule class ("InProcessE2E") into
# this module's globals, which would otherwise shadow the rule itself.
from aspergillus.rules.catalog import InProcessE2E as InProcessE2ERule


def _reports(rule: LintRule, code: str, path: Path | None = None) -> list[LintViolation]:
    file_path = path if path is not None else Path.cwd() / "sample.py"
    runner = LintRunner(file_path, code.encode())
    return list(runner.collect_violations([rule], Config(path=file_path)))


def test_construct_and_drive_flagged_construct_only_clean() -> None:
    """The load-bearing pair, asserted directly.

    Constructing the SUT in-process AND driving its loop is the in-process-e2e
    shape ASP410 exists to catch; constructing without a loop drive (a unit
    test of the SUT's core) is legitimate and must stay silent.
    """
    flagged = _reports(InProcessE2ERule(), "d = Dispatcher(spawn)\nd.tick()\n")
    assert len(flagged) == 1, flagged
    assert "ASP410" in flagged[0].message

    clean = _reports(InProcessE2ERule(), "d = Dispatcher(spawn)\nassert d is not None\n")
    assert clean == [], clean


def test_drive_only_clean() -> None:
    """A loop-drive method on a handle that was NOT constructed in-process
    (e.g. returned by a real boundary call) is not the smell."""
    assert _reports(InProcessE2ERule(), "client.tick()\n") == []


def test_real_subprocess_boundary_clean() -> None:
    """A genuine e2e drives the shipped artifact across a process boundary —
    no in-process construction — and must stay silent."""
    assert _reports(InProcessE2ERule(), 'subprocess.run(["exophial", "run"])\n') == []


def test_named_in_docstring_not_flagged() -> None:
    """AST, not text (exo-8e0): naming ``Dispatcher().tick()`` in a docstring
    is invisible to the invariant — only real ``cst.Call`` nodes count."""
    code = '"""An installed-CLI e2e must not do Dispatcher().tick()."""\nx = 1\n'
    assert _reports(InProcessE2ERule(), code) == []


def test_e2e_path_pattern_gates_by_path() -> None:
    """``E2E_PATH_PATTERN`` restricts the check to matching paths: the same
    violating content fires under ``tests/e2e/`` and stays clean elsewhere."""

    class ScopedInProcessE2E(InProcessE2ERule):
        E2E_PATH_PATTERN = "*/tests/e2e/*"

    code = "d = Dispatcher(spawn)\nd.tick()\n"
    root = Path.cwd()

    under_e2e = _reports(ScopedInProcessE2E(), code, root / "tests" / "e2e" / "test_flow.py")
    assert len(under_e2e) == 1, under_e2e

    outside_e2e = _reports(ScopedInProcessE2E(), code, root / "tests" / "unit" / "test_core.py")
    assert outside_e2e == [], outside_e2e


def test_construct_and_drive_names_are_configurable() -> None:
    """The SUT symbols are consumer config, not hardcoded to exophial's
    ``Dispatcher``: a subclass retargets them, and under that config the
    default ``Dispatcher`` shape no longer fires while the new one does."""

    class ServerInProcessE2E(InProcessE2ERule):
        CONSTRUCT_CLASS_NAMES = frozenset({"Server"})
        DRIVE_METHOD_NAMES = frozenset({"serve"})

    fires = _reports(ServerInProcessE2E(), "s = Server(cfg)\ns.serve()\n")
    assert len(fires) == 1, fires

    # exophial's default shape is not this consumer's SUT -> silent.
    assert _reports(ServerInProcessE2E(), "d = Dispatcher(spawn)\nd.tick()\n") == []


def test_rule_is_discoverable_by_fixit() -> None:
    """ASP410 must be reachable through fixit's ``aspergillus.rules`` walk —
    the parent-package re-export seam (``rules/__init__.py``). Without it the
    rule is defined but never enforced (the gap ASP409 shipped with)."""
    cfg = generate_config(Path.cwd() / "sample.py")
    discovered = {type(rule).__name__ for rule in collect_rules(cfg)}
    assert "InProcessE2E" in discovered, sorted(discovered)


add_lint_rule_tests_to_module(globals(), [InProcessE2ERule()])
