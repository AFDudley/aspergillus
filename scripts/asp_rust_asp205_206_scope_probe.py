#!/usr/bin/env python3
"""Acceptance probe for asp-b7b.1 clause C13.

Diffs this branch's current commit against the pebble's base sha and
counts the changed files under ``lobaria/`` (a vendored lobaria source
tree — this repository carries none; lobaria is a separate project),
``python/`` and ``typescript/``. This pebble's work is scoped to
``rust/``, ``scripts/`` and ``docs/`` only.

Emits one ``stdout_json`` object. Judges nothing itself — the linked
spec's ``then`` clauses own the verdict.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_SHA = "75b0187deb9c3371cc6f4141c9cb387562f41a66"


def changed_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{BASE_SHA}...HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def main() -> int:
    files = changed_files()

    observation = {
        "lobaria_source_files_changed": sum(1 for f in files if f.startswith("lobaria/")),
        "python_files_changed": sum(1 for f in files if f.startswith("python/")),
        "typescript_files_changed": sum(1 for f in files if f.startswith("typescript/")),
    }
    print(json.dumps(observation))
    return 0


if __name__ == "__main__":
    sys.exit(main())
