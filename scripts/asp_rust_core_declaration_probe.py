#!/usr/bin/env python3
"""Acceptance probe for asp-b7b.1 clause C1.

Builds the Rust gate, then writes the SAME I/O-calling function into two
throwaway single-crate workspaces: one whose ``aspergillus.toml`` declares
``src/**`` as the functional core, one whose ``aspergillus.toml`` declares
a path pattern the function's file does not match. Runs the gate over
each and counts the ASP205/ASP206 findings. Also confirms the gate's own
stderr says it read the declaration from a configuration file.

Emits one ``stdout_json`` object. Judges nothing itself — the linked
spec's ``then`` clauses own the verdict.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUST_DIR = REPO_ROOT / "rust"
RULES_DIR = RUST_DIR / "ast-grep-rules"

FUNCTION_SOURCE = (
    'pub fn persist(ps: &[&str]) {\n'
    '    ps.iter().for_each(|p| std::fs::write(p, b"").unwrap());\n'
    "}\n"
)

FINDING_RE = re.compile(r": (ASP\d{3})$", re.MULTILINE)


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


def write_workspace(root: Path, core_paths: list[str]) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "Cargo.toml").write_text(
        '[package]\nname = "probe"\nversion = "0.1.0"\nedition = "2021"\n'
    )
    (root / "aspergillus.toml").write_text(
        "core_paths = [" + ", ".join(f'"{p}"' for p in core_paths) + "]\n"
    )
    (root / "src" / "lib.rs").write_text(FUNCTION_SOURCE)


def run_gate(gate: Path, workspace: Path) -> tuple[str, str]:
    result = subprocess.run(
        [str(gate), str(workspace), "--rules", str(RULES_DIR)],
        capture_output=True,
        text=True,
        env=gate_env(),
        cwd=REPO_ROOT,
    )
    return result.stdout, result.stderr


def asp205_206_count(stdout: str) -> int:
    return sum(1 for m in FINDING_RE.finditer(stdout) if m.group(1) in ("ASP205", "ASP206"))


def main() -> int:
    gate = build_gate()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        core_ws = tmp_path / "core-copy"
        outside_ws = tmp_path / "outside-copy"
        write_workspace(core_ws, ["src/**"])
        write_workspace(outside_ws, ["nonexistent-path/**"])

        core_stdout, core_stderr = run_gate(gate, core_ws)
        outside_stdout, _outside_stderr = run_gate(gate, outside_ws)

    observation = {
        "findings_in_declared_core": asp205_206_count(core_stdout),
        "findings_outside_declared_core": asp205_206_count(outside_stdout),
        "core_declaration_file_read": "read core declaration from" in core_stderr
        and "aspergillus.toml" in core_stderr,
    }
    print(json.dumps(observation))
    return 0


if __name__ == "__main__":
    sys.exit(main())
