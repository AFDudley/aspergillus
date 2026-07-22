"""Tests for ASP411 FsmRedundantBranches (verification-integrity family).

Mirrors the catalog-move test shape: ``add_lint_rule_tests_to_module``
consumes the rule's ``VALID``/``INVALID`` cases (ported verbatim from the
standalone checker's fixtures, ``tests/fixtures/asp_fsm_redundant.py``) and
generates one test method per case. Standalone contract tests assert the
load-bearing properties directly, independent of the generated cases:

- identical branch bodies in a match dispatch or if/elif chain fire, and a
  chain where every branch differs stays clean;
- comment/whitespace-only differences between branches still count as
  identical (the rule strips locations and comments before comparing);
- a rename-only difference is deliberately NOT flagged (no alpha-rename);
- a non-Enum dispatch subject with identical branch bodies is out of scope;
- the rule is DISCOVERABLE via fixit's ``aspergillus.rules`` walk (the
  registration seam every enabled rule depends on).
"""

from __future__ import annotations

from pathlib import Path

from fixit import LintRule
from fixit.config import collect_rules, generate_config
from fixit.engine import LintRunner
from fixit.ftypes import Config, LintViolation
from fixit.testing import add_lint_rule_tests_to_module

# Imported under an alias: ``add_lint_rule_tests_to_module`` injects a
# ``unittest.TestCase`` named after the rule class ("FsmRedundantBranches")
# into this module's globals, which would otherwise shadow the rule itself.
from aspergillus.rules.catalog import FsmRedundantBranches as FsmRedundantBranchesRule

_PREAMBLE = (
    "from enum import Enum\n"
    "\n"
    "\n"
    "class Phase(Enum):\n"
    '    PENDING = "pending"\n'
    '    RUNNING = "running"\n'
    '    DONE = "done"\n'
    "\n"
    "\n"
    "class Fail:\n"
    "    def __init__(self, reason: str) -> None:\n"
    "        self.reason = reason\n"
    "\n"
    "\n"
)


def _reports(rule: LintRule, code: str, path: Path | None = None) -> list[LintViolation]:
    file_path = path if path is not None else Path.cwd() / "sample.py"
    runner = LintRunner(file_path, code.encode())
    return list(runner.collect_violations([rule], Config(path=file_path)))


def test_match_dispatch_identical_bodies_flagged() -> None:
    """The load-bearing shape: two ``match`` cases over an enum subject with
    textually identical bodies -- the real PRESERVE/FAIL shape."""
    code = (
        _PREAMBLE + "match phase:\n"
        "    case Phase.PENDING:\n"
        '        return "waiting"\n'
        "    case Phase.RUNNING:\n"
        '        reason = "not ready"\n'
        "        return Fail(reason)\n"
        "    case Phase.DONE:\n"
        '        reason = "not ready"\n'
        "        return Fail(reason)\n"
    )
    flagged = _reports(FsmRedundantBranchesRule(), code)
    assert len(flagged) == 1, flagged
    assert "ASP411" in flagged[0].message


def test_if_elif_chain_genuinely_different_stays_clean() -> None:
    """A chain where every branch does something different must stay
    silent."""
    code = (
        _PREAMBLE + "if phase == Phase.PENDING:\n"
        '    return "waiting"\n'
        "elif phase == Phase.RUNNING:\n"
        '    return "working"\n'
        "elif phase == Phase.DONE:\n"
        '    return "finished"\n'
    )
    assert _reports(FsmRedundantBranchesRule(), code) == []


def test_comment_and_whitespace_only_difference_still_flagged() -> None:
    """Neither source location nor comments survive the normalization, so a
    branch differing only by an extra comment and re-indentation is still
    identical to its sibling."""
    code = (
        _PREAMBLE + "if phase == Phase.PENDING:\n"
        '    reason = "bad state"\n'
        "    return Fail(reason)\n"
        "elif phase == Phase.RUNNING:\n"
        "        # extra comment explaining this branch\n"
        '        reason  =    "bad state"\n'
        "        return Fail(reason)\n"
        "elif phase == Phase.DONE:\n"
        '    return "finished"\n'
    )
    flagged = _reports(FsmRedundantBranchesRule(), code)
    assert len(flagged) == 1, flagged


def test_renamed_variable_not_flagged() -> None:
    """Deliberate no-alpha-rename design choice: two branches that are
    structurally identical but use a different local variable name must NOT
    be flagged -- the rename may be semantically load-bearing."""
    code = (
        _PREAMBLE + "if phase == Phase.PENDING:\n"
        '    reason = "bad state"\n'
        "    return Fail(reason)\n"
        "elif phase == Phase.RUNNING:\n"
        '    cause = "bad state"\n'
        "    return Fail(cause)\n"
        "elif phase == Phase.DONE:\n"
        '    return "finished"\n'
    )
    assert _reports(FsmRedundantBranchesRule(), code) == []


def test_non_enum_dispatch_out_of_scope() -> None:
    """Identical branch bodies over a plain string subject are out of scope
    since the subject isn't Enum-typed."""
    code = (
        _PREAMBLE + 'if status == "pending":\n'
        '    reason = "bad state"\n'
        "    return Fail(reason)\n"
        'elif status == "running":\n'
        '    reason = "bad state"\n'
        "    return Fail(reason)\n"
        "else:\n"
        '    return "finished"\n'
    )
    assert _reports(FsmRedundantBranchesRule(), code) == []


def test_rule_is_discoverable_by_fixit() -> None:
    """ASP411 must be reachable through fixit's ``aspergillus.rules`` walk --
    the parent-package re-export seam (``rules/__init__.py``). Without it the
    rule is defined but never enforced (the gap ASP409 shipped with)."""
    cfg = generate_config(Path.cwd() / "sample.py")
    discovered = {type(rule).__name__ for rule in collect_rules(cfg)}
    assert "FsmRedundantBranches" in discovered, sorted(discovered)


add_lint_rule_tests_to_module(globals(), [FsmRedundantBranchesRule()])
