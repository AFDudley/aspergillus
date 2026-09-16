"""Acceptance oracle for asp-d88.2 clause c3: clone-type label.

Emits ONE observation: whether the reported duplicate pair carries a
non-empty clone-type label. Judges nothing -- the spec's ``then`` predicate
owns the verdict.
"""

from __future__ import annotations

import json

from _scan import fixture_dir_arg, group_containing, scan

from aspergillus.duplicates import find_all_duplicate_groups


def main() -> None:
    records = scan(fixture_dir_arg())
    groups = find_all_duplicate_groups(records, min_lines=1, allowlist=frozenset())
    match = group_containing(groups, "fetch_a", "fetch_b")
    has_label = match is not None and bool(match.clone_type)
    print(json.dumps({"has_label": has_label}))


if __name__ == "__main__":
    main()
