#!/usr/bin/env python3
"""ASP-FSM rule-table oracle probe (pebble asp-fd1.5): emits an SMT-LIB2
behavior theory, judges nothing.

Reads the target rule-taxonomy doc (docs/design.md) and, for each of the
four ASP-FSM rules (FsmEnumDispatchExhaustive, FsmEdgeDuration,
FsmRedundantBranches, FsmStringlyDispatch), determines whether the rule
name is mentioned and, if so, the ASP4xx number label sharing its line (a
bullet header or table row always carries both on one physical line in
this repo's docs; a name mentioned only in prose with no co-located number
is treated as unlabeled). Declares one Bool per rule ("mentions_<Rule>")
plus "numbers_distinct" (true iff the four rules that were found each carry
a DIFFERENT ASP4xx number), and asserts each to its real, observed value --
no `check-sat`, the runner's own z3 discharge owns satisfiability.

Usage: verify_design_doc_rule_table.py <path-to-doc>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RULE_NAMES = (
    "FsmEnumDispatchExhaustive",
    "FsmEdgeDuration",
    "FsmRedundantBranches",
    "FsmStringlyDispatch",
)

_NUMBER_RE = re.compile(r"ASP4\d\d")


def same_line_number(text: str, name: str) -> str | None:
    """Pure: the ASP4xx label CLOSEST (by character position) to some
    mention of `name`, restricted to the same physical LINE -- so a
    table's dense rows or a doc's neighboring bullets never leak a
    different rule's number into this one, and a line naming several
    rules (e.g. "`A` (ASP408), `B` (ASP409)") pairs each with its own
    nearest label rather than all labels on the line."""
    for line in text.splitlines():
        idx = line.find(name)
        if idx == -1:
            continue
        matches = list(_NUMBER_RE.finditer(line))
        if not matches:
            continue
        best = min(matches, key=lambda m: min(abs(m.start() - idx), abs(m.end() - idx)))
        return best.group(0)
    return None


def collect_facts(text: str) -> dict[str, str | None]:
    """Pure: {rule_name: same-line ASP4xx label or None} for every rule name."""
    return {name: same_line_number(text, name) for name in RULE_NAMES}


def render_smt2(facts: dict[str, str | None]) -> str:
    """Pure: assemble the SMT-LIB2 behavior theory from the observed facts."""
    lines: list[str] = []
    found_numbers: list[str] = []
    for name, number in facts.items():
        mentioned = number is not None
        lines.append(f"(declare-const mentions_{name} Bool)")
        lines.append(f"(assert (= mentions_{name} {'true' if mentioned else 'false'}))")
        if number is not None:
            found_numbers.append(number)
    distinct = len(found_numbers) == len(RULE_NAMES) == len(set(found_numbers))
    lines.append("(declare-const numbers_distinct Bool)")
    lines.append(f"(assert (= numbers_distinct {'true' if distinct else 'false'}))")
    return "\n".join(lines) + "\n"


def main() -> int:
    doc_path = Path(sys.argv[1])
    text = doc_path.read_text(encoding="utf-8")
    facts = collect_facts(text)
    sys.stdout.write(render_smt2(facts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
