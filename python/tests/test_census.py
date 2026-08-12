"""Tests for the I/O census — ASP205's enumeration without its verdict.

ASP205 was retired for Python because its per-function verdict had no
legal passing form. The enumeration it produced beside that verdict was
never wrong, and nothing replaced it. These tests assert the census
restores the enumeration, keeps the same effect signal, and reaches no
verdict of its own.
"""

from __future__ import annotations

from aspergillus.__main__ import main
from aspergillus.census import census_of_module, format_census, merge_censuses

_PURE = "def add(a: int, b: int) -> int:\n    return a + b\n"
_SHELL = "def emit(line: str) -> None:\n    print(line)\n"
_FACTORY = (
    "def make_logger(prefix: str):\n"
    "    def emit(line: str) -> None:\n"
    "        print(prefix, line)\n"
    "\n"
    "    return emit\n"
)
_METHOD = "class Loader:\n    def load(self, p) -> str:\n        return p.read_text()\n"


def test_the_census_reports_a_shell_function_and_omits_a_pure_one() -> None:
    """The effect signal is `_find_io_calls`, the SAME one ASP202 and
    ASP206 use, so the census and the rules cannot disagree."""
    seen, sites = census_of_module("b.py", _SHELL)
    assert seen == 1
    assert [(s.qualname, s.io_calls) for s in sites] == [("emit", ("print",))]
    assert census_of_module("a.py", _PURE) == (1, [])


def test_a_factory_is_absent_and_its_product_is_present() -> None:
    """Same unit of analysis `_find_io_calls` states: `make_logger`
    prints nothing when called, so it performs no effect."""
    seen, sites = census_of_module("c.py", _FACTORY)
    assert seen == 2
    assert [s.qualname for s in sites] == ["make_logger.emit"]


def test_a_method_carries_its_class_in_the_qualified_name() -> None:
    _seen, sites = census_of_module("d.py", _METHOD)
    assert [(s.qualname, s.io_calls) for s in sites] == [("Loader.load", ("read_text",))]


def test_adding_a_pure_function_moves_no_line_of_the_enumeration() -> None:
    """This is the defect `purity-ratio` had. A ratio rises when a pure
    function is added and no effect has moved. An enumeration does not.
    """
    before = merge_censuses([census_of_module("shell.py", _SHELL)])
    after = merge_censuses(
        [census_of_module("shell.py", _SHELL), census_of_module("pure.py", _PURE)]
    )
    assert before.sites == after.sites
    assert (before.scanned, after.scanned) == (1, 2)


def test_adding_an_effect_adds_a_line_and_removing_it_takes_the_line_away() -> None:
    """Discrimination. The census must move when an effect moves."""
    pure = "def work(items: list) -> int:\n    return sum(items)\n"
    impure = "def work(items: list) -> int:\n    print(items)\n    return sum(items)\n"
    assert census_of_module("m.py", pure)[1] == []
    grown = census_of_module("m.py", impure)[1]
    assert [(s.qualname, s.io_calls) for s in grown] == [("work", ("print",))]
    assert census_of_module("m.py", pure)[1] == []


def test_the_rendered_census_names_every_site_and_the_population() -> None:
    census = merge_censuses(
        [census_of_module("shell.py", _SHELL), census_of_module("pure.py", _PURE)]
    )
    rendered = format_census(census)
    assert "shell.py:1: emit — print" in rendered
    assert "1 effect-bearing functions in 1 modules, 2 functions scanned" in rendered


def test_the_command_exits_zero_on_a_tree_that_is_all_effect(tmp_path) -> None:
    """An instrument, not a gate. There is no census a tree can fail.

    A verdict here would rebuild ASP205: the enumeration is the same
    content, and the verdict is the part that had no passing form.
    """
    (tmp_path / "all_shell.py").write_text(_SHELL * 3, encoding="utf-8")
    assert main(["io-census", str(tmp_path)]) == 0
    (tmp_path / "all_shell.py").write_text(_PURE, encoding="utf-8")
    assert main(["io-census", str(tmp_path)]) == 0
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["io-census", str(empty)]) == 0
