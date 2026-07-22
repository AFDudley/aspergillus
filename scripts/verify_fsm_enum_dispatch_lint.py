#!/usr/bin/env python3
"""ASP413 fixit-lint oracle probe: emits observations, judges nothing.

Drives the REAL `uv run --directory python fixit lint` CLI, using the
repo's own `python/pyproject.toml` `[tool.fixit]` config (`enable =
["aspergillus.rules"]`), against a temp copy of one of the two canonical
FsmEnumDispatchExhaustive (ASP413) fixtures -- the same shapes ported from
`scripts/check_asp_fsm_enum_dispatch.py` / `tests/fixtures/
asp_fsm_enum_dispatch.py` into the rule's own VALID/INVALID lists. This
is the independent-verification bar asp-6b0 used for ASP410: a real CLI
subprocess, not an in-process rule call.

Usage: verify_fsm_enum_dispatch_lint.py <invalid|valid>

Prints one JSON object to stdout:
``{"fixit_exit_code": <int>, "reports_violation": <bool>}``. Judges
nothing itself -- the linked spec's `then` clauses own the verdict.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_DIR = REPO_ROOT / "python"

# Mirrors FsmEnumDispatchExhaustive.INVALID[0]: if/elif enum dispatch that
# falls through to a plain trailing return -- no assert_never-guarded else.
_INVALID_FIXTURE = """\
from enum import Enum


class Phase(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"


def handle(phase: Phase) -> str:
    if phase == Phase.PENDING:
        return "waiting"
    elif phase == Phase.RUNNING:
        return "working"
    elif phase == Phase.DONE:
        return "finished"
    return "unreachable"
"""

# Mirrors FsmEnumDispatchExhaustive.VALID[0]: the same dispatch as a
# `match` statement ending in `case _: assert_never(...)`.
_VALID_FIXTURE = """\
from enum import Enum
from typing import assert_never


class Phase(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"


def handle(phase: Phase) -> str:
    match phase:
        case Phase.PENDING:
            return "waiting"
        case Phase.RUNNING:
            return "working"
        case Phase.DONE:
            return "finished"
        case _ as unreachable:
            assert_never(unreachable)
"""

_FIXTURES = {"invalid": _INVALID_FIXTURE, "valid": _VALID_FIXTURE}


def run_fixit_lint(mode: str) -> dict:
    """IO shell: write ``mode``'s fixture under python/ (so the repo's own
    pyproject.toml config resolves by directory walk) and lint it via the
    real CLI subprocess."""
    fixture_code = _FIXTURES[mode]
    with tempfile.TemporaryDirectory(dir=PYTHON_DIR) as tmp_dir:
        fixture_path = Path(tmp_dir) / "sample.py"
        fixture_path.write_text(fixture_code, encoding="utf-8")
        result = subprocess.run(
            [
                "uv",
                "run",
                "--directory",
                str(PYTHON_DIR),
                "fixit",
                "lint",
                str(fixture_path.relative_to(PYTHON_DIR)),
            ],
            capture_output=True,
            text=True,
        )
    return {
        "fixit_exit_code": result.returncode,
        "reports_violation": "FsmEnumDispatchExhaustive" in result.stdout,
    }


def main() -> int:
    mode = sys.argv[1]
    if mode not in _FIXTURES:
        raise ValueError(f"unknown mode {mode!r}, expected 'invalid' or 'valid'")
    print(json.dumps(run_fixit_lint(mode)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
