"""Tests for ASP414 FsmStringlyDispatch (FSM-verification-integrity family).

Mirrors the catalog-move test shape: ``add_lint_rule_tests_to_module``
consumes the rule's ``VALID``/``INVALID`` cases (ported from the standalone
ASP-FSM-STRINGLY probe's scenarios) and generates one test method per case.
Standalone contract tests assert the load-bearing
properties directly, independent of the generated cases:

- no same-module Enum -> silent, even with a matching literal shape;
- the ``# asp-fsm: boundary-parse`` escape hatch silences a function even
  though its dispatch otherwise matches;
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
# ``unittest.TestCase`` named after the rule class ("FsmStringlyDispatch")
# into this module's globals, which would otherwise shadow the rule itself.
from aspergillus.rules.catalog import FsmStringlyDispatch as FsmStringlyDispatchRule


def _reports(rule: LintRule, code: str) -> list[LintViolation]:
    path = Path.cwd() / "sample.py"
    runner = LintRunner(path, code.encode())
    return list(runner.collect_violations([rule], Config(path=path)))


def test_no_enum_stays_silent_even_with_matching_literal_shape() -> None:
    """No same-module Enum means nothing for the string literals to shadow —
    the checker's own precondition (``if not enum_values: return []``)."""
    code = 'def route(status):\n    if status == "active":\n        return 1\n    return 0\n'
    assert _reports(FsmStringlyDispatchRule(), code) == []


def test_if_elif_shadowing_enum_flagged() -> None:
    code = (
        "from enum import Enum\n\n\n"
        'class Status(Enum):\n    ACTIVE = "active"\n    IDLE = "idle"\n\n\n'
        "def route(status):\n"
        '    if status == "active":\n'
        "        return 1\n"
        '    elif status == "idle":\n'
        "        return 0\n"
        "    return -1\n"
    )
    flagged = _reports(FsmStringlyDispatchRule(), code)
    assert len(flagged) >= 1, flagged
    assert all("ASP414" in report.message for report in flagged)


def test_boundary_marker_silences_the_function() -> None:
    """The escape hatch: a genuine serialization-boundary parser marked with
    ``# asp-fsm: boundary-parse`` is exempt even though its dispatch shape
    otherwise matches exactly."""
    code = (
        "from enum import Enum\n\n\n"
        'class Status(Enum):\n    ACTIVE = "active"\n    IDLE = "idle"\n\n\n'
        "def parse_status(raw):\n"
        "    # asp-fsm: boundary-parse\n"
        '    if raw == "active":\n'
        "        return Status.ACTIVE\n"
        '    if raw == "idle":\n'
        "        return Status.IDLE\n"
        "    raise ValueError(raw)\n"
    )
    assert _reports(FsmStringlyDispatchRule(), code) == []


def test_match_shadowing_enum_flagged() -> None:
    code = (
        "from enum import Enum\n\n\n"
        'class Status(Enum):\n    ACTIVE = "active"\n    IDLE = "idle"\n\n\n'
        "def route(status):\n"
        "    match status:\n"
        '        case "active":\n'
        "            return 1\n"
        '        case "idle":\n'
        "            return 0\n"
    )
    flagged = _reports(FsmStringlyDispatchRule(), code)
    assert len(flagged) >= 1, flagged
    assert all("ASP414" in report.message for report in flagged)


def test_dispatch_on_enum_member_itself_clean() -> None:
    """Dispatching on the Enum member (not a stringly-typed shadow of it) is
    exactly the fix this rule prescribes — it must stay silent."""
    code = (
        "from enum import Enum\n\n\n"
        'class Status(Enum):\n    ACTIVE = "active"\n    IDLE = "idle"\n\n\n'
        "def route(status: Status):\n"
        "    match status:\n"
        "        case Status.ACTIVE:\n"
        "            return 1\n"
        "        case Status.IDLE:\n"
        "            return 0\n"
    )
    assert _reports(FsmStringlyDispatchRule(), code) == []


def test_rule_is_discoverable_by_fixit() -> None:
    """ASP414 must be reachable through fixit's ``aspergillus.rules`` walk —
    the parent-package re-export seam (``rules/__init__.py``). Without it the
    rule is defined but never enforced (the asp-321 gap ASP409 shipped
    with)."""
    cfg = generate_config(Path.cwd() / "sample.py")
    discovered = {type(rule).__name__ for rule in collect_rules(cfg)}
    assert "FsmStringlyDispatch" in discovered, sorted(discovered)


add_lint_rule_tests_to_module(globals(), [FsmStringlyDispatchRule()])
