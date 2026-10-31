#!/usr/bin/env python3
"""Acceptance probe for asp-ce6.2 clause C10: adding the Rust surface
changes neither the Python rules nor the TypeScript rules.

Runs the real Python test suite (``uv run --directory python pytest
tests -q``) and the real TypeScript rule/layout/error test suite
(``bun test typescript/rules typescript/layouts typescript/errors``),
each as a real subprocess, and counts failures from their own reported
summary line. Emits one ``stdout_json`` object. Judges nothing itself —
the linked spec's ``then`` clauses own the verdict.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def gate_env() -> dict[str, str]:
    env = dict(os.environ)
    home = env.get("HOME", "")
    env["PATH"] = f"{home}/.cargo/bin:{home}/.bun/bin:{env.get('PATH', '')}"
    return env


def first_int(pattern: str, text: str) -> int:
    match = re.search(pattern, text)
    return int(match.group(1)) if match else 0


def main() -> int:
    env = gate_env()

    python_result = subprocess.run(
        ["uv", "run", "--directory", "python", "pytest", "tests", "-q"],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    python_out = python_result.stdout + python_result.stderr
    python_failures = first_int(r"(\d+) failed", python_out)

    bun = env.get("HOME", "") + "/.bun/bin/bun"
    if not Path(bun).exists():
        bun = "bun"
    ts_result = subprocess.run(
        [bun, "test", "typescript/rules", "typescript/layouts", "typescript/errors"],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    ts_out = ts_result.stdout + ts_result.stderr
    ts_failures = first_int(r"(\d+) fail", ts_out)

    exit_code = 0 if python_failures == 0 and ts_failures == 0 else 1
    observation = {
        "exit_code": exit_code,
        "python_rule_failures": python_failures,
        "typescript_rule_failures": ts_failures,
    }
    print(json.dumps(observation))
    return 0


if __name__ == "__main__":
    sys.exit(main())
