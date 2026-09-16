"""Shared scan helper for asp-d88.2 acceptance-oracle scripts.

Each oracle script is a standalone entrypoint the exophial reducer runs
directly (``python3 <script> <fixture_dir>``), so this module holds only the
one bit of repeated plumbing -- reading a fixture directory's .py files into
FunctionRecords -- imported the same way ``aspergillus`` itself is (this repo
root is a uv project whose venv carries the ``aspergillus`` package; see
``pyproject.toml``).
"""

from __future__ import annotations

import sys
from pathlib import Path

from aspergillus.duplicates import DuplicateGroup, FunctionRecord, extract_function_records


def scan(fixture_dir: str) -> list[FunctionRecord]:
    """Extract every function record from every ``*.py`` file under ``fixture_dir``."""
    records: list[FunctionRecord] = []
    for path in sorted(Path(fixture_dir).glob("*.py")):
        records.extend(extract_function_records(path.read_text(encoding="utf-8"), str(path)))
    return records


def fixture_dir_arg() -> str:
    """The fixture directory passed as the oracle script's one CLI argument."""
    (arg,) = sys.argv[1:]
    return arg


def group_containing(
    groups: list[DuplicateGroup], name_a: str, name_b: str
) -> DuplicateGroup | None:
    """The first group whose members include both ``name_a`` and ``name_b``, if any.

    A whole corpus can contain incidental duplicate groups besides the pair a
    given fixture targets (e.g. a shared trivial inner helper); matching on
    the specific pair of names keeps the observation about THAT pair, not
    about whether the corpus produced any group at all.
    """
    for group in groups:
        names = {member.name for member in group.members}
        if name_a in names and name_b in names:
            return group
    return None
