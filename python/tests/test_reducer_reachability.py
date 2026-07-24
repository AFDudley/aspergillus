"""Tests for ASP415 reducer-reachability (verification-integrity family).

Mirrors the catalog-move test shape used by ``test_in_process_e2e.py``:
``add_lint_rule_tests_to_module`` consumes the rule's ``VALID``/``INVALID``
cases and generates one test method per case. Standalone contract tests
assert the load-bearing properties directly, independent of the generated
cases:

- each of the three reachable shapes (bare/dotted call, fluent
  construct+drive, marked subprocess) fires on its own;
- the decorator and container-harness-import exemptions silence a call that
  would otherwise fire;
- ``WATCHED_PATH_PATTERNS`` gates by file path, and is CONFIGURABLE (a
  subclass narrows it) -- this is the property acceptance clause c1/c4 need;
- the symbol/marker sets are CONFIGURABLE (a subclass retargets them
  entirely, unrelated to exophial's names) -- clause c1;
- the rule is DISCOVERABLE via fixit's ``aspergillus.rules`` walk.
"""

from __future__ import annotations

from pathlib import Path

from fixit import LintRule
from fixit.config import collect_rules, generate_config
from fixit.engine import LintRunner
from fixit.ftypes import Config, LintViolation
from fixit.testing import add_lint_rule_tests_to_module

# Imported under an alias: ``add_lint_rule_tests_to_module`` injects a
# ``unittest.TestCase`` named after the rule class ("ReducerReachability")
# into this module's globals, which would otherwise shadow the rule itself.
from aspergillus.rules.catalog import ReducerReachability as ReducerReachabilityRule


def _reports(rule: LintRule, code: str, path: Path | None = None) -> list[LintViolation]:
    file_path = path if path is not None else Path.cwd() / "sample.py"
    runner = LintRunner(file_path, code.encode())
    return list(runner.collect_violations([rule], Config(path=file_path)))


def test_bare_reachable_call_flagged() -> None:
    """The load-bearing shape: a bare call to a configured reachable symbol."""
    flagged = _reports(ReducerReachabilityRule(), "run_cli_dispatch('repo', 'pebble')\n")
    assert len(flagged) == 1, flagged
    assert "ASP415" in flagged[0].message

    clean = _reports(ReducerReachabilityRule(), "other_thing()\n")
    assert clean == [], clean


def test_dotted_reachable_call_flagged() -> None:
    """A module-qualified dotted call (``daemon.start``) is the same shape
    as the bare form, matched at a ``.`` boundary."""
    assert len(_reports(ReducerReachabilityRule(), "exophial.daemon.start(repo)\n")) == 1
    assert len(_reports(ReducerReachabilityRule(), "daemon.start(repo)\n")) == 1
    # A different attribute isn't the configured shape.
    assert _reports(ReducerReachabilityRule(), "daemon.stop(repo)\n") == []


def test_fluent_construct_drive_flagged() -> None:
    """``Dispatcher(...).run()`` -- construct+drive in one expression -- is
    the shape a dotted-string reconstruction can't see (the base is a
    ``Call``, not a ``Name``/``Attribute`` chain), so it needs its own
    detector, mirroring ASP410's construct+drive pair."""
    assert len(_reports(ReducerReachabilityRule(), "Dispatcher(cfg).run()\n")) == 1
    # Construct without the drive method is not the smell.
    assert _reports(ReducerReachabilityRule(), "Dispatcher(cfg)\n") == []
    # A different class's fluent call is not a configured construct.
    assert _reports(ReducerReachabilityRule(), "Other(cfg).run()\n") == []


def test_marked_subprocess_flagged() -> None:
    """``subprocess.run``/``Popen`` only fires when the argv carries a
    configured daemon-launching marker -- an unrelated subprocess call
    must stay silent."""
    assert (
        len(_reports(ReducerReachabilityRule(), "subprocess.run(['exophiald', '--once'])\n")) == 1
    )
    assert len(_reports(ReducerReachabilityRule(), 'subprocess.Popen("exophial dispatch")\n')) == 1
    assert _reports(ReducerReachabilityRule(), "subprocess.run(['ls', '-la'])\n") == []


