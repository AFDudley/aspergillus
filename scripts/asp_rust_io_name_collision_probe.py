#!/usr/bin/env python3
"""Acceptance probe for asp-b7b.1 clause C2.

Builds the Rust gate, writes five ordinary-domain-code cases — each its
own module file — into a throwaway workspace whose ``aspergillus.toml``
declares the whole crate as the functional core, and confirms none of
the five produce an ASP205/ASP206 finding. Each case shares a bare name
with a real I/O call but is not I/O: an in-memory ``Book::open``, a
``json5::read`` over a ``&str``, an ``mpsc`` ``send`` and ``recv``, and a
domain ``create`` constructor.

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

# Each case is its own module file, so a per-case finding is unambiguous.
CASES: dict[str, str] = {
    "book_open": (
        "pub struct Book;\n"
        "impl Book {\n"
        "    pub fn open(&self) -> std::vec::IntoIter<i32> { vec![].into_iter() }\n"
        "}\n"
        "pub fn open_tokens(book: &Book) -> Option<i32> {\n"
        "    book.open().find_map(Some)\n"
        "}\n"
    ),
    "json5_read": (
        "pub fn load(text: &str) -> Result<i32, String> {\n"
        "    json5::read(text).map_err(|e| e.to_string())\n"
        "}\n"
    ),
    "mpsc_send": (
        "pub fn dispatch(jobs: &std::sync::mpsc::SyncSender<i32>) {\n"
        "    jobs.send(1).ok();\n"
        "}\n"
    ),
    "mpsc_recv": (
        "pub fn decode_worker(queue: &std::sync::mpsc::Receiver<i32>) -> Option<i32> {\n"
        "    queue.recv().ok()\n"
        "}\n"
    ),
    "domain_create": (
        "pub fn build(from: i32) -> i32 {\n"
        "    let outcome = rc::create(from);\n"
        "    outcome\n"
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
        workspace = Path(tmp) / "collision-cases"
        (workspace / "src").mkdir(parents=True)
        (workspace / "Cargo.toml").write_text(
            '[package]\nname = "collision-cases"\nversion = "0.1.0"\nedition = "2021"\n'
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

    cases_with_finding = sum(1 for name in CASES if f"src/{name}.rs" in flagged_files)

    observation = {
        "cases_checked": len(CASES),
        "cases_with_finding": cases_with_finding,
    }
    print(json.dumps(observation))
    return 0


if __name__ == "__main__":
    sys.exit(main())
