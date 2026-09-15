#!/usr/bin/env python3
"""Acceptance probe for pebble asp-c01 (behavior oracles, arg-dispatched).

Proves ``python/src/aspergillus/__init__.py`` imports under the bare-python3
acceptance-oracle contract (``scripts/CLAUDE.md``: standalone, stdlib-only,
no venv), where no aspergillus distribution metadata is findable, and that
``__version__`` still comes from the real distribution metadata when the
package IS installed. This probe drives a child ``python3`` (or, for the
``installed`` mode, ``uv run``) subprocess and EMITS one ``stdout_json``
observation. It judges nothing — the linked spec's ``then`` predicates own
the verdict.

Modes (``argv[1]``):

- ``pythonpath`` — spawns bare ``python3`` with ``PYTHONPATH`` pointing at
  ``python/src`` and no aspergillus distribution installed.
- ``sys_path`` — spawns bare ``python3`` with no ``PYTHONPATH`` set; the
  child inserts ``python/src`` into ``sys.path`` itself before importing.
- ``installed`` — spawns ``python3`` inside the project's uv-managed
  environment (``uv run --directory python``), where aspergillus IS
  installed and its distribution metadata is real.

Each mode emits: ``metadata_found`` (bool), ``import_ok`` (bool),
``package_not_found_error`` (bool, whether ``PackageNotFoundError``
propagated out of the import), ``version_is_str`` (bool),
``version_length`` (int), ``version_matches_metadata`` (bool).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_SRC = REPO_ROOT / "python" / "src"

_CHILD_SCRIPT = """
import json
from importlib.metadata import PackageNotFoundError, version

result = {"package_not_found_error": False}

try:
    version("aspergillus")
    result["metadata_found"] = True
except PackageNotFoundError:
    result["metadata_found"] = False

try:
    import aspergillus
except PackageNotFoundError:
    result["import_ok"] = False
    result["package_not_found_error"] = True
else:
    result["import_ok"] = True
    result["version_is_str"] = isinstance(aspergillus.__version__, str)
    result["version_length"] = len(aspergillus.__version__)
    try:
        result["version_matches_metadata"] = aspergillus.__version__ == version("aspergillus")
    except PackageNotFoundError:
        result["version_matches_metadata"] = False

print(json.dumps(result))
"""

_SYS_PATH_PREFIX = "import sys\nsys.path.insert(0, {path!r})\n"


def _run_child(command: list[str], script_source: str, env: dict[str, str]) -> dict:
    """IO shell: write the child script, run it as a subprocess, parse its
    one JSON line.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", dir=REPO_ROOT / "scripts", delete=False
    ) as handle:
        handle.write(script_source)
        script_path = handle.name
    try:
        proc = subprocess.run(
            [*command, script_path], env=env, capture_output=True, text=True, check=False
        )
    finally:
        os.unlink(script_path)
    if proc.returncode != 0 or not proc.stdout.strip():
        return {"child_exit_code": proc.returncode, "child_stderr": proc.stderr}
    return json.loads(proc.stdout.strip().splitlines()[-1])


def run_pythonpath() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PYTHON_SRC)
    return _run_child(["python3"], _CHILD_SCRIPT, env)


def run_sys_path() -> dict:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    script = _SYS_PATH_PREFIX.format(path=str(PYTHON_SRC)) + _CHILD_SCRIPT
    return _run_child(["python3"], script, env)


def run_installed() -> dict:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    command = ["uv", "run", "--directory", str(REPO_ROOT / "python"), "python3"]
    return _run_child(command, _CHILD_SCRIPT, env)


_MODES = {
    "pythonpath": run_pythonpath,
    "sys_path": run_sys_path,
    "installed": run_installed,
}


def main() -> int:
    mode = sys.argv[1]
    result = _MODES[mode]()
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
