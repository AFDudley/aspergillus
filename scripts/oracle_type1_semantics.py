#!/usr/bin/env python3
"""Acceptance probe for pebble asp-d88.1, clause c1 (behavior oracle).

Proves the type-1 detector (``aspergillus.duplicates.find_type1_duplicate_groups``)
compares function bodies after stripping only comments and whitespace, with
no identifier renaming and no literal-value normalization — the Roy & Cordy
(2007) definition of a type-1 (exact) clone.

Reads one JSON object from stdin:
``{"comment_whitespace_pair": [src_a, src_b],
   "renamed_identifier_pair": [src_a, src_b],
   "literal_value_pair": [src_a, src_b]}``
Each value is a two-element list of Python source strings, each defining
one function.

This probe drives a child ``python3`` inside the project's uv-managed
environment (``uv run --directory python``), where ``aspergillus`` and its
``libcst`` dependency are installed, and EMITS one ``stdout_json``
observation. It judges nothing — the linked spec's ``then`` predicates own
the verdict.

Prints one JSON object to stdout:
``{"comment_whitespace_pair_is_type1": <bool>,
   "renamed_identifier_pair_is_type1": <bool>,
   "literal_value_pair_is_type1": <bool>}``
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_DIR = REPO_ROOT / "python"

_CHILD_TEMPLATE = """
import json

from aspergillus.duplicates import extract_function_records, find_type1_duplicate_groups

pairs = json.loads({pairs_json!r})


def is_type1(src_a, src_b):
    records = extract_function_records(src_a, "a.py") + extract_function_records(src_b, "b.py")
    groups = find_type1_duplicate_groups(records, min_lines=1, allowlist=frozenset())
    return len(groups) == 1


result = {{name: is_type1(*pair) for name, pair in pairs.items()}}
print(json.dumps(result))
"""


def main() -> int:
    """IO shell: parse stdin, drive the real detector via ``uv run``, emit its verdict fields."""
    payload = json.loads(sys.stdin.read())
    pairs = {
        "comment_whitespace_pair_is_type1": payload["comment_whitespace_pair"],
        "renamed_identifier_pair_is_type1": payload["renamed_identifier_pair"],
        "literal_value_pair_is_type1": payload["literal_value_pair"],
    }
    child_source = _CHILD_TEMPLATE.format(pairs_json=json.dumps(pairs))

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", dir=PYTHON_DIR, delete=False
    ) as handle:
        handle.write(child_source)
        script_path = handle.name
    try:
        proc = subprocess.run(
            ["uv", "run", "--directory", str(PYTHON_DIR), "python3", script_path],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        Path(script_path).unlink()

    if proc.returncode != 0 or not proc.stdout.strip():
        print(json.dumps({"child_exit_code": proc.returncode, "child_stderr": proc.stderr}))
        return 0

    print(proc.stdout.strip().splitlines()[-1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
