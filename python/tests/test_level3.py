"""Tests for Level 3 NASA rules."""

from __future__ import annotations

from fixit.testing import add_lint_rule_tests_to_module

from aspergillus.rules.level3 import (
    ErrorSwallowedIntoSentinel,
    FailureDiscardsEvidence,
    OptionalReturnType,
)

# ASP301 (RaiseInsteadOfResult) retired for Python — pebble asp-80c.
# The regression that an idiomatic guard-raise-then-return function is
# NOT flagged is pinned by the guard-raise-return VALID fixtures on the
# two surviving L3 rules (OptionalReturnType / ASP302 and
# ErrorSwallowedIntoSentinel / ASP303) in level3.py — with ASP301 gone,
# no L3 rule reports that pattern.
add_lint_rule_tests_to_module(
    globals(),
    [
        OptionalReturnType(),
        ErrorSwallowedIntoSentinel(),
        FailureDiscardsEvidence(),
    ],
)
