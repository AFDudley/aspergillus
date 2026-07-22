"""Fixtures for ASP-FSM-REDUNDANT (asp-5a8): redundant-branch dispatch shapes.

Each top-level function is one independently-checked scenario, merged into
``python/tests/test_fsm_redundant_branches.py`` as direct contract
assertions against the ``FsmRedundantBranches`` (ASP411) fixit rule. This
module is never imported or executed as a whole -- some scenarios below are
exactly the malformed shape the rule exists to flag.
"""

from enum import Enum


class Phase(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"


class Fail:
    def __init__(self, reason: str) -> None:
        self.reason = reason


def redundant_identical_bodies(phase: Phase):
    """match dispatch where RUNNING and DONE are both literally
    ``Fail(reason)`` -- the real PRESERVE/FAIL shape -- WARNED."""
    match phase:
        case Phase.PENDING:
            return "waiting"
        case Phase.RUNNING:
            reason = "not ready"
            return Fail(reason)
        case Phase.DONE:
            reason = "not ready"
            return Fail(reason)


def redundant_comment_whitespace_diff(phase: Phase):
    """if/elif dispatch where PENDING and RUNNING do the same thing, but one
    branch has an extra comment and different indentation -- still WARNED."""
    if phase == Phase.PENDING:
        reason = "bad state"
        return Fail(reason)
    elif phase == Phase.RUNNING:
            # extra comment explaining this branch
            reason  =    "bad state"
            return Fail(reason)
    elif phase == Phase.DONE:
        return "finished"


def renamed_variable_not_flagged(phase: Phase):
    """if/elif dispatch where PENDING and RUNNING are structured identically
    but use different local variable names -- NOT flagged (no alpha-rename)."""
    if phase == Phase.PENDING:
        reason = "bad state"
        return Fail(reason)
    elif phase == Phase.RUNNING:
        cause = "bad state"
        return Fail(cause)
    elif phase == Phase.DONE:
        return "finished"


def genuinely_different_bodies(phase: Phase):
    """if/elif dispatch where every branch does something different --
    silent."""
    if phase == Phase.PENDING:
        return "waiting"
    elif phase == Phase.RUNNING:
        return "working"
    elif phase == Phase.DONE:
        return "finished"


def non_enum_dispatch_identical_bodies(status: str):
    """if/elif dispatch over a plain string subject where two branches are
    identical -- out of scope since the subject isn't Enum-typed."""
    if status == "pending":
        reason = "bad state"
        return Fail(reason)
    elif status == "running":
        reason = "bad state"
        return Fail(reason)
    else:
        return "finished"
