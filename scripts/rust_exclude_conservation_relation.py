#!/usr/bin/env python3
"""Acceptance probe for pebble asp-f4c, clause c7 (metamorphic, conservation).

Proves excluding a path removes exactly the findings under that path and
changes nothing else: running ``aspergillus-rust-dup-type-check`` over the
same fixture with and without ``--exclude 'alpha/**'``, the finding count
without the flag equals the finding count with the flag plus the count of
findings the un-excluded run reports under ``alpha/``.

Builds the real ``aspergillus-rust-dup-type-check`` binary (``rust/``),
writes a throwaway three-crate fixture (``kept-a``, ``kept-b``,
``alpha/dup``, each declaring the same duplicated ``Marker`` type), runs
the real binary twice, and prints one JSON object to stdout:
``{"flows": [without, -with, -under_excluded]}``. The runner's own
``_relation_conservation`` reads this ``flows`` list and requires it sum
to zero; this script judges nothing itself and its exit code is not the
verdict.
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
MANIFEST = REPO_ROOT / "rust" / "Cargo.toml"

FINDING_RE = re.compile(r"^(?P<path>.+):(?P<line>\d+): ASP502$")

CRATE_LIB_RS = """pub struct Marker(pub i64);

static mut COUNTER: u32 = 0;

pub fn shaped(a: i32, b: i32) -> i32 {
    let sum = a + b;
    let scaled = sum * 9;
    let result = scaled + 1;
    result
}
"""


def cargo_env() -> dict[str, str]:
    """The subprocess environment with `~/.cargo/bin` reachable, mirroring
    the shell oracles' PATH fix for the hermetic grading env."""
    env = dict(os.environ)
    cargo_bin = str(Path.home() / ".cargo" / "bin")
    env["PATH"] = f"{cargo_bin}:{env.get('PATH', '')}"
    return env


def build_binary(env: dict[str, str]) -> Path:
    subprocess.run(
        [
            "cargo",
            "build",
            "--manifest-path",
            str(MANIFEST),
            "--offline",
            "-q",
            "--bin",
            "aspergillus-rust-dup-type-check",
        ],
        check=True,
        env=env,
    )
    return REPO_ROOT / "rust" / "target" / "debug" / "aspergillus-rust-dup-type-check"


def write_crate(root: Path, name: str) -> None:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (root / "Cargo.toml").write_text(
        f'[package]\nname = "{name}"\nversion = "0.1.0"\nedition = "2021"\n'
    )
    (src / "lib.rs").write_text(CRATE_LIB_RS)


def write_fixture(root: Path) -> None:
    write_crate(root / "kept-a", "kept-a")
    write_crate(root / "kept-b", "kept-b")
    write_crate(root / "alpha" / "dup", "alpha-dup")


def run_findings(binary: Path, fixture: Path, env: dict[str, str], extra_args: list[str]) -> list[tuple[str, int]]:
    result = subprocess.run(
        [str(binary), str(fixture), *extra_args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    findings = []
    for line in result.stdout.splitlines():
        match = FINDING_RE.match(line)
        if match:
            findings.append((match.group("path"), int(match.group("line"))))
    return findings


def main() -> int:
    env = cargo_env()
    binary = build_binary(env)

    with tempfile.TemporaryDirectory() as tmp:
        fixture = Path(tmp) / "fixture"
        write_fixture(fixture)

        without_exclude = run_findings(binary, fixture, env, [])
        with_exclude = run_findings(binary, fixture, env, ["--exclude", "alpha/**"])

    under_excluded = sum(1 for path, _ in without_exclude if path.startswith("alpha/"))
    flows = [len(without_exclude), -len(with_exclude), -under_excluded]

    print(json.dumps({"flows": flows}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
