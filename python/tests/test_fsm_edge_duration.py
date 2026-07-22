"""Tests for ASP412 FsmEdgeDuration (ASP-FSM family; ported from the
standalone ``scripts/check_edge_duration.py`` under pebble ``asp-fd1.2``).

Mirrors the level2/level3/catalog test shape:
``add_lint_rule_tests_to_module`` consumes the rule's ``VALID``/``INVALID``
cases (converted 1:1 from the checker's original ``derived-asp-fef``
acceptance scenarios) and generates one test method per case.
"""

from __future__ import annotations

from fixit.testing import add_lint_rule_tests_to_module

from aspergillus.rules.catalog import FsmEdgeDuration

add_lint_rule_tests_to_module(globals(), [FsmEdgeDuration()])
