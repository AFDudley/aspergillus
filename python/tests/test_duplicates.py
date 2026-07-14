"""Tests for the duplicate-function detector core (duplicates.py).

These exercise the PURE functions — normalize/hash (via extract_function_records),
cross-file grouping, allowlist parsing, and report formatting. The CLI wiring in
__main__.py is the imperative shell; its subcommand routing is covered end-to-end
by test_cli.py's untouched single-file lint tests plus the acceptance run recorded
in the asp-21d handoff (pre/post exo-c3a exophial test tree). Pebble: asp-21d.
"""

from __future__ import annotations

from aspergillus.duplicates import (
    extract_function_records,
    find_duplicate_groups,
    format_report,
    parse_allowlist,
)

# Two functions identical up to identifier renaming + literal values. Under
# type-2 normalization they MUST hash the same.
_RENAMED_A = """
def fetch(repo, name):
    result = run(["git", "-C", repo, name], check=True)
    return result.stdout.strip()
"""
_RENAMED_B = """
def pull(project, arg):
    outcome = run(["git", "-C", project, arg], check=True)
    return outcome.stdout.strip()
"""


class TestNormalizationAndHashing:
    """Type-2 clones hash equal; structurally-different code hashes distinct."""

    def test_renamed_clone_hashes_equal(self) -> None:
        a = extract_function_records(_RENAMED_A, "a.py")
        b = extract_function_records(_RENAMED_B, "b.py")
        assert a[0].normalized_hash == b[0].normalized_hash

    def test_structural_difference_hashes_differ(self) -> None:
        one = extract_function_records("def f(x):\n    return x + 1\n", "one.py")
        two = extract_function_records("def f(x):\n    return x * 1\n", "two.py")
        assert one[0].normalized_hash != two[0].normalized_hash

    def test_records_capture_name_and_span(self) -> None:
        records = extract_function_records(_RENAMED_A, "a.py")
        assert len(records) == 1
        assert records[0].name == "fetch"
        assert records[0].path == "a.py"
        assert records[0].n_lines == 3

    def test_methods_and_nested_functions_are_collected(self) -> None:
        src = (
            "class C:\n"
            "    def m(self):\n"
            "        def inner():\n"
            "            return 1\n"
            "        return inner\n"
        )
        records = extract_function_records(src, "c.py")
        names = {r.name for r in records}
        assert names == {"m", "inner"}


class TestFindDuplicateGroups:
    """Cross-file grouping, the min_lines floor, and allowlist filtering."""

    def _records(self) -> list:
        return extract_function_records(_RENAMED_A, "a.py") + extract_function_records(
            _RENAMED_B, "b.py"
        )

    def test_cross_file_clone_is_grouped(self) -> None:
        groups = find_duplicate_groups(self._records(), min_lines=1, allowlist=frozenset())
        assert len(groups) == 1
        assert len(groups[0].members) == 2
        assert {m.path for m in groups[0].members} == {"a.py", "b.py"}

    def test_min_lines_floor_excludes_small_clones(self) -> None:
        # The clones span 3 lines; a floor of 10 drops them.
        groups = find_duplicate_groups(self._records(), min_lines=10, allowlist=frozenset())
        assert groups == []

    def test_singletons_are_not_reported(self) -> None:
        records = extract_function_records(_RENAMED_A, "a.py")
        groups = find_duplicate_groups(records, min_lines=1, allowlist=frozenset())
        assert groups == []

    def test_allowlisted_hash_is_suppressed(self) -> None:
        records = self._records()
        target = records[0].normalized_hash
        groups = find_duplicate_groups(records, min_lines=1, allowlist=frozenset({target}))
        assert groups == []


class TestParseAllowlist:
    """Allowlist config parsing: hashes kept, comments/blanks dropped."""

    def test_strips_comments_and_blanks(self) -> None:
        text = "# a citing comment\n\nabc123  # inline reason\n   def456\n"
        assert parse_allowlist(text) == frozenset({"abc123", "def456"})

    def test_empty_text_is_empty_set(self) -> None:
        assert parse_allowlist("# only comments\n\n") == frozenset()


class TestFormatReport:
    """Human-readable rendering of results."""

    def test_clean_message_when_no_groups(self) -> None:
        assert "no duplicate functions" in format_report([])

    def test_report_lists_members_and_hash(self) -> None:
        groups = find_duplicate_groups(
            extract_function_records(_RENAMED_A, "a.py")
            + extract_function_records(_RENAMED_B, "b.py"),
            min_lines=1,
            allowlist=frozenset(),
        )
        report = format_report(groups)
        assert "a.py:2" in report
        assert "b.py:2" in report
        assert "fetch" in report
        assert "allowlist with:" in report
