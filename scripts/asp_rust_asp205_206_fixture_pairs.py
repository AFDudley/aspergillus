#!/usr/bin/env python3
"""Acceptance probe for asp-b7b.1 clause C4.

Builds the Rust gate and runs it over ``rust/fixtures/ASP205/`` and
``rust/fixtures/ASP206/``'s committed ``violating``/``satisfying`` pairs.
For each rule: the violating fixture must report that rule's id at least
once, and the satisfying fixture must report it zero times.

Emits one ``stdout_json`` object. Judges nothing itself — the linked
spec's ``then`` clauses own the verdict.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUST_DIR = REPO_ROOT / "rust"
RULES_DIR = RUST_DIR / "ast-grep-rules"
FIXTURES_DIR = RUST_DIR / "fixtures"

FINDING_RE = re.compile(r": (ASP\d{3})$", re.MULTILINE)
RULE_IDS = ["ASP205", "ASP206"]


def gate_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = f"{env.get('HOME', '')}/.cargo/bin:{env.get('PATH', '')}"
    return env


def build_gate() -> Path:
    subprocess.run(
        ["cargo", "build", "--manifest-path", str(RUST_DIR / "Cargo.toml"), "--offline", "-q"],
        check=True,
        env=gate_env(),
        cwd=REPO_ROOT,
    )
    return RUST_DIR / "target" / "debug" / "aspergillus-rust-gate"


def rule_findings(gate: Path, workspace: Path, rule_id: str) -> int:
    result = subprocess.run(
        [str(gate), str(workspace), "--rules", str(RULES_DIR)],
        capture_output=True,
        text=True,
        env=gate_env(),
        cwd=REPO_ROOT,
    )
    return sum(1 for m in FINDING_RE.finditer(result.stdout) if m.group(1) == rule_id)


def main() -> int:
    gate = build_gate()

    rules_missing_fixtures = 0
    violating_fixtures_without_finding = 0
    satisfying_fixtures_with_finding = 0

    for rule_id in RULE_IDS:
        violating = FIXTURES_DIR / rule_id / "violating"
        satisfying = FIXTURES_DIR / rule_id / "satisfying"
        if not violating.is_dir() or not satisfying.is_dir():
            rules_missing_fixtures += 1
            continue
        if rule_findings(gate, violating, rule_id) < 1:
            violating_fixtures_without_finding += 1
        if rule_findings(gate, satisfying, rule_id) != 0:
            satisfying_fixtures_with_finding += 1

    observation = {
        "rules_checked": len(RULE_IDS),
        "rules_missing_fixtures": rules_missing_fixtures,
        "violating_fixtures_without_finding": violating_fixtures_without_finding,
        "satisfying_fixtures_with_finding": satisfying_fixtures_with_finding,
    }
    print(json.dumps(observation))
    return 0


if __name__ == "__main__":
    sys.exit(main())
