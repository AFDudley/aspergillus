#!/usr/bin/env python3
"""Acceptance probe for pebble asp-d88.1, clause c2 (behavior oracle).

Proves each detected type-1 clone pair in the report carries a clone-type
label and a similarity score, via
``aspergillus.duplicates.find_type1_duplicate_groups``.

Reads one JSON object from stdin: ``{"pair": [src_a, src_b]}`` — a
two-element list of Python source strings, each defining one function
identical to the other except for comments and blank lines.

This probe drives a child ``python3`` inside the project's uv-managed
environment (``uv run --directory python``) and EMITS one ``stdout_json``
observation. It judges nothing — the linked spec's ``then`` predicates own
the verdict.

Prints one JSON object to stdout:
``{"clone_type_label": <str>, "similarity_score": <float>}``. When the pair
is not detected as a type-1 clone at all, the fields are ``""`` and ``0.0``
— an honest report of "no such field exists", not a fabricated pass.
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

src_a, src_b = json.loads({pair_json!r})
records = extract_function_records(src_a, "a.py") + extract_function_records(src_b, "b.py")
groups = find_type1_duplicate_groups(records, min_lines=1, allowlist=frozenset())

if groups:
    result = {{"clone_type_label": groups[0].clone_type, "similarity_score": groups[0].similarity}}
else:
    result = {{"clone_type_label": "", "similarity_score": 0.0}}

print(json.dumps(result))
"""


def main() -> int:
    """IO shell: parse stdin, drive the real detector via ``uv run``, emit its verdict fields."""
    payload = json.loads(sys.stdin.read())
    child_source = _CHILD_TEMPLATE.format(pair_json=json.dumps(payload["pair"]))

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
