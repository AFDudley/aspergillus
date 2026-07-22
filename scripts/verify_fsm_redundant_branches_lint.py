#!/usr/bin/env python3
"""ASP411 FsmRedundantBranches: verify the RULE fires through the real fixit
CLI, not just via in-repo pytest fixtures.

Unlike the sibling ``check_*.py`` scripts in this directory (standalone
``ast``-only checkers that never touch the package's install state), this
probe deliberately shells out to ``uv run --directory python fixit lint`` --
the exact command a developer or CI gate runs -- against a temp fixture
written inside ``python/`` (so fixit's config discovery finds this repo's own
``[tool.fixit]`` in ``python/pyproject.toml``). That is the independent-
verification bar pebble asp-6b0 used for ASP410: the shipped CLI, this
repo's own config, not an isolated unit test of the rule's internals.

Usage: verify_fsm_redundant_branches_lint.py <redundant|renamed>

Prints one JSON object to stdout: ``{"reports_violation": <bool>}``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_DIR = REPO_ROOT / "python"

# Two of the checker's own merged fixture scenarios
# (tests/fixtures/asp_fsm_redundant.py), each isolated into its own module so
# running fixit on one doesn't also contain the other's shape.
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

FIXTURES = {
    # redundant_identical_bodies: RUNNING and DONE are both literally
    # Fail(reason) -- the real PRESERVE/FAIL shape -- must WARN.
    "redundant": (
        _PREAMBLE + "def handle(phase: Phase):\n"
        "    if phase == Phase.PENDING:\n"
        '        return "waiting"\n'
        "    elif phase == Phase.RUNNING:\n"
        '        reason = "not ready"\n'
        "        return Fail(reason)\n"
        "    elif phase == Phase.DONE:\n"
        '        reason = "not ready"\n'
        "        return Fail(reason)\n"
    ),
    # renamed_variable_not_flagged: PENDING and RUNNING are structured
    # identically but use different local variable names -- must NOT warn
    # (the rule's deliberate no-alpha-rename design choice).
    "renamed": (
        _PREAMBLE + "def handle(phase: Phase):\n"
        "    if phase == Phase.PENDING:\n"
        '        reason = "bad state"\n'
        "        return Fail(reason)\n"
        "    elif phase == Phase.RUNNING:\n"
        '        cause = "bad state"\n'
        "        return Fail(cause)\n"
        "    elif phase == Phase.DONE:\n"
        '        return "finished"\n'
    ),
}


def _run_fixit_lint(fixture_code: str) -> str:
    """IO: write ``fixture_code`` under ``python/`` and run the real fixit
    CLI on it via ``uv run --directory python``, returning combined output."""
    with tempfile.NamedTemporaryFile(
        suffix=".py", dir=PYTHON_DIR, delete=False
    ) as handle:
        handle.write(fixture_code.encode("utf-8"))
        fixture_path = Path(handle.name)
    try:
        result = subprocess.run(
            ["uv", "run", "--directory", str(PYTHON_DIR), "fixit", "lint", fixture_path.name],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout + result.stderr
    finally:
        fixture_path.unlink(missing_ok=True)


def main() -> int:
    """IO shell: run the real fixit CLI against the named scenario and print
    whether ASP411 reported a violation."""
    scenario = sys.argv[1]
    output = _run_fixit_lint(FIXTURES[scenario])
    print(json.dumps({"reports_violation": "ASP411" in output}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
