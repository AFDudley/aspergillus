#!/usr/bin/env python3
"""Acceptance probe for pebble asp-d88.1, clause c4/c7 (behavior oracle).

Proves, independently of the pytest suite built for this feature, that
``aspergillus.duplicates.find_type1_duplicate_groups`` correctly labels
type-1 pairs across three Roy & Cordy (2007) editing scenarios: a blank
line, an inserted comment, and layout whitespace around an operator.

Reads one JSON object from stdin:
``{"blank_line_pair": [src_a, src_b],
   "comment_insertion_pair": [src_a, src_b],
   "layout_whitespace_pair": [src_a, src_b]}``
Each value is a two-element list of Python source strings, each defining
one function.

This probe drives a child ``python3`` inside the project's uv-managed
environment (``uv run --directory python``) and EMITS one ``stdout_json``
observation. It judges nothing — the linked spec's ``then`` predicates own
the verdict.

Prints one JSON object to stdout:
``{"blank_line_pair_is_type1": <bool>,
   "comment_insertion_pair_is_type1": <bool>,
   "layout_whitespace_pair_is_type1": <bool>}``
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
        "blank_line_pair_is_type1": payload["blank_line_pair"],
        "comment_insertion_pair_is_type1": payload["comment_insertion_pair"],
        "layout_whitespace_pair_is_type1": payload["layout_whitespace_pair"],
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
