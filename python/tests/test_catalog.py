"""Tests for catalog-move rules (ASP4xx).

Mirrors the level2/level3 test shape:
``add_lint_rule_tests_to_module`` consumes each rule's
``VALID``/``INVALID`` cases and generates one test method per case.
``Invalid`` cases with ``expected_replacement`` also exercise the
fixit autofix machinery and assert the rewrite matches.
"""

from __future__ import annotations

from fixit.testing import add_lint_rule_tests_to_module

from aspergillus.rules.catalog import (
    EtaReduce,
    FilterFusion,
    MapFusion,
    RedundantConditionalBoolAnd,
    RedundantConditionalBoolOr,
    Tupling,
    WorkerWrapper,
)

add_lint_rule_tests_to_module(
    globals(),
    [
        MapFusion(),
        FilterFusion(),
        EtaReduce(),
        RedundantConditionalBoolOr(),
        RedundantConditionalBoolAnd(),
        Tupling(),
        WorkerWrapper(),
    ],
)
