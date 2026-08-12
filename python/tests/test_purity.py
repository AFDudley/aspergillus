"""Tests for the corpus purity ratio — ASP205's criterion, at its real unit.

ASP205 was retired for Python because it reported a CORPUS claim ("70%+
of functions should be pure") once per FUNCTION. These tests assert the
replacement decides the claim the rule could not: over many files, as one
ratio, against one floor, with a pass verdict a real program can reach.
"""

from __future__ import annotations

from aspergillus.purity import (
    DEFAULT_MIN_PURE_RATIO,
    format_report,
    function_purities,
    summarize,
)

_PURE = "def add(a: int, b: int) -> int:\n    return a + b\n"
_IMPURE = "def emit(line: str) -> None:\n    print(line)\n"
_FACTORY = "def make_logger(prefix: str):\n    def emit(line: str) -> None:\n        print(prefix, line)\n\n    return emit\n"


def test_a_shell_function_is_impure_and_a_transform_is_pure() -> None:
    """The effect signal is `_find_io_calls`, so the two rules and this
    command can never disagree about what an effect is."""
    pure = function_purities("a.py", _PURE)
    impure = function_purities("b.py", _IMPURE)
    assert [p.pure for p in pure] == [True]
    assert [p.pure for p in impure] == [False]
    assert impure[0].io_calls == ("print",)


def test_a_factory_is_pure_and_its_product_is_not() -> None:
    """Same unit of analysis `_find_io_calls` states: `make_logger` prints
    nothing when called, so counting it impure double-counted one effect."""
    records = {p.name: p.pure for p in function_purities("c.py", _FACTORY)}
    assert records == {"make_logger": True, "emit": False}


def test_the_ratio_is_a_corpus_verdict_not_a_per_function_one() -> None:
    """Nine pure functions and one shell function clear the 70% floor.

    This is the passing form ASP205 had none of: the shell function is
    still there, still does its I/O, and the program passes.
    """
    purities = []
    for index in range(9):
        purities.extend(function_purities(f"pure{index}.py", _PURE))
    purities.extend(function_purities("shell.py", _IMPURE))
    report = summarize(purities, DEFAULT_MIN_PURE_RATIO)
    assert (report.total, report.pure, report.impure) == (10, 9, 1)
    assert report.ratio == 0.9
    assert report.meets_target


def test_a_corpus_below_the_floor_fails_and_names_the_worst_files() -> None:
    purities = []
    purities.extend(function_purities("pure.py", _PURE))
    for _index in range(3):
        purities.extend(function_purities("shell.py", _IMPURE))
    purities.extend(function_purities("other.py", _IMPURE))
    report = summarize(purities, DEFAULT_MIN_PURE_RATIO)
    assert report.ratio == 0.2
    assert not report.meets_target
    assert report.worst == (("shell.py", 3), ("other.py", 1))
    rendered = format_report(report)
    assert "BELOW TARGET" in rendered
    assert "shell.py" in rendered


def test_an_empty_corpus_is_pure_rather_than_a_division_by_zero() -> None:
    report = summarize([], DEFAULT_MIN_PURE_RATIO)
    assert report.ratio == 1.0
    assert report.meets_target
