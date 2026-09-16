"""Acceptance oracle for asp-d88.2 clause c1: fragment-granular detection.

Emits ONE observation: whether process_orders and process_items -- which
share an inner helper and a duplicated statement block inside otherwise
different bodies -- are flagged as a duplicate pair. Judges nothing -- the
spec's ``then`` predicate owns the verdict.
"""

from __future__ import annotations

import json

from _scan import fixture_dir_arg, group_containing, scan

from aspergillus.duplicates import find_all_duplicate_groups


def main() -> None:
    records = scan(fixture_dir_arg())
    groups = find_all_duplicate_groups(records, min_lines=3, allowlist=frozenset())
    match = group_containing(groups, "process_orders", "process_items")
    print(json.dumps({"flagged": match is not None}))


if __name__ == "__main__":
    main()
