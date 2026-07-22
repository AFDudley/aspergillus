"""Tests for ASP413 FSM enum dispatch exhaustiveness (verification-integrity
family).

Mirrors the catalog-move test shape: ``add_lint_rule_tests_to_module``
consumes the rule's ``VALID``/``INVALID`` cases and generates one test method
per case. The four standalone scenario tests below are the merged fixtures
from ``tests/fixtures/asp_fsm_enum_dispatch.py``, converted into direct
contract assertions against the real fixit rule.
"""

from __future__ import annotations

from pathlib import Path

from fixit import LintRule
from fixit.config import collect_rules, generate_config
from fixit.engine import LintRunner
from fixit.ftypes import Config, LintViolation
from fixit.testing import add_lint_rule_tests_to_module

# Imported under an alias: ``add_lint_rule_tests_to_module`` injects a
# ``unittest.TestCase`` named after the rule class
# ("FsmEnumDispatchExhaustive") into this module's globals, which would
# otherwise shadow the rule itself.
from aspergillus.rules.catalog import (
    FsmEnumDispatchExhaustive as FsmEnumDispatchExhaustiveRule,
)

_ENUM_PREAMBLE = "from enum import Enum\n\n\nclass Phase(Enum):\n    PENDING = 'pending'\n    RUNNING = 'running'\n    DONE = 'done'\n\n\n"
_ASSERT_NEVER_IMPORT = "from typing import assert_never\n\n"


def _reports(rule: LintRule, code: str) -> list[LintViolation]:
    path = Path.cwd() / "sample.py"
    runner = LintRunner(path, code.encode())
    return list(runner.collect_violations([rule], Config(path=path)))


def test_no_assert_never_else_flagged() -> None:
    """Fixture scenario ``no_assert_never_else``: if/elif enum dispatch that
    falls through to a plain trailing return, with no ``assert_never``-guarded
    else -- REJECTED."""
    code = (
        _ENUM_PREAMBLE + "def no_assert_never_else(phase: Phase) -> str:\n"
        "    if phase == Phase.PENDING:\n"
        "        return 'waiting'\n"
        "    elif phase == Phase.RUNNING:\n"
        "        return 'working'\n"
        "    elif phase == Phase.DONE:\n"
        "        return 'finished'\n"
        "    return 'unreachable'\n"
    )
    flagged = _reports(FsmEnumDispatchExhaustiveRule(), code)
    assert len(flagged) == 1, flagged
    assert "ASP413" in flagged[0].message


def test_match_assert_never_clean() -> None:
    """Fixture scenario ``match_assert_never``: the same dispatch as a
    ``match`` statement ending in ``assert_never`` -- PASSES (a ``match`` is
    never flagged; it is already the exhaustiveness-checkable form)."""
    code = (
        _ASSERT_NEVER_IMPORT + _ENUM_PREAMBLE + "def match_assert_never(phase: Phase) -> str:\n"
        "    match phase:\n"
        "        case Phase.PENDING:\n"
        "            return 'waiting'\n"
        "        case Phase.RUNNING:\n"
        "            return 'working'\n"
        "        case Phase.DONE:\n"
        "            return 'finished'\n"
        "        case _ as unreachable:\n"
        "            assert_never(unreachable)\n"
    )
    assert _reports(FsmEnumDispatchExhaustiveRule(), code) == []


def test_if_elif_assert_never_else_clean() -> None:
    """Fixture scenario ``if_elif_assert_never_else``: if/elif with
    ``else: assert_never(x)`` -- PASSES."""
    code = (
        _ASSERT_NEVER_IMPORT
        + _ENUM_PREAMBLE
        + "def if_elif_assert_never_else(phase: Phase) -> str:\n"
        "    if phase == Phase.PENDING:\n"
        "        return 'waiting'\n"
        "    elif phase == Phase.RUNNING:\n"
        "        return 'working'\n"
        "    elif phase == Phase.DONE:\n"
        "        return 'finished'\n"
        "    else:\n"
        "        assert_never(phase)\n"
    )
    assert _reports(FsmEnumDispatchExhaustiveRule(), code) == []


def test_if_elif_non_enum_clean() -> None:
    """Fixture scenario ``if_elif_non_enum``: if/elif over non-enum values --
    not flagged (out of scope entirely)."""
    code = (
        "def if_elif_non_enum(status: str) -> str:\n"
        "    if status == 'pending':\n"
        "        return 'waiting'\n"
        "    elif status == 'running':\n"
        "        return 'working'\n"
        "    return 'unknown'\n"
    )
    assert _reports(FsmEnumDispatchExhaustiveRule(), code) == []


def test_rule_is_discoverable_by_fixit() -> None:
    """ASP413 must be reachable through fixit's ``aspergillus.rules`` walk --
    the parent-package re-export seam (``rules/__init__.py``). Without it the
    rule is defined but never enforced."""
    cfg = generate_config(Path.cwd() / "sample.py")
    discovered = {type(rule).__name__ for rule in collect_rules(cfg)}
    assert "FsmEnumDispatchExhaustive" in discovered, sorted(discovered)


add_lint_rule_tests_to_module(globals(), [FsmEnumDispatchExhaustiveRule()])
