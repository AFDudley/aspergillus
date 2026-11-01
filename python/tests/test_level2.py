"""Tests for Level 2 NASA rules."""

from __future__ import annotations

from pathlib import Path

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
    ImpureFunction,
    LowAssertionDensity,
    MixedIOAndLogic,
    UnboundedLoop,
)

add_lint_rule_tests_to_module(
    globals(),
    [
        FunctionTooLong(),
        LowAssertionDensity(),
        GlobalMutableState(),
        UnboundedLoop(),
        ImpureFunction(),
        MixedIOAndLogic(),
    ],
)


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


def test_asp205_attributes_nested_io_to_the_nested_function_only() -> None:
    """A factory performs no I/O; its product does.

    `make_logger(...)` prints nothing when called. Reporting it for
    `emit`'s `print` also double-counted one I/O site, and left the
    factory with no passing form — `emit` closes over `prefix`, so it
    cannot be lifted to module scope.
    """
    assert _report_lines(level2.ImpureFunction(), NESTED_IO) == [2]


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
