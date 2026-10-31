#!/usr/bin/env python3
"""Acceptance probe for asp-b7b.1 clause C7.

Builds the Rust gate, writes the pebble's two named probe functions —
each its own module file — into a throwaway workspace whose
``aspergillus.toml`` declares the whole crate as the functional core,
and confirms ASP205 fires on both: a file write for every path in a
list, hidden inside a ``for_each`` closure, and a ``writeln!`` into an
open file.

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

PROBES: dict[str, str] = {
    "persist": (
        "pub fn persist(ps: &[&str]) {\n"
        '    ps.iter().for_each(|p| std::fs::write(p, b"").unwrap());\n'
        "}\n"
    ),
    "f": (
        "pub fn f(w: &mut std::fs::File) {\n"
        '    writeln!(w, "x").unwrap();\n'
        "}\n"
    ),
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
        workspace = Path(tmp) / "asp205-probes"
        (workspace / "src").mkdir(parents=True)
        (workspace / "Cargo.toml").write_text(
            '[package]\nname = "asp205-probes"\nversion = "0.1.0"\nedition = "2021"\n'
        )
        (workspace / "aspergillus.toml").write_text('core_paths = ["src/**"]\n')
        mod_decls = "\n".join(f"pub mod probe_{name};" for name in PROBES) + "\n"
        (workspace / "src" / "lib.rs").write_text(mod_decls)
        for name, source in PROBES.items():
            (workspace / "src" / f"probe_{name}.rs").write_text(source)

        result = subprocess.run(
            [str(gate), str(workspace), "--rules", str(RULES_DIR)],
            capture_output=True,
            text=True,
            env=gate_env(),
            cwd=REPO_ROOT,
        )

    flagged_files: set[str] = set()
    for path, rule_id in FINDING_RE.findall(result.stdout):
        if rule_id == "ASP205":
            flagged_files.add(path)

    probes_without_asp205_finding = sum(
        1 for name in PROBES if f"src/probe_{name}.rs" not in flagged_files
    )

    observation = {
        "probes_checked": len(PROBES),
        "probes_without_asp205_finding": probes_without_asp205_finding,
    }
    print(json.dumps(observation))
    return 0


if __name__ == "__main__":
    sys.exit(main())
