#!/usr/bin/env python3
"""Acceptance probe for asp-b7b.1 clause C6.

Builds the Rust gate and runs it over the committed
``rust/fixtures/lobaria-d0269c7/`` snapshot (verbatim real lobaria
source at commit ``d0269c7`` — see its ``PROVENANCE.md``) with the two
exclusions the pebble names and lobaria's own core declaration
(``aspergillus.toml``: ``statechart/**`` is the core). Confirms five
previously-verified false-positive sites produce no ASP205/ASP206
finding: ``shell/src/machine.rs`` ``create``, ``shell/src/capture.rs``
``decode_worker``, ``backtest/src/replay.rs`` ``open_tokens``,
``chart/src/lib.rs`` ``load``, and the committed ASP206 satisfying
fixture's shell wrapper (``summarize``) checked under ASP205.

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
ASP206_SATISFYING = RUST_DIR / "fixtures" / "ASP206" / "satisfying"

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


def run_gate(gate: Path, workspace: Path, extra_args: list[str]) -> str:
    result = subprocess.run(
        [str(gate), str(workspace), "--rules", str(RULES_DIR), *extra_args],
        capture_output=True,
        text=True,
        env=gate_env(),
        cwd=REPO_ROOT,
    )
    return result.stdout


def function_line(source_path: Path, function_name: str) -> int:
    pattern = re.compile(
        rf"^\s*(?:pub\s+)?fn\s+{re.escape(function_name)}\s*[(<]", re.MULTILINE
    )
    text = source_path.read_text()
    match = pattern.search(text)
    if match is None:
        raise ValueError(f"{function_name} not found in {source_path}")
    return text.count("\n", 0, match.start()) + 1


def is_flagged(findings: set[tuple[str, int]], path: str, line: int) -> bool:
    return (path, line) in findings


def main() -> int:
    gate = build_gate()

    lobaria_stdout = run_gate(
        gate,
        LOBARIA_FIXTURE,
        ["--exclude", "scripts/oracles/fixtures/**", "--exclude", "vendored/**"],
    )
    lobaria_findings = {
        (path, int(line))
        for path, line, rule_id in FINDING_RE.findall(lobaria_stdout)
        if rule_id in ("ASP205", "ASP206")
    }

    sites = [
        (
            "shell/src/machine.rs",
            function_line(LOBARIA_FIXTURE / "shell" / "src" / "machine.rs", "create"),
        ),
        (
            "shell/src/capture.rs",
            function_line(LOBARIA_FIXTURE / "shell" / "src" / "capture.rs", "decode_worker"),
        ),
        (
            "backtest/src/replay.rs",
            function_line(LOBARIA_FIXTURE / "backtest" / "src" / "replay.rs", "open_tokens"),
        ),
        (
            "chart/src/lib.rs",
            function_line(LOBARIA_FIXTURE / "chart" / "src" / "lib.rs", "load"),
        ),
    ]
    sites_with_finding = sum(1 for path, line in sites if is_flagged(lobaria_findings, path, line))

    # The fifth site: the ASP206 satisfying fixture's shell wrapper
    # (`summarize`), checked under ASP205 specifically — a separate,
    # single-crate workspace run (it is not part of the lobaria snapshot).
    asp206_stdout = run_gate(gate, ASP206_SATISFYING, [])
    asp206_findings = {
        (path, int(line))
        for path, line, rule_id in FINDING_RE.findall(asp206_stdout)
        if rule_id == "ASP205"
    }
    shell_wrapper_line = function_line(ASP206_SATISFYING / "src" / "lib.rs", "summarize")
    if is_flagged(asp206_findings, "src/lib.rs", shell_wrapper_line):
        sites_with_finding += 1

    observation = {
        "sites_checked": len(sites) + 1,
        "sites_with_finding": sites_with_finding,
    }
    print(json.dumps(observation))
    return 0


if __name__ == "__main__":
    sys.exit(main())
