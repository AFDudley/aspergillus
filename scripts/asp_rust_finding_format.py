#!/usr/bin/env python3
"""Acceptance probe for asp-ce6.2 clause C8: every printed finding line
reads as ``path:line: ASPnnn``.

Builds the real Rust gate and runs it over every committed
``rust/fixtures/<ASPnnn>/violating/`` crate, collects every printed
finding line, and counts how many match the given format regex. Emits
one ``stdout_json`` object. Judges nothing itself — the linked spec's
``then`` clauses own the verdict.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUST_MANIFEST = REPO_ROOT / "rust" / "Cargo.toml"
FIXTURES_DIR = REPO_ROOT / "rust" / "fixtures"


def gate_env() -> dict[str, str]:
    env = dict(os.environ)
    home = env.get("HOME", "")
    env["PATH"] = f"{home}/.cargo/bin:{home}/.bun/bin:{env.get('PATH', '')}"
    return env


def build_gate() -> Path:
    subprocess.run(
        ["cargo", "build", "--manifest-path", str(RUST_MANIFEST), "--offline", "-q"],
        check=True,
        env=gate_env(),
        cwd=REPO_ROOT,
    )
    return REPO_ROOT / "rust" / "target" / "debug" / "aspergillus-rust-gate"


def gate_stdout_lines(gate: Path, workspace: Path) -> list[str]:
    result = subprocess.run(
        [str(gate), str(workspace)],
        capture_output=True,
        text=True,
        env=gate_env(),
        cwd=REPO_ROOT,
    )
    return [line for line in result.stdout.splitlines() if line]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format-regex", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    format_re = re.compile(args.format_regex)
    gate = build_gate()

    all_lines: list[str] = []
    for violating_dir in sorted(FIXTURES_DIR.glob("*/violating")):
        all_lines.extend(gate_stdout_lines(gate, violating_dir))

    not_matching = sum(1 for line in all_lines if not format_re.match(line))

    observation = {
        "finding_lines_total": len(all_lines),
        "finding_lines_not_matching_format": not_matching,
    }
    print(json.dumps(observation))
    return 0


if __name__ == "__main__":
    sys.exit(main())
