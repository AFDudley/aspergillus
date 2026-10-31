#!/usr/bin/env python3
"""Acceptance probe for asp-ce6.2 clauses C1/C2/C7.

Default mode (``--json``) parses ``docs/rust-rules.md`` and reports how
many of the 27 aspergillus rules it names, how many carry no recognized
disposition, and how many carry a disposition that is not one of the five
allowed kinds. ``--fixtures`` additionally builds the Rust gate, finds
every rule whose disposition is a checked kind (clippy lint, ast-grep
rule, or gate check), and confirms each has a committed
``rust/fixtures/<ASPnnn>/{violating,satisfying}/`` pair that behaves
correctly: at least one finding on the violating fixture, none on the
satisfying one.

Emits one ``stdout_json`` object. Judges nothing itself — the linked
spec's ``then`` clauses own the verdict.
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
RUST_RULES_DOC = REPO_ROOT / "docs" / "rust-rules.md"
RUST_MANIFEST = REPO_ROOT / "rust" / "Cargo.toml"
FIXTURES_DIR = REPO_ROOT / "rust" / "fixtures"

ALL_RULE_IDS = (
    [f"ASP{n}" for n in range(201, 207)]
    + [f"ASP{n}" for n in range(301, 305)]
    + [f"ASP{n}" for n in range(401, 418)]
)

CHECKED_KINDS = {"Clippy lint", "ast-grep rule", "Gate check"}
RECOGNIZED_KINDS = CHECKED_KINDS | {"Language feature", "Does not apply"}

ROW_RE = re.compile(r"^\|\s*(ASP\d{3})\s*\|\s*([^|]+?)\s*\|\s*$", re.MULTILINE)
KIND_RE = re.compile(r"^([A-Za-z][A-Za-z \-]*?):")


def parse_dispositions(text: str) -> dict[str, str]:
    """Every ``ASPnnn`` table row's disposition cell, by rule id."""
    dispositions: dict[str, str] = {}
    for match in ROW_RE.finditer(text):
        rule_id, cell = match.group(1), match.group(2).strip()
        dispositions[rule_id] = cell
    return dispositions


def kind_of(disposition: str) -> str | None:
    match = KIND_RE.match(disposition)
    return match.group(1) if match else None


def build_gate() -> Path:
    env = dict(os.environ)
    env["PATH"] = f"{env.get('HOME', '')}/.cargo/bin:{env.get('HOME', '')}/.bun/bin:{env.get('PATH', '')}"
    subprocess.run(
        ["cargo", "build", "--manifest-path", str(RUST_MANIFEST), "--offline", "-q"],
        check=True,
        env=env,
        cwd=REPO_ROOT,
    )
    return REPO_ROOT / "rust" / "target" / "debug" / "aspergillus-rust-gate"

FINDING_RE = re.compile(r": (ASP\d{3})$", re.MULTILINE)


def rule_findings(gate: Path, workspace: Path, rule_id: str) -> int:
    env = dict(os.environ)
    env["PATH"] = f"{env.get('HOME', '')}/.cargo/bin:{env.get('HOME', '')}/.bun/bin:{env.get('PATH', '')}"
    result = subprocess.run(
        [str(gate), str(workspace)],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    return sum(1 for m in FINDING_RE.finditer(result.stdout) if m.group(1) == rule_id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fixtures", action="store_true")
    args = parser.parse_args()

    text = RUST_RULES_DOC.read_text()
    dispositions = parse_dispositions(text)

    rules_without_disposition = sum(
        1 for rule_id in ALL_RULE_IDS if not dispositions.get(rule_id, "").strip()
    )
    rules_with_unrecognized_disposition = 0
    for rule_id in ALL_RULE_IDS:
        cell = dispositions.get(rule_id, "")
        kind = kind_of(cell) if cell else None
        if kind is None or kind not in RECOGNIZED_KINDS:
            rules_with_unrecognized_disposition += 1

    observation: dict[str, object] = {
        "rules_total": len(ALL_RULE_IDS),
        "rules_named": sum(1 for rule_id in ALL_RULE_IDS if rule_id in dispositions),
        "rules_without_disposition": rules_without_disposition,
        "rules_with_unrecognized_disposition": rules_with_unrecognized_disposition,
    }

    if args.fixtures:
        checked_rule_ids = [
            rule_id
            for rule_id in ALL_RULE_IDS
            if kind_of(dispositions.get(rule_id, "")) in CHECKED_KINDS
        ]
        gate = build_gate()
        missing_pair = 0
        misbehaves = 0
        for rule_id in checked_rule_ids:
            violating = FIXTURES_DIR / rule_id / "violating"
            satisfying = FIXTURES_DIR / rule_id / "satisfying"
            if not violating.is_dir() or not satisfying.is_dir():
                missing_pair += 1
                continue
            violating_count = rule_findings(gate, violating, rule_id)
            satisfying_count = rule_findings(gate, satisfying, rule_id)
            if violating_count < 1 or satisfying_count != 0:
                misbehaves += 1
        observation["rules_with_check"] = len(checked_rule_ids)
        observation["rules_with_check_missing_fixture_pair"] = missing_pair
        observation["rules_with_check_whose_fixture_pair_misbehaves"] = misbehaves

    print(json.dumps(observation))
    return 0


if __name__ == "__main__":
    sys.exit(main())
