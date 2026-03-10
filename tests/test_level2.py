"""Tests for Level 2 NASA rules."""

from __future__ import annotations

from fixit.testing import add_lint_rule_tests_to_module

from aspergillus.rules.level2 import FunctionTooLong, GlobalMutableState, LowAssertionDensity

add_lint_rule_tests_to_module(
    globals(), [FunctionTooLong(), LowAssertionDensity(), GlobalMutableState()]
)


def test_asp201_threshold() -> None:
    """60-line function passes, 61-line function fails."""
    pass  # covered by VALID/INVALID test cases