def test_decorator_exemption_silences_call() -> None:
    """A call lexically nested inside a function carrying the configured
    exemption decorator is not reported -- the sanctioned container fixture
    marker."""
    code = "@requires_container_reducer\ndef test_x():\n    run_cli_dispatch('repo', 'pebble')\n"
    assert _reports(ReducerReachabilityRule(), code) == []

    # A different decorator provides no exemption.
    other = "@some_other_decorator\ndef test_x():\n    run_cli_dispatch('repo', 'pebble')\n"
    assert len(_reports(ReducerReachabilityRule(), other)) == 1


def test_container_harness_import_exempts_whole_file() -> None:
    """Importing the configured container-harness module exempts every call
    in the file, not just the importing function."""
    code = (
        "from tests.e2e.container_harness import spawn\n\n\n"
        "def test_x():\n    run_cli_dispatch('repo', 'pebble')\n"
    )
    assert _reports(ReducerReachabilityRule(), code) == []


def test_named_in_docstring_not_flagged() -> None:
    """AST, not text: naming ``run_cli_dispatch()`` in a docstring is
    invisible -- only real ``cst.Call`` nodes count."""
    code = '"""Forbids run_cli_dispatch() bare."""\nx = 1\n'
    assert _reports(ReducerReachabilityRule(), code) == []


def test_watched_path_patterns_gates_by_path() -> None:
    """``WATCHED_PATH_PATTERNS`` restricts the check to matching paths (the
    default is empty = every path is in scope); a consumer narrows it, and
    only in-scope files get flagged."""

    class ScopedReducerReachability(ReducerReachabilityRule):
        WATCHED_PATH_PATTERNS = frozenset({"*/tests/*", "*/scripts/*"})

    code = "run_cli_dispatch('repo', 'pebble')\n"
    root = Path.cwd()

    under_tests = _reports(ScopedReducerReachability(), code, root / "tests" / "test_probe.py")
    assert len(under_tests) == 1, under_tests

    under_scripts = _reports(ScopedReducerReachability(), code, root / "scripts" / "probe.py")
    assert len(under_scripts) == 1, under_scripts

    outside_scope = _reports(ScopedReducerReachability(), code, root / "src" / "daemon.py")
    assert outside_scope == [], outside_scope


def test_symbols_are_configurable() -> None:
    """The reachable-call / construct / drive / subprocess-marker sets are
    consumer config, not hardcoded to exophial's names: a subclass retargets
    them entirely, and under that config exophial's default shape no longer
    fires while the new one does."""

    class WidgetReachability(ReducerReachabilityRule):
        REACHABLE_CALLS = frozenset({"launch_widget_thing"})
        CONSTRUCT_CLASS_NAMES = frozenset({"Supervisor"})
        DRIVE_METHOD_NAMES = frozenset({"serve"})
        SUBPROCESS_DOTTED_NAMES: frozenset[str] = frozenset()
        SUBPROCESS_ARGV_MARKERS: frozenset[str] = frozenset()

    fires = _reports(WidgetReachability(), "launch_widget_thing('cfg')\n")
    assert len(fires) == 1, fires

    fluent = _reports(WidgetReachability(), "Supervisor(cfg).serve()\n")
    assert len(fluent) == 1, fluent

    # exophial's default shape is not this consumer's symbol set -> silent.
    assert _reports(WidgetReachability(), "run_cli_dispatch('repo', 'pebble')\n") == []


def test_rule_is_discoverable_by_fixit() -> None:
    """ASP415 must be reachable through fixit's ``aspergillus.rules`` walk --
    the parent-package re-export seam (``rules/__init__.py``). Without it the
    rule is defined but never enforced."""
    cfg = generate_config(Path.cwd() / "sample.py")
    discovered = {type(rule).__name__ for rule in collect_rules(cfg)}
    assert "ReducerReachability" in discovered, sorted(discovered)


add_lint_rule_tests_to_module(globals(), [ReducerReachabilityRule()])
