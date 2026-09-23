#!/usr/bin/env python3
"""Acceptance probe for asp-ce6.2 clauses C3-C6: one Rust rule's fixture
pair.

Builds the real Rust gate, runs it over the named rule's committed
``rust/fixtures/<ASPnnn>/violating/`` and
``rust/fixtures/<ASPnnn>/satisfying/`` crates, and counts how many lines
the gate prints for that rule id on each. Emits one ``stdout_json``
object. Judges nothing itself — the linked spec's ``then`` clauses own
the verdict.
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


def count_findings(gate: Path, workspace: Path, rule_id: str) -> int:
    pattern = re.compile(rf": {re.escape(rule_id)}$", re.MULTILINE)
    result = subprocess.run(
        [str(gate), str(workspace)],
        capture_output=True,
        text=True,
        env=gate_env(),
        cwd=REPO_ROOT,
    )
    return len(pattern.findall(result.stdout))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rule", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rule_id = args.rule
    violating = FIXTURES_DIR / rule_id / "violating"
    satisfying = FIXTURES_DIR / rule_id / "satisfying"
    if not violating.is_dir() or not satisfying.is_dir():
        print(
            json.dumps(
                {
                    "rule": rule_id,
                    "violating_findings": 0,
                    "satisfying_findings": 0,
                    "error": "missing fixture pair",
                }
            )
        )
        return 0

    gate = build_gate()
    observation = {
        "rule": rule_id,
        "violating_findings": count_findings(gate, violating, rule_id),
        "satisfying_findings": count_findings(gate, satisfying, rule_id),
    }
    print(json.dumps(observation))
    return 0


if __name__ == "__main__":
    sys.exit(main())
