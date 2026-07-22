"""Tests for ASP408 AntiSpecialCasing (gaming detector).

``add_lint_rule_tests_to_module`` consumes the rule's VALID/INVALID
cases and generates one test method per case — this is the red->green
evidence the pebble (``exo-e2f.5``) requires: the snake-gaming stub
(INVALID) is flagged, the real implementation (VALID) is not.

The explicit ``test_snake_stub_flagged_real_not`` below asserts the
same load-bearing pair directly against the rule, independent of the
harness generation, so the contract is legible as a single assertion.
"""

from __future__ import annotations

from pathlib import Path

from fixit.engine import LintRunner
from fixit.ftypes import Config
from fixit.testing import add_lint_rule_tests_to_module

# Aliased: ``add_lint_rule_tests_to_module`` injects a generated
# ``unittest.TestCase`` named ``AntiSpecialCasing`` into this module's
# globals, which would shadow the rule class. Keep a private handle so
# the explicit test below can still instantiate the rule.
from aspergillus.rules.catalog import AntiSpecialCasing as _Rule

add_lint_rule_tests_to_module(globals(), [_Rule()])


def _violations(source: str) -> int:
    """Number of ASP408 reports the rule emits over ``source``."""
    runner = LintRunner(Path("impl.py"), source.encode())
    return len(list(runner.collect_violations([_Rule()], Config())))


SNAKE_GAMING_STUB = (
    "def next_state(board, move):\n"
    '    if move == "UP":\n'
    "        return [[0, 0, 0], [0, 1, 0], [0, 0, 0]]\n"
    "    return board\n"
)

REAL_SNAKE_IMPL = (
    "def next_state(board, move):\n"
    "    head = board[0]\n"
    "    dx, dy = move\n"
    "    new_head = (head[0] + dx, head[1] + dy)\n"
    "    return [new_head, *board[:-1]]\n"
)


def test_snake_stub_flagged_real_not() -> None:
    """The load-bearing contract: the hardcoded-move stub is flagged;
    the computed implementation is clean.
    """
    assert _violations(SNAKE_GAMING_STUB) == 1
    assert _violations(REAL_SNAKE_IMPL) == 0
