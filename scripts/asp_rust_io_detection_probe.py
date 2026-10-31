#!/usr/bin/env python3
"""Acceptance probe for asp-b7b.1 clause C3.

Builds the Rust gate, writes seven real-I/O cases — each its own module
file — into a throwaway workspace whose ``aspergillus.toml`` declares the
whole crate as the functional core, and confirms every one of the seven
produces an ASP205/ASP206 finding: a file write hidden inside a closure
passed to ``for_each``, ``writeln!`` to a file, ``write!`` to a file,
``dbg!``, ``flush``, ``sync_all``, and ``std::process::exit``.

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

FINDING_RE = re.compile(r"^(src/[\w./]+\.rs):\d+: (ASP\d{3})$", re.MULTILINE)

CASES: dict[str, str] = {
    "closure_write": (
        "pub fn persist(ps: &[&str]) {\n"
        '    ps.iter().for_each(|p| std::fs::write(p, b"").unwrap());\n'
        "}\n"
    ),
    "writeln_to_file": (
        "pub fn log_line(w: &mut std::fs::File) {\n"
        '    writeln!(w, "x").unwrap();\n'
        "}\n"
    ),
    "write_to_file": (
        "pub fn log_text(w: &mut std::fs::File) {\n"
        '    write!(w, "x").unwrap();\n'
        "}\n"
    ),
    "dbg_macro": ("pub fn trace(x: i32) -> i32 {\n    dbg!(x)\n}\n"),
    "flush_call": (
        "pub fn flush_out(w: &mut std::fs::File) {\n    w.flush().unwrap();\n}\n"
    ),
    "sync_all_call": (
        "pub fn durable(w: &std::fs::File) {\n    w.sync_all().unwrap();\n}\n"
    ),
    "process_exit": ("pub fn halt() {\n    std::process::exit(1);\n}\n"),
}


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

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "io-cases"
        (workspace / "src").mkdir(parents=True)
        (workspace / "Cargo.toml").write_text(
            '[package]\nname = "io-cases"\nversion = "0.1.0"\nedition = "2021"\n'
        )
        (workspace / "aspergillus.toml").write_text('core_paths = ["src/**"]\n')
        mod_decls = "\n".join(f"pub mod {name};" for name in CASES) + "\n"
        (workspace / "src" / "lib.rs").write_text(mod_decls)
        for name, source in CASES.items():
            (workspace / "src" / f"{name}.rs").write_text(source)

        result = subprocess.run(
            [str(gate), str(workspace), "--rules", str(RULES_DIR)],
            capture_output=True,
            text=True,
            env=gate_env(),
            cwd=REPO_ROOT,
        )

    flagged_files: set[str] = set()
    for path, rule_id in FINDING_RE.findall(result.stdout):
        if rule_id in ("ASP205", "ASP206"):
            flagged_files.add(path)

    cases_without_finding = sum(
        1 for name in CASES if f"src/{name}.rs" not in flagged_files
    )

    observation = {
        "cases_checked": len(CASES),
        "cases_without_finding": cases_without_finding,
    }
    print(json.dumps(observation))
    return 0


if __name__ == "__main__":
    sys.exit(main())
