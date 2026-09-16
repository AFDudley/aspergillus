#!/usr/bin/env python3
"""Acceptance probe for pebble asp-d88.1, clause c3 (behavior oracle).

Proves the type-1 detector (``aspergillus.duplicates.find_type1_duplicate_groups``)
excludes boilerplate (trivial dunders, getters, pass-only bodies) from its
reports, while still detecting real duplication.

Reads one JSON object from stdin:
``{"boilerplate_pairs": [[src_a, src_b], ...], "real_pair": [src_a, src_b]}``.
Each pair is a two-element list of Python source strings, each defining one
function.

This probe drives a child ``python3`` inside the project's uv-managed
environment (``uv run --directory python``) and EMITS one ``stdout_json``
observation. It judges nothing — the linked spec's ``then`` predicates own
the verdict.

Prints one JSON object to stdout:
``{"boilerplate_pairs_reported": <int>, "real_pair_reported": <bool>}``.
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

payload = json.loads({payload_json!r})


def is_reported(src_a, src_b):
    records = extract_function_records(src_a, "a.py") + extract_function_records(src_b, "b.py")
    groups = find_type1_duplicate_groups(records, min_lines=1, allowlist=frozenset())
    return len(groups) == 1


boilerplate_reported = sum(1 for pair in payload["boilerplate_pairs"] if is_reported(*pair))
real_reported = is_reported(*payload["real_pair"])

print(json.dumps({{
    "boilerplate_pairs_reported": boilerplate_reported,
    "real_pair_reported": real_reported,
}}))
"""


def main() -> int:
    """IO shell: parse stdin, drive the real detector via ``uv run``, emit its verdict fields."""
    payload = json.loads(sys.stdin.read())
    child_source = _CHILD_TEMPLATE.format(payload_json=json.dumps(payload))

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
