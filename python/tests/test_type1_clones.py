"""Tests for type-1 (exact) clone detection (duplicates.py).

Fixtures are drawn from two sources named in pebble asp-d88.1:

- Roy & Cordy's 2007 clone taxonomy paper (C.K. Roy and J.R. Cordy, "A
  Survey on Software Clone Detection Research", 2007) defines a type-1
  clone as identical code fragments except for variations in whitespace,
  layout, and comments — and separately enumerates the small per-line
  editing operations (adding a blank line, inserting a comment, changing
  layout whitespace) this suite's ``TestRoyCordyEditingScenarios`` covers.
- Bellon and colleagues' 2007 reference-clone work (S. Bellon, R. Koschke,
  G. Antoniol, J. Krinke, and E. Merlo, "Comparison and Evaluation of Clone
  Detection Tools", 2007) built a reference corpus of clone/non-clone pairs
  to grade detector output against; ``TestBellonReferenceClones`` mirrors
  that judged-pair structure (a clone pair a detector must accept, and
  near-miss pairs — renamed identifiers, changed literals — it must reject
  as NOT type-1, since those are type-2 territory).
"""

from __future__ import annotations

from aspergillus.duplicates import (
    extract_function_records,
    find_type1_duplicate_groups,
)


def _is_type1(source_a: str, source_b: str) -> bool:
    records = extract_function_records(source_a, "a.py") + extract_function_records(
        source_b, "b.py"
    )
    groups = find_type1_duplicate_groups(records, min_lines=1, allowlist=frozenset())
    return len(groups) == 1


class TestRoyCordyEditingScenarios:
    """Roy & Cordy (2007) type-1 editing scenarios: whitespace, layout, comments."""

    def test_blank_line_insertion_is_type1(self) -> None:
        a = "def merge(a, b):\n    return a + b\n"
        b = "def merge(a, b):\n\n    return a + b\n"
        assert _is_type1(a, b)

    def test_comment_insertion_is_type1(self) -> None:
        a = "def merge(a, b):\n    return a + b\n"
        b = "def merge(a, b):\n    # combine the two values\n    return a + b\n"
        assert _is_type1(a, b)

    def test_operator_spacing_change_is_type1(self) -> None:
        a = "def merge(a, b):\n    return a+b\n"
        b = "def merge(a, b):\n    return a + b\n"
        assert _is_type1(a, b)

    def test_leading_comment_and_blank_lines_combined_is_type1(self) -> None:
        a = "def foo(x):\n    # add one\n    return x + 1\n"
        b = "def foo(x):\n\n    return x+1\n"
        assert _is_type1(a, b)


class TestBellonReferenceClones:
    """Bellon et al. (2007) judged clone/non-clone reference pairs."""

    def test_reference_clone_pair_is_type1(self) -> None:
        a = "def compute_total(items):\n    total = 0\n    for item in items:\n        total += item.price * item.qty\n    return total\n"
        b = "def compute_total(items):\n\n    total = 0\n    for item in items:\n        total += item.price * item.qty\n    return total\n"
        assert _is_type1(a, b)

    def test_renamed_identifier_pair_is_not_type1(self) -> None:
        a = "def foo(x):\n    return x + 1\n"
        b = "def bar(y):\n    return y + 1\n"
        assert not _is_type1(a, b)

    def test_changed_literal_pair_is_not_type1(self) -> None:
        a = "def foo(x):\n    return x + 1\n"
        b = "def foo(x):\n    return x + 2\n"
        assert not _is_type1(a, b)

    def test_structurally_different_pair_is_not_type1(self) -> None:
        a = "def f(x):\n    return x + 1\n"
        b = "def f(x):\n    return x * 1\n"
        assert not _is_type1(a, b)


class TestReportFields:
    """Each detected type-1 pair carries a clone-type label and a similarity score."""

    def test_type1_pair_reports_label_and_score(self) -> None:
        a = "def foo(x):\n    # step one\n    return x + 1\n"
        b = "def foo(x):\n\n\n    return x + 1\n"
        records = extract_function_records(a, "a.py") + extract_function_records(b, "b.py")
        (group,) = find_type1_duplicate_groups(records, min_lines=1, allowlist=frozenset())
        assert group.clone_type == "type-1"
        assert group.similarity >= 0.95


class TestBoilerplateExclusion:
    """Trivial dunders, one-line getters, and pass-only bodies never report."""

    def test_trivial_dunder_pair_not_reported(self) -> None:
        a = 'def __repr__(self):\n    return f"<{type(self).__name__}>"\n'
        b = 'def __repr__(self):\n    return f"<{type(self).__name__}>"\n'
        assert not _is_type1(a, b)

    def test_one_line_getter_pair_not_reported(self) -> None:
        a = "def get_x(self):\n    return self._x\n"
        b = "def get_x(self):\n    return self._x\n"
        assert not _is_type1(a, b)

    def test_pass_only_pair_not_reported(self) -> None:
        a = "def noop(self):\n    pass\n"
        b = "def noop(self):\n    pass\n"
        assert not _is_type1(a, b)

    def test_real_duplicated_logic_still_reported(self) -> None:
        a = "def compute_total(items):\n    total = 0\n    for item in items:\n        total += item.price * item.qty\n    return total\n"
        b = "def compute_total(items):\n\n    total = 0\n    for item in items:\n        total += item.price * item.qty\n    return total\n"
        assert _is_type1(a, b)
