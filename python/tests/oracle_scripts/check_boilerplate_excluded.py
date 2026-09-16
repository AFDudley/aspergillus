"""Acceptance oracle for asp-d88.2 clause c5: boilerplate exclusion.

Emits ONE observation: whether a fixture containing only a pass-only
__init__ and a one-line getter, verbatim identical across two classes,
produces NO duplicate report. Judges nothing -- the spec's ``then``
predicate owns the verdict.
"""

from __future__ import annotations

import json

from _scan import fixture_dir_arg, scan

from aspergillus.duplicates import find_all_duplicate_groups


def main() -> None:
    records = scan(fixture_dir_arg())
    groups = find_all_duplicate_groups(records, min_lines=1, allowlist=frozenset())
    print(json.dumps({"excluded": len(groups) == 0}))


if __name__ == "__main__":
    main()
