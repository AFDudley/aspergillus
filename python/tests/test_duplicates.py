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


_MATCH_NONE = """
def handle_none(x):
    match x:
        case None:
            return 1
        case _:
            return 0
"""
_MATCH_TRUE = """
def handle_true(x):
    match x:
        case True:
            return 1
        case _:
            return 0
"""
_MATCH_FALSE = """
def handle_false(x):
    match x:
        case False:
            return 1
        case _:
            return 0
"""


class TestMatchSingletonNormalization:
    """A ``case True``/``case False``/``case None`` pattern keeps its keyword.

    ``cst.MatchSingleton`` accepts only the literal ``True``, ``False``, or
    ``None`` as its value. The normalizer must not rewrite that ``Name`` to
    the identifier placeholder, or LibCST's own validation rejects the
    rewritten tree. Pebble: asp-63a.
    """

    def test_case_none_does_not_raise(self) -> None:
        extract_function_records(_MATCH_NONE, "none.py")

    def test_case_true_does_not_raise(self) -> None:
        extract_function_records(_MATCH_TRUE, "true.py")

    def test_case_false_does_not_raise(self) -> None:
        extract_function_records(_MATCH_FALSE, "false.py")

    def test_case_true_and_case_false_hash_differently(self) -> None:
        true_records = extract_function_records(_MATCH_TRUE, "true.py")
        false_records = extract_function_records(_MATCH_FALSE, "false.py")
        assert true_records[0].normalized_hash != false_records[0].normalized_hash

    def test_case_none_and_case_true_hash_differently(self) -> None:
        none_records = extract_function_records(_MATCH_NONE, "none.py")
        true_records = extract_function_records(_MATCH_TRUE, "true.py")
        assert none_records[0].normalized_hash != true_records[0].normalized_hash


# Two distinct functions that differ only in a long docstring and a one-line
# body. Their code is not duplicated in any meaningful amount, so the docstring
# must not inflate them over the size floor.
_DOCSTRING_HEAVY_A = '''
def plural_of(noun):
    """The regular plural of a noun.

    Every derived noun needs one. A long rationale sits here across several
    lines, but the body below is a single delegating call.
    """
    return _inflected(noun, _plural)
'''
_DOCSTRING_HEAVY_B = '''
def third_person_of(verb):
    """The third-person singular of a verb.

    A different rationale entirely, also several lines long, explaining why the
    verb case shares the one regular rule.
    """
    return _inflected(verb, _plural)
'''

# A genuine multi-statement clone: five lines of real code, no docstring.
_BIG_A = '''
def a(xs, ys):
    total = 0
    for item in xs:
        if item in ys:
            total += item
    return total
'''
_BIG_B = '''
def b(ps, qs):
    total = 0
    for element in ps:
        if element in qs:
            total += element
    return total
'''


class TestDocstringDoesNotInflateCloneSize:
    """A long docstring must not push a one-line-body function over min_lines."""

    def test_n_lines_is_the_code_span_not_the_docstring_span(self) -> None:
        (record,) = extract_function_records(_DOCSTRING_HEAVY_A, "a.py")
        assert record.n_lines < 5

    def test_docstring_heavy_clones_are_detected_but_below_the_code_floor(self) -> None:
        records = extract_function_records(_DOCSTRING_HEAVY_A, "a.py") + extract_function_records(
            _DOCSTRING_HEAVY_B, "b.py"
        )
        assert len(find_duplicate_groups(records, min_lines=1, allowlist=frozenset())) == 1
        assert find_duplicate_groups(records, min_lines=5, allowlist=frozenset()) == []

    def test_a_genuine_multiline_clone_still_clears_the_floor(self) -> None:
        records = extract_function_records(_BIG_A, "a.py") + extract_function_records(
            _BIG_B, "b.py"
        )
        assert len(find_duplicate_groups(records, min_lines=5, allowlist=frozenset())) == 1
