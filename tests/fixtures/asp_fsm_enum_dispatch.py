"""Fixtures for ASP-FSM-EXHAUSTIVE (asp-26e): enum dispatch shapes.

Each top-level function is one independently-checked scenario, merged into
``python/tests/test_fsm_enum_dispatch_exhaustive.py`` as direct contract
assertions against the ``FsmEnumDispatchExhaustive`` (ASP413) fixit rule.
This module is never imported or executed as a whole — some scenarios below
are exactly the malformed shape the rule exists to reject.
"""

from enum import Enum
from typing import assert_never


class Phase(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"


def no_assert_never_else(phase: Phase) -> str:
    """if/elif enum dispatch with no assert_never else -- REJECTED."""
    if phase == Phase.PENDING:
        return "waiting"
    elif phase == Phase.RUNNING:
        return "working"
    elif phase == Phase.DONE:
        return "finished"
    return "unreachable"


def match_assert_never(phase: Phase) -> str:
    """Same dispatch as a match statement ending in assert_never -- PASSES."""
    match phase:
        case Phase.PENDING:
            return "waiting"
        case Phase.RUNNING:
            return "working"
        case Phase.DONE:
            return "finished"
        case _ as unreachable:
            assert_never(unreachable)


def if_elif_assert_never_else(phase: Phase) -> str:
    """if/elif with else: assert_never(x) -- PASSES."""
    if phase == Phase.PENDING:
        return "waiting"
    elif phase == Phase.RUNNING:
        return "working"
    elif phase == Phase.DONE:
        return "finished"
    else:
        assert_never(phase)


def if_elif_non_enum(status: str) -> str:
    """if/elif over non-enum values -- not flagged."""
    if status == "pending":
        return "waiting"
    elif status == "running":
        return "working"
    return "unknown"
