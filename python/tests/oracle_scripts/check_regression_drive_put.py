"""Acceptance oracle for asp-d88.2 clause c6: the drive/put regression.

Emits TWO observations: whether the checker flags a group at all, and
whether that group's members are drive and put by name. Judges nothing --
the spec's ``then`` predicates own the verdict.
"""

from __future__ import annotations

import json

from _scan import fixture_dir_arg, group_containing, scan

from aspergillus.duplicates import find_all_duplicate_groups


def main() -> None:
    records = scan(fixture_dir_arg())
    groups = find_all_duplicate_groups(records, min_lines=3, allowlist=frozenset())
    match = group_containing(groups, "drive", "put")
    print(
        json.dumps(
            {
                "flagged": match is not None,
                "members_include_drive_and_put": match is not None,
            }
        )
    )


if __name__ == "__main__":
    main()
