#!/usr/bin/env python3
"""Acceptance probe for asp-b7b.1 clause C10.

Runs ``cargo clippy -D warnings`` and ``cargo fmt --check`` over
``rust/`` and records each command's exit code.

Emits one ``stdout_json`` object. Judges nothing itself — the linked
spec's ``then`` clauses own the verdict.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUST_DIR = REPO_ROOT / "rust"


def gate_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = f"{env.get('HOME', '')}/.cargo/bin:{env.get('PATH', '')}"
    return env


def main() -> int:
    clippy = subprocess.run(
        ["cargo", "clippy", "--offline", "--all-targets", "-q", "--", "-D", "warnings"],
        cwd=RUST_DIR,
        env=gate_env(),
        capture_output=True,
        text=True,
    )
    fmt_check = subprocess.run(
        ["cargo", "fmt", "--check"],
        cwd=RUST_DIR,
        env=gate_env(),
        capture_output=True,
        text=True,
    )

    observation = {
        "clippy_exit_code": clippy.returncode,
        "fmt_check_exit_code": fmt_check.returncode,
    }
    print(json.dumps(observation))
    return 0


if __name__ == "__main__":
    sys.exit(main())
