#!/usr/bin/env python3
"""Acceptance probe for asp-b7b.1 clause C8.

Builds the Rust gate and runs it over the committed
``rust/fixtures/lobaria-d0269c7/`` snapshot with the pebble's two
exclusions and lobaria's own core declaration (``statechart/**`` is the
core). Counts the ASP205 and ASP206 findings whose path starts with
``statechart/`` — lobaria's pure functional core — and how many
``statechart/**/*.rs`` files the fixture carries.

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
LOBARIA_FIXTURE = RUST_DIR / "fixtures" / "lobaria-d0269c7"

FINDING_RE = re.compile(r"^(\S+):(\d+): (ASP\d{3})$", re.MULTILINE)


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


def main() -> int:
    gate = build_gate()

    result = subprocess.run(
        [
            str(gate),
            str(LOBARIA_FIXTURE),
            "--rules",
            str(RULES_DIR),
            "--exclude",
            "scripts/oracles/fixtures/**",
            "--exclude",
            "vendored/**",
        ],
        capture_output=True,
        text=True,
        env=gate_env(),
        cwd=REPO_ROOT,
    )

    statechart_asp205 = 0
    statechart_asp206 = 0
    for path, _line, rule_id in FINDING_RE.findall(result.stdout):
        if not path.startswith("statechart/"):
            continue
        if rule_id == "ASP205":
            statechart_asp205 += 1
        elif rule_id == "ASP206":
            statechart_asp206 += 1

    statechart_files_scanned = len(list((LOBARIA_FIXTURE / "statechart").rglob("*.rs")))

    observation = {
        "statechart_files_scanned": statechart_files_scanned,
        "statechart_asp205_findings": statechart_asp205,
        "statechart_asp206_findings": statechart_asp206,
    }
    print(json.dumps(observation))
    return 0


if __name__ == "__main__":
    sys.exit(main())
