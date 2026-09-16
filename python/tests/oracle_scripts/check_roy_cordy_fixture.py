"""Acceptance oracle for asp-d88.2 clause c7: Roy & Cordy (2007) fixture.

Emits ONE observation: whether summarize_a and summarize_b -- a type-2
clone produced by the "statement insertion" editing scenario from the Roy &
Cordy taxonomy -- are flagged as a duplicate pair. Judges nothing -- the
spec's ``then`` predicate owns the verdict.
"""

from __future__ import annotations

import json

from _scan import fixture_dir_arg, group_containing, scan

from aspergillus.duplicates import find_all_duplicate_groups


def main() -> None:
    records = scan(fixture_dir_arg())
    groups = find_all_duplicate_groups(records, min_lines=3, allowlist=frozenset())
    match = group_containing(groups, "summarize_a", "summarize_b")
    print(json.dumps({"flagged": match is not None}))


if __name__ == "__main__":
    main()
