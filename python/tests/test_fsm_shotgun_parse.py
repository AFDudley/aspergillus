"""Tests for ASP417 FsmShotgunParse (FSM-verification-integrity family).

Mirrors the catalog-move test shape: ``add_lint_rule_tests_to_module``
consumes the rule's ``VALID``/``INVALID`` cases and generates one test
method per case. Standalone contract tests assert the load-bearing
properties directly, independent of the generated cases:

- a side effect followed by a later rejection, inside one loop body, is
  flagged;
- a side effect (a write to a parameter's attribute) followed by a later
  refusal ``return None`` is flagged;
- a parse-then-act function (every rejection precedes every effect) stays
  silent;
- a pure function with no effect and no rejection stays silent;
- the ``# asp-fsm: boundary-parse`` escape hatch silences a function that
  would otherwise be flagged, matching ASP414's and ASP416's escape hatch
  exactly;
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
# ``unittest.TestCase`` named after the rule class ("FsmShotgunParse") into
# this module's globals, which would otherwise shadow the rule itself.
from aspergillus.rules.catalog import FsmShotgunParse as FsmShotgunParseRule


def _reports(rule: LintRule, code: str) -> list[LintViolation]:
    path = Path.cwd() / "sample.py"
    runner = LintRunner(path, code.encode())
    return list(runner.collect_violations([rule], Config(path=path)))


def test_effect_then_rejection_in_same_loop_body_flagged() -> None:
    """The motivating shape: appending to a sink, then raising on a later,
    invalid element in the same loop body."""
    code = (
        "def process(items, sink):\n"
        "    for item in items:\n"
        "        sink.append(item)\n"
        "        if item < 0:\n"
        '            raise ValueError("negative item")\n'
    )
    flagged = _reports(FsmShotgunParseRule(), code)
    assert len(flagged) == 1, flagged
    assert "ASP417" in flagged[0].message


def test_attribute_write_then_refusal_return_flagged() -> None:
    """A write to a parameter's attribute, then a refusal `return None`
    discovered afterward."""
    code = (
        "def apply(config, value):\n"
        "    config.value = value\n"
        "    if value is None:\n"
        "        return None\n"
    )
    flagged = _reports(FsmShotgunParseRule(), code)
    assert len(flagged) == 1, flagged
    assert "ASP417" in flagged[0].message


def test_parse_then_act_stays_silent() -> None:
    """A first pass rejects every bad element before a second pass acts on
    the now-proven-good input -- every rejection precedes every effect."""
    code = (
        "def process(items, sink):\n"
        "    for item in items:\n"
        "        if item < 0:\n"
        '            raise ValueError("negative item")\n'
        "    for item in items:\n"
        "        sink.append(item)\n"
    )
    assert _reports(FsmShotgunParseRule(), code) == []


def test_pure_function_stays_silent() -> None:
    """No effect and no rejection: nothing to flag."""
    code = "def add(a, b):\n    return a + b\n"
    assert _reports(FsmShotgunParseRule(), code) == []


def test_boundary_marker_silences_an_otherwise_flagged_function() -> None:
    """The rule bites on the shotgun-parse shape, then the
    ``# asp-fsm: boundary-parse`` escape hatch silences the identical
    shape once the marker is present."""
    flagged_code = (
        "def process(items, sink):\n"
        "    for item in items:\n"
        "        sink.append(item)\n"
        "        if item < 0:\n"
        '            raise ValueError("negative item")\n'
    )
    exempt_code = (
        "def process(items, sink):\n"
        "    # asp-fsm: boundary-parse\n"
        "    for item in items:\n"
        "        sink.append(item)\n"
        "        if item < 0:\n"
        '            raise ValueError("negative item")\n'
    )
    flagged = _reports(FsmShotgunParseRule(), flagged_code)
    assert len(flagged) == 1, flagged
    assert "ASP417" in flagged[0].message
    assert _reports(FsmShotgunParseRule(), exempt_code) == []


def test_rule_is_discoverable_by_fixit() -> None:
    """ASP417 must be reachable through fixit's ``aspergillus.rules`` walk --
    the parent-package re-export seam (``rules/__init__.py``). Without it
    the rule is defined but never enforced (the asp-321 gap ASP409 shipped
    with)."""
    cfg = generate_config(Path.cwd() / "sample.py")
    discovered = {type(rule).__name__ for rule in collect_rules(cfg)}
    assert "FsmShotgunParse" in discovered, sorted(discovered)


add_lint_rule_tests_to_module(globals(), [FsmShotgunParseRule()])
