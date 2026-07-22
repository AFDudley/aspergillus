#!/usr/bin/env python3
"""Acceptance probe for pebble asp-fd1.4 (behavior oracles, arg-dispatched).

Proves ASP414 FsmStringlyDispatch actually fires through the SHIPPED fixit
CLI (``uv run --directory python fixit lint``), using this repo's own
``[tool.fixit]`` config — not just via ``LintRunner`` in a unit test — and
that the ``# asp-fsm: boundary-parse`` escape hatch silences it. Mirrors the
independent-verification bar asp-6b0 used for ASP410 (real subprocess, real
CLI, real config), lifted from a manual transcript into a committed,
re-runnable probe.

This probe drives the real ``fixit`` CLI against a fixture written to a
scratch file and EMITS one ``stdout_json`` observation. It judges nothing —
the linked spec's ``then`` predicates own the verdict (``docs/ORACLES.md``-
style separation: the probe emits, the runner judges).

Modes (``argv[1]``):

- ``invalid`` — a same-module Enum plus an unmarked if/elif dispatch on
  string literals shadowing its values. Emits
  ``{"reports_violation": <bool>}`` — expected ``True``.
- ``boundary_marker`` — the identical dispatch shape, but the function
  carries ``# asp-fsm: boundary-parse``. Emits
  ``{"reports_violation": <bool>}`` — expected ``False``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_INVALID_FIXTURE = '''\
from enum import Enum


class Status(Enum):
    ACTIVE = "active"
    IDLE = "idle"


def route(status):
    if status == "active":
        return 1
    elif status == "idle":
        return 0
    return -1
'''

_BOUNDARY_MARKER_FIXTURE = '''\
from enum import Enum


class Status(Enum):
    ACTIVE = "active"
    IDLE = "idle"


def parse_status(raw):
    # asp-fsm: boundary-parse
    if raw == "active":
        return Status.ACTIVE
    if raw == "idle":
        return Status.IDLE
    raise ValueError(raw)
'''

_FIXTURES = {
    "invalid": _INVALID_FIXTURE,
    "boundary_marker": _BOUNDARY_MARKER_FIXTURE,
}


def run_fixit_lint(fixture_source: str) -> bool:
    """IO shell: write the fixture, run the real fixit CLI, report whether
    FsmStringlyDispatch fired.

    The fixture is written INSIDE ``python/`` (not a bare /tmp dir): fixit's
    config discovery walks up from the target file's own path looking for
    ``pyproject.toml``, independent of the invoking ``--directory`` cwd — a
    fixture outside the ``python/`` tree never sees
    ``[tool.fixit] enable = ["aspergillus.rules"]`` and would silently never
    fire any aspergillus rule at all.
    """
    python_dir = REPO_ROOT / "python"
    with tempfile.TemporaryDirectory(dir=python_dir) as tmp_dir:
        fixture_path = Path(tmp_dir) / "fixture.py"
        fixture_path.write_text(fixture_source, encoding="utf-8")
        result = subprocess.run(
            ["uv", "run", "--directory", str(python_dir), "fixit", "lint", str(fixture_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    return "FsmStringlyDispatch" in result.stdout


def main() -> int:
    mode = sys.argv[1]
    reports_violation = run_fixit_lint(_FIXTURES[mode])
    print(json.dumps({"reports_violation": reports_violation}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
