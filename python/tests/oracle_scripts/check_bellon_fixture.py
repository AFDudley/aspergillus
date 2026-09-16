"""Acceptance oracle for asp-d88.2 clause c8: Bellon et al. (2007) fixture.

Emits ONE observation: whether import_widget and import_gadget -- a
real-world-shaped type-2 clone from the Bellon reference-clone benchmark
lineage -- are flagged as a duplicate pair. Judges nothing -- the spec's
``then`` predicate owns the verdict.
"""

from __future__ import annotations

import json

from _scan import fixture_dir_arg, group_containing, scan

from aspergillus.duplicates import find_all_duplicate_groups


def main() -> None:
    records = scan(fixture_dir_arg())
    groups = find_all_duplicate_groups(records, min_lines=3, allowlist=frozenset())
    match = group_containing(groups, "import_widget", "import_gadget")
    print(json.dumps({"flagged": match is not None}))


if __name__ == "__main__":
    main()
