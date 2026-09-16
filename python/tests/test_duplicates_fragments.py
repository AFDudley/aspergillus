"""Tests for fragment-granular type-2 clone detection (asp-d88.2).

find_duplicate_groups only ever matched an ENTIRE normalized function body,
so a copied statement spine embedded inside two differently-shaped functions
was invisible to it by construction. find_fragment_duplicates slides a
window of normalized statements instead, and find_all_duplicate_groups
combines both, each pair carrying a clone-type label and a similarity score.
Boilerplate (pass-only bodies, one-line getters, dunders) is excluded from
both. The on-disk fixtures under tests/fixtures/asp_* are the same ones the
derived-asp-d88.2 acceptance oracles (tests/oracle_scripts/check_*.py) run
against — read once here so the pytest suite and the oracle scripts never
describe the fixture twice. Pebble: asp-d88.2.
"""

from __future__ import annotations

from pathlib import Path

from aspergillus.duplicates import (
    CLONE_TYPE_FRAGMENT,
    CLONE_TYPE_WHOLE,
    FunctionRecord,
    extract_function_records,
    find_all_duplicate_groups,
    find_duplicate_groups,
    find_fragment_duplicates,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def _scan(fixture_name: str) -> list[FunctionRecord]:
    records: list[FunctionRecord] = []
    for path in sorted((_FIXTURES / fixture_name).glob("*.py")):
        records.extend(extract_function_records(path.read_text(encoding="utf-8"), str(path)))
    return records


def _names(group_members: tuple[FunctionRecord, ...]) -> set[str]:
    return {member.name for member in group_members}


class TestFragmentGranularDetection:
    """A copied spine inside a larger, differently-shaped function is caught."""

    def test_shared_inner_helper_and_block_are_flagged(self) -> None:
        groups = find_all_duplicate_groups(
            _scan("asp_fragment_pair"), min_lines=3, allowlist=frozenset()
        )
        matches = [g for g in groups if _names(g.members) >= {"process_orders", "process_items"}]
        assert matches, "process_orders/process_items spine was not flagged"
        assert matches[0].clone_type == CLONE_TYPE_FRAGMENT
        assert 0.0 < matches[0].similarity < 1.0

    def test_whole_body_clone_still_found_via_the_combined_entrypoint(self) -> None:
        # A plain renamed-clone pair (no fragment needed) still comes through
        # find_all_duplicate_groups, labeled as a whole-body match.
        records = _scan("asp_known_duplicate")
        groups = find_all_duplicate_groups(records, min_lines=1, allowlist=frozenset())
        matches = [g for g in groups if _names(g.members) >= {"fetch_a", "fetch_b"}]
        assert len(matches) == 1
        assert matches[0].clone_type == CLONE_TYPE_WHOLE
        assert matches[0].similarity == 1.0

    def test_fragment_and_whole_body_pair_are_not_double_reported(self) -> None:
        # A pair whose ENTIRE bodies match is reported once (as type-2-whole),
        # not again as a redundant fragment match at the same full length.
        records = _scan("asp_known_duplicate")
        groups = find_all_duplicate_groups(records, min_lines=1, allowlist=frozenset())
        matches = [g for g in groups if _names(g.members) >= {"fetch_a", "fetch_b"}]
        assert len(matches) == 1

    def test_min_statements_floor_excludes_a_too_short_fragment(self) -> None:
        # Only the first statement is shared; the rest diverges in shape
        # (a single return vs. an assignment then a return), so the longest
        # common spine is 1 statement -- below the min_statements=2 floor.
        source_a = "def a(x):\n    helper(x)\n    return 1\n"
        source_b = "def b(y):\n    helper(y)\n    z = 2\n    return z\n"
        records = extract_function_records(source_a, "a.py") + extract_function_records(
            source_b, "b.py"
        )
        groups = find_fragment_duplicates(
            records, min_lines=1, min_statements=2, allowlist=frozenset()
        )
        assert groups == []


class TestBoilerplateExclusion:
    """Pass-only bodies, one-line getters, and dunders never report as clones."""

    def test_shared_boilerplate_is_excluded(self) -> None:
        groups = find_all_duplicate_groups(
            _scan("asp_boilerplate"), min_lines=1, allowlist=frozenset()
        )
        assert groups == []

    def test_boilerplate_flag_is_set_on_the_record(self) -> None:
        init_record, getter_record = extract_function_records(
            "class C:\n"
            "    def __init__(self):\n"
            "        pass\n"
            "    def name(self):\n"
            "        return self._name\n",
            "c.py",
        )
        assert init_record.is_boilerplate
        assert getter_record.is_boilerplate

    def test_non_trivial_dunder_body_is_still_boilerplate_by_name(self) -> None:
        # A one-statement dunder body that is neither pass nor a bare getter
        # (e.g. a formatted __repr__) is still boilerplate: any dunder with a
        # single-statement body is scaffolding, not meaningful duplication.
        (record,) = extract_function_records(
            'def __repr__(self):\n    return f"<{self.x}>"\n', "c.py"
        )
        assert record.is_boilerplate

    def test_multi_statement_dunder_body_is_not_boilerplate(self) -> None:
        (record,) = extract_function_records(
            "def __init__(self, x):\n    self.x = x\n    self.y = x * 2\n", "c.py"
        )
        assert not record.is_boilerplate


class TestRegressionDrivePut:
    """The original report: exophial3's drive.py:drive vs driver.py:put."""

    def test_drive_and_put_are_now_flagged(self) -> None:
        groups = find_all_duplicate_groups(
            _scan("asp_regression_drive_put"), min_lines=3, allowlist=frozenset()
        )
        matches = [g for g in groups if _names(g.members) >= {"drive", "put"}]
        assert matches, "drive/put spine was not flagged"
        assert matches[0].clone_type == CLONE_TYPE_FRAGMENT

    def test_whole_body_hash_alone_still_misses_the_pair(self) -> None:
        # Proves the regression is real: the OLD whole-body-only comparison
        # (find_duplicate_groups) does not see drive/put, because they
        # diverge at the start and the end of the body.
        records = _scan("asp_regression_drive_put")
        whole_only = find_duplicate_groups(records, min_lines=3, allowlist=frozenset())
        assert not any(_names(g.members) >= {"drive", "put"} for g in whole_only)


class TestNamedResearchFixtures:
    """The three fixtures cited by asp-d88.2's restatement clauses c7-c9."""

    def test_roy_cordy_2007_type2_editing_scenario_is_flagged(self) -> None:
        groups = find_all_duplicate_groups(
            _scan("asp_roy_cordy_type2"), min_lines=3, allowlist=frozenset()
        )
        assert any(_names(g.members) >= {"summarize_a", "summarize_b"} for g in groups)

    def test_bellon_2007_reference_clone_is_flagged(self) -> None:
        groups = find_all_duplicate_groups(
            _scan("asp_bellon_reference_clone"), min_lines=3, allowlist=frozenset()
        )
        assert any(_names(g.members) >= {"import_widget", "import_gadget"} for g in groups)

    def test_bigclonebench_2014_t2_pair_is_flagged(self) -> None:
        groups = find_all_duplicate_groups(
            _scan("asp_bigclonebench_t2"), min_lines=3, allowlist=frozenset()
        )
        assert any(_names(g.members) >= {"compute_checksum", "compute_digest"} for g in groups)
