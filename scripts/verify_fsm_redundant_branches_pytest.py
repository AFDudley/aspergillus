#!/usr/bin/env python3
"""ASP411 FsmRedundantBranches: verify the full project test suite is green
and includes the new rule's fixture-based coverage.

Shells out to ``uv run --directory python pytest tests -q`` -- the exact
command from the pebble's acceptance criteria -- rather than importing
pytest, so this probe carries no dependency on the package's install state
beyond what ``uv run`` resolves itself.

Usage: verify_fsm_redundant_branches_pytest.py

Prints one JSON object to stdout:
``{"exit_code": <int>, "mentions_rule": <bool>}``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    """IO shell: run the real pytest suite and report its exit code plus
    whether the new rule's dedicated test module ran."""
    result = subprocess.run(
        ["uv", "run", "--directory", str(REPO_ROOT / "python"), "pytest", "tests", "-q", "-v"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT / "python",
        timeout=300,
    )
    output = result.stdout + result.stderr
    print(
        json.dumps(
            {
                "exit_code": result.returncode,
                "mentions_rule": "test_fsm_redundant_branches" in output
                or "FsmRedundantBranches" in output,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
