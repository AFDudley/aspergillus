#!/usr/bin/env python3
"""Acceptance probe for pebble asp-fd1.4 (behavior oracle, single mode).

Proves the project's whole test suite (``uv run --directory python pytest
tests -q``) stays green with ASP411 FsmStringlyDispatch's fixture-based
coverage included — not just the rule's own isolated test file. Runs the
REAL suite via subprocess and EMITS one ``stdout_json`` observation; it
judges nothing — the linked spec's ``then`` predicates own the verdict.

``-rA`` (report all outcomes) is added to the described ``pytest tests -q``
command so the single run's own output names the passing test IDs — this is
how ``mentions_rule`` is derived from the SAME real run that produces
``exit_code``, rather than a second, separate invocation.

Emits ``{"exit_code": <int>, "mentions_rule": <bool>}``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_pytest() -> tuple[int, str]:
    """IO shell: run the real project test suite, return (exit_code, stdout)."""
    result = subprocess.run(
        ["uv", "run", "--directory", str(REPO_ROOT / "python"), "pytest", "tests", "-q", "-rA"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout


def main() -> int:
    exit_code, stdout = run_pytest()
    mentions_rule = "FsmStringlyDispatch" in stdout
    print(json.dumps({"exit_code": exit_code, "mentions_rule": mentions_rule}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
