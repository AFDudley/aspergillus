"""Tests for ASP409 shell-to-self (verification-integrity family).

Mirrors the catalog-move test shape: ``add_lint_rule_tests_to_module``
consumes the rule's ``VALID``/``INVALID`` cases and generates one test
method per case. A standalone contract test asserts the load-bearing
flag/pass pair directly (own-package ``-m`` FLAGGED, external tool
``git`` NOT flagged), independent of the generated cases.
"""

from __future__ import annotations

from pathlib import Path

from fixit import LintRule
from fixit.engine import LintRunner
from fixit.ftypes import Config, LintViolation
from fixit.testing import add_lint_rule_tests_to_module

# Imported under an alias: ``add_lint_rule_tests_to_module`` injects a
# ``unittest.TestCase`` named after the rule class ("ShellToSelf") into
# this module's globals, which would otherwise shadow the rule itself.
from aspergillus.rules.catalog import ShellToSelf as ShellToSelfRule


def _reports(rule: LintRule, code: str) -> list[LintViolation]:
    path = Path.cwd() / "sample.py"
    runner = LintRunner(path, code.encode())
    return list(runner.collect_violations([rule], Config(path=path)))


def test_own_package_subprocess_flagged_external_not() -> None:
    """The one load-bearing pair, asserted directly.

    Invoking the project's own importable package via a subprocess is
    the smell ASP409 exists to catch; shelling out to an external tool
    (``git``) is legitimate and must stay silent.
    """
    flagged = _reports(
        ShellToSelfRule(),
        'subprocess.run([sys.executable, "-m", "aspergillus", "check"])\n',
    )
    assert len(flagged) == 1, flagged
    assert "ASP409" in flagged[0].message

    clean = _reports(ShellToSelfRule(), 'subprocess.run(["git", "status"])\n')
    assert clean == [], clean


add_lint_rule_tests_to_module(globals(), [ShellToSelfRule()])
