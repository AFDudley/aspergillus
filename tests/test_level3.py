"""Tests for Level 3 NASA rules."""

from __future__ import annotations

from fixit.testing import add_lint_rule_tests_to_module

from aspergillus.rules.level3 import RaiseInsteadOfResult

add_lint_rule_tests_to_module(globals(), [RaiseInsteadOfResult()])
