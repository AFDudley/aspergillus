"""Acceptance oracle for asp-d88.2 clause c9: BigCloneBench (2014) T2 fixture.

Emits ONE observation: whether compute_checksum and compute_digest -- a
whole-body type-2 clone in the shape of BigCloneBench's T2 category -- are
flagged as a duplicate pair. Judges nothing -- the spec's ``then`` predicate
owns the verdict.
"""

from __future__ import annotations

import json

from _scan import fixture_dir_arg, group_containing, scan

from aspergillus.duplicates import find_all_duplicate_groups


def main() -> None:
    records = scan(fixture_dir_arg())
    groups = find_all_duplicate_groups(records, min_lines=3, allowlist=frozenset())
    match = group_containing(groups, "compute_checksum", "compute_digest")
    print(json.dumps({"flagged": match is not None}))


if __name__ == "__main__":
    main()
