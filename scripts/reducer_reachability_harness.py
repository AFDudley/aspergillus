#!/usr/bin/env python3
"""Acceptance probe for pebble asp-9b8 (behavior oracles, arg-dispatched).

Proves ASP415 ``ReducerReachability`` actually fires through the SHIPPED
fixit CLI (``uv run --directory python fixit lint``) -- and, crucially, that
it does so under a CONSUMER-SUPPLIED CONFIGURATION rather than logic baked
into the tool. Mirrors the independent-verification bar
``verify_fsm_stringly_dispatch_lint.py`` used for ASP414 (real subprocess,
real CLI, real config) and the local-rule mechanism fixit itself ships
(``fixit.config.local_rule_loader``): a per-scenario scratch directory gets
its own ``.fixit.toml`` (``root = true``, so it is the ONLY config fixit
reads for that scenario -- the shipped ``python/pyproject.toml``'s
``enable = ["aspergillus.rules"]`` is never merged in) enabling a small local
module that subclasses the shipped ``ReducerReachability`` engine with a
scenario-specific configuration.

Two named configurations:

- ``exophial`` -- the real motivating consumer config: ``WATCHED_PATH_PATTERNS
  = {"*/tests/*", "*/scripts/*"}``, otherwise the engine's own defaults
  (``run_cli_dispatch``, ``@requires_container_reducer``).
- ``alt-demo`` -- a configuration with NO relationship to exophial's names:
  a different watched folder (``*/widgets/*``) and a different reachable
  symbol (``launch_widget_thing``), proving the engine's behavior comes
  entirely from the configuration handed to it (acceptance clause c1).

Four modes (``argv[1]``), each builds a fixture, runs the real CLI against
it, and EMITS one ``stdout_json`` observation. It judges nothing -- the
linked spec's ``then`` predicates own the verdict; the process exit code
mirrors a real lint gate's own convention (0 = clean, 1 = the configured
rule fired), which the spec grades directly:

- ``bare`` -- an unguarded reachable call inside the config's watched folder.
  Expected: fires (exit 1).
- ``guarded`` -- the identical call, wrapped in the config's exemption
  decorator. Expected: clean (exit 0).
- ``outside-scope`` -- the identical unguarded call, placed OUTSIDE the
  config's watched folder (standing in for real production code).
  Expected: clean (exit 0).
- ``generic`` -- ``bare``, run against a configuration unrelated to
  exophial's own names/paths. Expected: fires (exit 1).

Usage: ``reducer_reachability_harness.py <bare|guarded|outside-scope|generic> <exophial|alt-demo>``
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_DIR = REPO_ROOT / "python"

_CONFIGS = {
    "exophial": {
        "class_name": "ExophialReducerReachability",
        "subclass_source": (
            "import aspergillus.rules.catalog.reducer_reachability as _rr\n\n\n"
            "class ExophialReducerReachability(_rr.ReducerReachability):\n"
            '    WATCHED_PATH_PATTERNS = frozenset({"*/tests/*", "*/scripts/*"})\n'
        ),
        "call_expr": "run_cli_dispatch('repo', 'pebble-id')",
        "decorator": "requires_container_reducer",
        "in_scope_dir": "tests",
        "out_of_scope_dir": "src",
    },
    "alt-demo": {
        "class_name": "AltDemoReachability",
        "subclass_source": (
            "import aspergillus.rules.catalog.reducer_reachability as _rr\n\n\n"
            "class AltDemoReachability(_rr.ReducerReachability):\n"
            '    WATCHED_PATH_PATTERNS = frozenset({"*/widgets/*"})\n'
            '    REACHABLE_CALLS = frozenset({"launch_widget_thing"})\n'
            "    CONSTRUCT_CLASS_NAMES = frozenset()\n"
            "    DRIVE_METHOD_NAMES = frozenset()\n"
            "    SUBPROCESS_DOTTED_NAMES = frozenset()\n"
            "    SUBPROCESS_ARGV_MARKERS = frozenset()\n"
            '    EXEMPTION_DECORATORS = frozenset({"requires_widget_harness"})\n'
            '    EXEMPTION_IMPORT_MODULES = frozenset({"widget_harness"})\n'
        ),
        "call_expr": "launch_widget_thing('cfg')",
        "decorator": "requires_widget_harness",
        "in_scope_dir": "widgets",
        "out_of_scope_dir": "core",
    },
}

_MODE_TO_CONFIG_KEY = {
    "bare": "exophial",
    "guarded": "exophial",
    "outside-scope": "exophial",
    "generic": "alt-demo",
}


def _fixture_source(call_expr: str, decorator: str | None) -> str:
    if decorator is None:
        return f"def probe():\n    {call_expr}\n"
    return f"@{decorator}\ndef probe():\n    {call_expr}\n"


def run_scenario(mode: str, config_name: str) -> dict:
    """IO shell: materialize a scratch consumer config + fixture INSIDE
    ``python/`` (fixit's config discovery walks up from the target file's
    own path; a ``root = true`` local config there is the ONLY config read
    for this scenario), run the real fixit CLI, and report whether the
    scenario's configured rule fired."""
    config = _CONFIGS[config_name]

    if mode == "outside-scope":
        fixture_dir_name = config["out_of_scope_dir"]
        decorator = None
    elif mode == "guarded":
        fixture_dir_name = config["in_scope_dir"]
        decorator = config["decorator"]
    else:  # "bare" / "generic"
        fixture_dir_name = config["in_scope_dir"]
        decorator = None

    with tempfile.TemporaryDirectory(dir=PYTHON_DIR) as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / ".fixit.toml").write_text(
            '[tool.fixit]\nroot = true\nenable = [".consumer_rule"]\n', encoding="utf-8"
        )
        (tmp_path / "consumer_rule.py").write_text(config["subclass_source"], encoding="utf-8")

        fixture_dir = tmp_path / fixture_dir_name
        fixture_dir.mkdir(parents=True, exist_ok=True)
        fixture_path = fixture_dir / "fixture.py"
        fixture_path.write_text(_fixture_source(config["call_expr"], decorator), encoding="utf-8")

        result = subprocess.run(
            ["uv", "run", "--directory", str(PYTHON_DIR), "fixit", "lint", str(fixture_path)],
            capture_output=True,
            text=True,
            check=False,
        )

    violated = config["class_name"] in result.stdout
    return {
        "mode": mode,
        "config": config_name,
        "rule": config["class_name"],
        "violated": violated,
    }


def main() -> int:
    mode = sys.argv[1]
    config_name = sys.argv[2]
    expected_config = _MODE_TO_CONFIG_KEY.get(mode)
    if expected_config is not None and expected_config != config_name:
        raise ValueError(f"mode {mode!r} is only defined for config {expected_config!r}, got {config_name!r}")

    observation = run_scenario(mode, config_name)
    print(json.dumps(observation))
    return 1 if observation["violated"] else 0


if __name__ == "__main__":
    sys.exit(main())
