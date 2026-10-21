#!/usr/bin/env python3
"""Acceptance probe for asp-b7b.1 clause C5.

Builds the Rust gate, runs it over the committed ASP205 and ASP206
violating fixtures, and records whether each run's exit code fails the
run (non-zero). Also confirms neither rule's finding is hardcoded as
non-blocking (``purity.rs`` maps every ASP205/ASP206 finding to
``blocking: true``) and that the gate's own CLI offers no flag to turn a
finding into a warning.

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
PURITY_SOURCE = RUST_DIR / "src" / "purity.rs"
GATE_BIN_SOURCE = RUST_DIR / "src" / "bin" / "aspergillus_rust_gate.rs"

RULE_IDS = ["ASP205", "ASP206"]

# A CLI flag name that would let a finding through as a warning instead
# of failing the run. None of these appear anywhere in the gate's own
# argument parsing.
REPORT_ONLY_FLAG_RE = re.compile(
    r"--(report-only|warn-only|no-block|severity|non-blocking)"
)


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


def run_exit_code(gate: Path, workspace: Path) -> int:
    result = subprocess.run(
        [str(gate), str(workspace), "--rules", str(RULES_DIR)],
        capture_output=True,
        text=True,
        env=gate_env(),
        cwd=REPO_ROOT,
    )
    return result.returncode


def rule_finding_is_blocking_in_source(rule_id: str, source: str) -> bool:
    """``purity.rs`` maps ``rule_id`` findings via a
    ``.map(|f| (f.line, "ASPnnn", true))`` shape (see
    ``impure_function_findings``/``mixed_io_logic_findings``): the
    literal directly after the rule id string is the hardcoded
    ``blocking`` value.
    """
    pattern = re.compile(rf'"{rule_id}",\s*(true|false)\)')
    match = pattern.search(source)
    return match is not None and match.group(1) == "true"


def main() -> int:
    gate = build_gate()
    purity_source = PURITY_SOURCE.read_text()
    gate_bin_source = GATE_BIN_SOURCE.read_text()

    cli_has_report_only_flag = REPORT_ONLY_FLAG_RE.search(gate_bin_source) is not None

    rules_that_did_not_fail_the_run = 0
    rules_with_report_only_mode = 0

    for rule_id in RULE_IDS:
        violating = FIXTURES_DIR / rule_id / "violating"
        exit_code = run_exit_code(gate, violating)
        if exit_code == 0:
            rules_that_did_not_fail_the_run += 1
        hardcoded_blocking = rule_finding_is_blocking_in_source(rule_id, purity_source)
        if not hardcoded_blocking or cli_has_report_only_flag:
            rules_with_report_only_mode += 1

    observation = {
        "rules_checked": len(RULE_IDS),
        "rules_that_did_not_fail_the_run": rules_that_did_not_fail_the_run,
        "rules_with_report_only_mode": rules_with_report_only_mode,
    }
    print(json.dumps(observation))
    return 0


if __name__ == "__main__":
    sys.exit(main())
