"""Acceptance oracle for asp-d88.2 clause c4: similarity score.

Emits ONE observation: the reported duplicate pair's numeric similarity
score. Judges nothing -- the spec's ``then`` predicate (score > 0) owns the
verdict.
"""

from __future__ import annotations

import json

from _scan import fixture_dir_arg, group_containing, scan

from aspergillus.duplicates import find_all_duplicate_groups


def main() -> None:
    records = scan(fixture_dir_arg())
    groups = find_all_duplicate_groups(records, min_lines=1, allowlist=frozenset())
    match = group_containing(groups, "fetch_a", "fetch_b")
    print(json.dumps({"score": match.similarity if match is not None else 0}))


if __name__ == "__main__":
    main()
