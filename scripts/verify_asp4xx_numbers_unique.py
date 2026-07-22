#!/usr/bin/env python3
"""ASP4xx uniqueness oracle probe (pebble asp-fd1.5): emits an SMT-LIB2
behavior theory, judges nothing.

Discovers every catalog rule's own self-claimed ASP4xx number (the first
``ASP4\\d\\d`` token in its module, paired with its ``class X(LintRule)``
name), then checks README.md / docs/design.md for the same rule names
mentioned on a line that also carries an ASP4xx label (a bullet header or
table row always carries both on one physical line in this repo's docs).
Declares one Bool per discovered ASP4xx number ("unique_ASP4nn"), true iff
exactly one rule name is associated with that number across the rule
source + both docs, plus an overall "all_unique" Bool -- no `check-sat`,
the runner's own z3 discharge owns satisfiability.

Usage: verify_asp4xx_numbers_unique.py <catalog_dir> <readme_path> <design_doc_path>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_NUMBER_RE = re.compile(r"ASP4\d\d")
_CLASS_RE = re.compile(r"^class (\w+)\(LintRule\):", re.MULTILINE)


def discover_catalog_claims(catalog_dir: Path) -> dict[str, str]:
    """Pure over given file contents: {rule_class_name: self-claimed ASP4xx}
    for every ``*.py`` file under `catalog_dir` that defines a LintRule."""
    claims: dict[str, str] = {}
    for path in sorted(catalog_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        class_match = _CLASS_RE.search(text)
        number_match = _NUMBER_RE.search(text)
        if class_match and number_match:
            claims[class_match.group(1)] = number_match.group(0)
    return claims


def same_line_numbers(text: str, name: str) -> list[str]:
    """Pure: for every physical LINE mentioning `name`, the ASP4xx label
    CLOSEST (by character position) to that mention -- so a table's dense
    rows or a doc's neighboring bullets never leak a different rule's
    number into this one, and a line naming several rules (e.g. "`A`
    (ASP408), `B` (ASP409)") pairs each with its own nearest label rather
    than all labels on the line."""
    found: list[str] = []
    for line in text.splitlines():
        idx = line.find(name)
        if idx == -1:
            continue
        matches = list(_NUMBER_RE.finditer(line))
        if not matches:
            continue
        best = min(matches, key=lambda m: min(abs(m.start() - idx), abs(m.end() - idx)))
        found.append(best.group(0))
    return found


def build_number_to_rules(
    catalog_claims: dict[str, str], doc_texts: list[str]
) -> dict[str, set[str]]:
    """Pure: {ASP4xx number: {rule names claiming it}} across the catalog's
    own self-claimed numbers and every doc's same-line mentions."""
    mapping: dict[str, set[str]] = {}
    for rule_name, number in catalog_claims.items():
        mapping.setdefault(number, set()).add(rule_name)
    for text in doc_texts:
        for rule_name in catalog_claims:
            for number in same_line_numbers(text, rule_name):
                mapping.setdefault(number, set()).add(rule_name)
    return mapping


def render_smt2(number_to_rules: dict[str, set[str]]) -> str:
    """Pure: assemble the SMT-LIB2 behavior theory from the observed facts."""
    lines: list[str] = []
    all_unique = True
    for number in sorted(number_to_rules):
        unique = len(number_to_rules[number]) == 1
        all_unique = all_unique and unique
        const = f"unique_{number}"
        lines.append(f"(declare-const {const} Bool)")
        lines.append(f"(assert (= {const} {'true' if unique else 'false'}))")
    lines.append("(declare-const all_unique Bool)")
    lines.append(f"(assert (= all_unique {'true' if all_unique else 'false'}))")
    return "\n".join(lines) + "\n"


def main() -> int:
    catalog_dir = Path(sys.argv[1])
    readme_path = Path(sys.argv[2])
    design_doc_path = Path(sys.argv[3])
    catalog_claims = discover_catalog_claims(catalog_dir)
    doc_texts = [
        readme_path.read_text(encoding="utf-8"),
        design_doc_path.read_text(encoding="utf-8"),
    ]
    number_to_rules = build_number_to_rules(catalog_claims, doc_texts)
    sys.stdout.write(render_smt2(number_to_rules))
    return 0


if __name__ == "__main__":
    sys.exit(main())
