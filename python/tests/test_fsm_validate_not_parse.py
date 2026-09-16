"""Tests for ASP416 FsmValidateNotParse (FSM-verification-integrity family).

Mirrors the catalog-move test shape: ``add_lint_rule_tests_to_module``
consumes the rule's ``VALID``/``INVALID`` cases and generates one test
method per case. Standalone contract tests assert the load-bearing
properties directly, independent of the generated cases:

- a validating signature (return type unions in one of its own parameter
  types) is flagged;
- the ``# asp-fsm: boundary-parse`` escape hatch silences a function that
  would otherwise be flagged, matching ASP414's escape hatch exactly;
- a true parser (return type appears in no parameter) and a bare,
  non-union transform both stay silent;
- the rule is DISCOVERABLE via fixit's ``aspergillus.rules`` walk (the
  registration seam every enabled rule depends on, per the asp-321 lesson
  from ASP410/asp-6b0: an un-re-exported rule exists in source but never
  actually runs).
"""

from __future__ import annotations

from pathlib import Path

from fixit import LintRule
from fixit.config import collect_rules, generate_config
from fixit.engine import LintRunner
from fixit.ftypes import Config, LintViolation
from fixit.testing import add_lint_rule_tests_to_module

# Imported under an alias: ``add_lint_rule_tests_to_module`` injects a
# ``unittest.TestCase`` named after the rule class ("FsmValidateNotParse")
# into this module's globals, which would otherwise shadow the rule itself.
from aspergillus.rules.catalog import FsmValidateNotParse as FsmValidateNotParseRule


def _reports(rule: LintRule, code: str) -> list[LintViolation]:
    path = Path.cwd() / "sample.py"
    runner = LintRunner(path, code.encode())
    return list(runner.collect_violations([rule], Config(path=path)))


def test_success_arm_equal_to_parameter_type_flagged() -> None:
    """The core trigger: the return union's success arm (`str`) is
    type-equal to the sole parameter's annotation (`str`)."""
    code = "def f(x: str) -> str | None:\n    return x if x else None\n"
    flagged = _reports(FsmValidateNotParseRule(), code)
    assert len(flagged) == 1, flagged
    assert "ASP416" in flagged[0].message


def test_boundary_marker_silences_an_otherwise_flagged_function() -> None:
    """The rule bites on the validate-not-parse shape, then the
    ``# asp-fsm: boundary-parse`` escape hatch silences the identical
    shape once the marker is present."""
    flagged_code = "def f(x: str) -> str | None:\n    return x if x else None\n"
    exempt_code = (
        "def f(x: str) -> str | None:\n    # asp-fsm: boundary-parse\n    return x if x else None\n"
    )
    flagged = _reports(FsmValidateNotParseRule(), flagged_code)
    assert len(flagged) == 1, flagged
    assert "ASP416" in flagged[0].message
    assert _reports(FsmValidateNotParseRule(), exempt_code) == []


def test_parser_returning_a_type_in_no_parameter_stays_silent() -> None:
    """A true parser: its return type appears in none of its parameters, so
    no union arm can match — nothing to flag."""
    code = "class Parsed: ...\n\n\ndef parse(x: str) -> Parsed: ...\n"
    assert _reports(FsmValidateNotParseRule(), code) == []


def test_bare_non_union_return_stays_silent() -> None:
    """A bare, non-union return has no rejection arm, so it's a transform,
    not a validation — the checker's own precondition."""
    code = "def transform(x: int) -> int: ...\n"
    assert _reports(FsmValidateNotParseRule(), code) == []


def test_rule_is_discoverable_by_fixit() -> None:
    """ASP416 must be reachable through fixit's ``aspergillus.rules`` walk —
    the parent-package re-export seam (``rules/__init__.py``). Without it the
    rule is defined but never enforced (the asp-321 gap ASP409 shipped
    with)."""
    cfg = generate_config(Path.cwd() / "sample.py")
    discovered = {type(rule).__name__ for rule in collect_rules(cfg)}
    assert "FsmValidateNotParse" in discovered, sorted(discovered)


add_lint_rule_tests_to_module(globals(), [FsmValidateNotParseRule()])
