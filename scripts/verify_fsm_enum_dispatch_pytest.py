#!/usr/bin/env python3
"""ASP411 pytest-suite oracle probe: emits observations, judges nothing.

Drives the REAL `uv run --directory python pytest tests -q` command --
the whole project test suite, not just the new rule's own tests -- and
reports whether it exited clean and whether the run actually exercised
`FsmEnumDispatchExhaustive` coverage (`python/tests/
test_fsm_enum_dispatch_exhaustive.py`).

Usage: verify_fsm_enum_dispatch_pytest.py

Prints one JSON object to stdout:
``{"exit_code": <int>, "mentions_rule": <bool>}``. Judges nothing itself
-- the linked spec's `then` clauses own the verdict.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_DIR = REPO_ROOT / "python"


def run_pytest() -> dict:
    """IO shell: run the full suite via the real CLI subprocess (verbose, so
    the collected test IDs are observable) and report the raw exit code plus
    whether the new rule's dedicated test module actually ran."""
    result = subprocess.run(
        ["uv", "run", "--directory", str(PYTHON_DIR), "pytest", "tests", "-v"],
        capture_output=True,
        text=True,
    )
    return {
        "exit_code": result.returncode,
        "mentions_rule": "test_fsm_enum_dispatch_exhaustive" in result.stdout,
    }


def main() -> int:
    print(json.dumps(run_pytest()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
