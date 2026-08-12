"""Tests for Level 2 NASA rules."""

from __future__ import annotations

from pathlib import Path

import libcst as cst
from fixit.engine import LintRunner
from fixit.ftypes import Config
from fixit.testing import add_lint_rule_tests_to_module

# `add_lint_rule_tests_to_module` REBINDS each rule's name in this module
# to a generated `unittest.TestCase`, so the hand-written tests below
# reach the rules through the module rather than those names.
from aspergillus.rules import level2
from aspergillus.rules.level2 import (
    FunctionTooLong,
    GlobalMutableState,
    LowAssertionDensity,
    MixedIOAndLogic,
    UnboundedLoop,
    _find_io_calls,
)

add_lint_rule_tests_to_module(
    globals(),
    [
        FunctionTooLong(),
        LowAssertionDensity(),
        GlobalMutableState(),
        UnboundedLoop(),
        MixedIOAndLogic(),
    ],
)


def _io_calls_of(source: str, index: int = 0) -> set[str]:
    """The I/O calls `_find_io_calls` attributes to the `index`-th function."""
    module = cst.parse_module(source)
    functions = [n for n in module.body if isinstance(n, cst.FunctionDef)]
    return _find_io_calls(functions[index].body)


def _report_lines(rule: object, source: str) -> list[int]:
    """Line numbers `rule` reports for `source`."""
    path = Path.cwd() / "sample.py"
    runner = LintRunner(path, source.encode())
    return [r.range.start.line for r in runner.collect_violations([rule], Config(path=path))]


NESTED_IO = (
    "def make_logger(prefix: str):\n"
    "    def emit(line: str) -> None:\n"
    "        print(prefix, line)\n"
    "\n"
    "    return emit\n"
)


def test_find_io_calls_attributes_nested_io_to_the_nested_function_only() -> None:
    """A factory performs no I/O; its product does.

    `make_logger(...)` prints nothing when called. Attributing `emit`'s
    `print` to the factory also double-counted one I/O site, and left the
    factory with no passing form — `emit` closes over `prefix`, so it
    cannot be lifted to module scope.

    This asserted through ASP205 until ASP205 was retired for Python
    (see the retirement note in `rules/level2.py`). The MECHANISM stayed:
    `_find_io_calls` still decides ASP202's imperative-shell predicate and
    ASP206's gate, so the unit-of-analysis rule is asserted directly.
    """
    assert _io_calls_of(NESTED_IO) == set()


def test_find_io_calls_separates_a_pandas_rename_from_a_filesystem_rename() -> None:
    """asp-108: `df.rename(columns=...)` is a pure in-memory transform;
    `p.rename(q)` is a filesystem rename.

    ASP205's VALID/INVALID cases carried this discrimination before its
    retirement. `_is_pandas_rename` is still reached from ASP202 and
    ASP206, so the discrimination is asserted on the mechanism itself.
    """
    pandas_kwarg = (
        "def normalize(df: object) -> object:\n    return df.rename(columns={'a': 'b'})\n"
    )
    pandas_computed = (
        "def spread(a: object, b: object) -> object:\n    return (a - b).rename('s')\n"
    )
    filesystem = "def move(p: object, q: object) -> None:\n    p.rename(q)\n"
    assert _io_calls_of(pandas_kwarg) == set()
    assert _io_calls_of(pandas_computed) == set()
    assert _io_calls_of(filesystem) == {"rename"}


def test_asp206_attributes_nested_io_to_the_nested_function_only() -> None:
    """ASP206 sourced io_calls from any depth while counting logic
    statements only at the outer body's top level, so its two halves
    measured different functions. Neither function here mixes."""
    assert _report_lines(level2.MixedIOAndLogic(), NESTED_IO) == []


def test_asp201_counts_code_lines_not_documentation() -> None:
    """A 70-line span that is 3 lines of code is a 3-line function.

    Under the raw span the only way to pass was to delete the prose,
    which is the incentive backwards — the same correction
    `duplicates.n_code_lines` already carries.
    """
    documented = (
        "def short_but_documented(x: int) -> int:\n"
        '    """Title.\n' + "".join(f"    prose line {i}\n" for i in range(70)) + '    """\n'
        "    # why the doubling\n"
        "\n"
        "    return x * 2\n"
    )
    assert _report_lines(level2.FunctionTooLong(), documented) == []


def test_asp201_still_reports_a_genuinely_long_function() -> None:
    """Comments do not buy length: 61 statements is 61 code lines."""
    long_body = (
        "def genuinely_long():\n"
        + "".join(f"    # step {i}\n    x{i} = {i}\n" for i in range(61))
        + "    return x0\n"
    )
    assert _report_lines(level2.FunctionTooLong(), long_body) == [1]


def test_asp202_triviality_exemption_survives_a_docstring() -> None:
    """A two-statement boundary reader is trivial however long its
    docstring is; the raw span made it lose the exemption for being
    documented."""
    documented_reader = (
        "def read_config(path: str) -> str:\n"
        '    """Read it.\n'
        "\n" + "".join(f"    prose {i}\n" for i in range(10)) + '    """\n'
        "    with open(path) as handle:\n"
        "        return handle.read()\n"
    )
    assert _report_lines(level2.LowAssertionDensity(), documented_reader) == []
