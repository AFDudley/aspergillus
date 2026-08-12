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


# --- exo-314.2: three distinct string node kinds collapsed to one token ------
#
# Both functions below are real shapes taken from exophial's group 45c567e5a4a9,
# which held 17 members spanning 3 to 16 lines. `worker_branch_name` returns one
# interpolation; `build_prompt` returns a six-part concatenation carrying three
# interpolations. They share only "has a docstring" and "returns a string".
_SHORT_FSTRING_RETURN = '''
def worker_branch_name(worker_id: str) -> str:
    """Pure: the `worker/<id>` branch name a captured commit lands on."""
    return f"worker/{worker_id}"
'''
_LONG_CONCATENATED_RETURN = '''
def build_prompt(citation: Citation) -> str:
    """Pure: the classification prompt for one citation."""
    return (
        "You verify whether a document's citation is honest.\\n\\n"
        f"The document credits this claim to: {citation.cited_source!r}\\n"
        f"Claim: {citation.claim}\\n\\n"
        f"Primary source text located for this citation:\\n{citation.source_text}\\n\\n"
        "Respond with the verdict and a one-sentence rationale."
    )
'''


class TestStringKindsAreDistinguished:
    """A docstring, an f-string and a concatenation are not one token (exo-314.2)."""

    def test_short_interpolation_is_not_a_clone_of_a_long_concatenation(self) -> None:
        short = extract_function_records(_SHORT_FSTRING_RETURN, "reroute.py")
        long_ = extract_function_records(_LONG_CONCATENATED_RETURN, "citation.py")
        assert short[0].normalized_hash != long_[0].normalized_hash

    def test_plain_string_return_is_not_a_clone_of_an_interpolated_return(self) -> None:
        plain = extract_function_records('def f(x):\n    return "worker/one"\n', "a.py")
        interp = extract_function_records('def f(x):\n    return f"worker/{x}"\n', "b.py")
        assert plain[0].normalized_hash != interp[0].normalized_hash

    def test_interpolation_count_changes_the_hash(self) -> None:
        one = extract_function_records('def f(a, b):\n    return f"{a}"\n', "a.py")
        two = extract_function_records('def f(a, b):\n    return f"{a}{b}"\n', "b.py")
        assert one[0].normalized_hash != two[0].normalized_hash

    def test_concatenation_arity_changes_the_hash(self) -> None:
        two = extract_function_records('def f():\n    return "a" "b"\n', "a.py")
        three = extract_function_records('def f():\n    return "a" "b" "c"\n', "b.py")
        assert two[0].normalized_hash != three[0].normalized_hash

    def test_literal_values_still_collapse(self) -> None:
        """The type-2 promise survives: only VALUES are dropped, not structure."""
        a = extract_function_records('def f(x):\n    return f"worker/{x}"\n', "a.py")
        b = extract_function_records('def g(y):\n    return f"agent-{y}"\n', "b.py")
        assert a[0].normalized_hash == b[0].normalized_hash


# --- exo-314.1: the size floor is applied to the group MAXIMUM ---------------
_THREE_LINE_CLONE = """
def short(a):
    return sorted(a)
"""
_SEVEN_LINE_CLONE = """
def long_one(collection):
    return sorted(
        collection
    )
"""


class TestMinLinesAppliesPerMember:
    """`--min-lines` is a promise about every reported member (exo-314.1)."""

    def _mixed(self) -> list:
        return extract_function_records(_THREE_LINE_CLONE, "short.py") + extract_function_records(
            _SEVEN_LINE_CLONE, "long.py"
        )

    def test_member_below_the_floor_is_never_reported(self) -> None:
        groups = find_duplicate_groups(self._mixed(), min_lines=4, allowlist=frozenset())
        reported = [m for group in groups for m in group.members]
        assert all(m.n_lines >= 4 for m in reported), [(m.path, m.n_lines) for m in reported]

    def test_a_group_left_with_one_member_is_not_a_group(self) -> None:
        assert find_duplicate_groups(self._mixed(), min_lines=4, allowlist=frozenset()) == []

    def test_group_span_is_the_smallest_reported_member(self) -> None:
        groups = find_duplicate_groups(self._mixed(), min_lines=1, allowlist=frozenset())
        assert len(groups) == 1
        assert groups[0].n_lines == min(m.n_lines for m in groups[0].members)

    def test_short_member_is_not_admitted_by_a_long_sibling(self) -> None:
        """exo-314.1 as it fired: a 3-line member rode in on a 16-line one."""
        records = extract_function_records(
            _SHORT_FSTRING_RETURN, "reroute.py"
        ) + extract_function_records(_LONG_CONCATENATED_RETURN, "citation.py")
        groups = find_duplicate_groups(records, min_lines=5, allowlist=frozenset())
        assert [m.name for group in groups for m in group.members if m.n_lines < 5] == []


# --- exo-eec: the normalizer renames a match singleton into an invalid node ---
_MATCH_SINGLETON = """
def pick(latest: object) -> str:
    match latest:
        case None:
            return "none"
        case True:
            return "yes"
        case _:
            return "other"
"""


class TestMatchSingleton:
    """`case None:` is hashed, not crashed on (exo-eec)."""

    def test_match_singleton_is_hashed(self) -> None:
        records = extract_function_records(_MATCH_SINGLETON, "post_merge_realize.py")
        assert [r.name for r in records] == ["pick"]

    def test_match_singletons_are_not_interchangeable(self) -> None:
        none_arm = extract_function_records(
            'def f(x):\n    match x:\n        case None:\n            return "a"\n', "a.py"
        )
        true_arm = extract_function_records(
            'def f(x):\n    match x:\n        case True:\n            return "a"\n', "b.py"
        )
        assert none_arm[0].normalized_hash != true_arm[0].normalized_hash


# --- exo-ed84: the hash is taken over rendered source, so layout changes it ---
_WRAPPED_SIGNATURE = """
def escalation_view(
    b: int,
) -> tuple[list[dict[str, Any]], str]:
    blocks = [{"type": "section", "text": b}]
    return (blocks, "esc")
"""
_ONE_LINE_SIGNATURE = """
def escalation_view(b: int) -> tuple[list[dict[str, Any]], str]:
    blocks = [{"type": "section", "text": b}]
    return (blocks, "esc")
"""
_COMMENTED = """
def escalation_view(b: int) -> tuple[list[dict[str, Any]], str]:
    # Build the section block first, then label it.

    blocks = [{"type": "section", "text": b}]
    return (blocks, "esc")
"""


class TestLayoutDoesNotChangeTheHash:
    """Type-2 clones ignore whitespace, layout and comments (exo-ed84)."""

    def test_signature_wrapping_does_not_change_the_hash(self) -> None:
        wrapped = extract_function_records(_WRAPPED_SIGNATURE, "a.py")
        flat = extract_function_records(_ONE_LINE_SIGNATURE, "b.py")
        assert wrapped[0].normalized_hash == flat[0].normalized_hash

    def test_comments_and_blank_lines_do_not_change_the_hash(self) -> None:
        flat = extract_function_records(_ONE_LINE_SIGNATURE, "b.py")
        commented = extract_function_records(_COMMENTED, "c.py")
        assert flat[0].normalized_hash == commented[0].normalized_hash

    def test_leading_blank_lines_do_not_change_the_hash(self) -> None:
        first = extract_function_records("def f(x):\n    return x + 1\n", "a.py")
        later = extract_function_records(
            "def other():\n    pass\n\n\n# a note\ndef f(x):\n    return x + 1\n", "b.py"
        )
        assert first[0].normalized_hash == later[1].normalized_hash


# exo-ed84 as it was observed: a `View` alias replaces a verbose return
# annotation on several view builders, ruff-format then collapses each
# multi-line signature onto one line, and functions whose bodies never changed
# are suddenly a duplicate group. The two module bodies below are the parent
# commit and the annotation-only child.
_ED84_PARENT = """
View = tuple[list[dict[str, Any]], str]


def ack_view(a: int) -> tuple[list[dict[str, Any]], str]:
    blocks = [{"type": "section", "text": a}]
    return (blocks, "ack")


def escalation_view(
    b: int,
) -> tuple[list[dict[str, Any]], str]:
    blocks = [{"type": "section", "text": b}]
    return (blocks, "esc")
"""
_ED84_CHILD = """
View = tuple[list[dict[str, Any]], str]


def ack_view(a: int) -> View:
    blocks = [{"type": "section", "text": a}]
    return (blocks, "ack")


def escalation_view(b: int) -> View:
    blocks = [{"type": "section", "text": b}]
    return (blocks, "esc")
"""


class TestAnnotationOnlyEditKeepsTheVerdict:
    """exo-ed84 c1: an annotation swap plus its reformat is verdict-neutral.

    The invariant is the VERDICT, not the hash. Replacing
    ``tuple[list[dict[str, Any]], str]`` with ``View`` genuinely changes the
    annotation's structure, so the hash moves — but it moves the same way for
    every function that shared the annotation, so the grouping does not.
    """

    def _verdict(self, source: str) -> list:
        return find_duplicate_groups(
            extract_function_records(source, "blocks.py"), min_lines=1, allowlist=frozenset()
        )

    def test_group_count_is_unchanged(self) -> None:
        before = self._verdict(_ED84_PARENT)
        after = self._verdict(_ED84_CHILD)
        assert len(before) == len(after)

    def test_group_membership_is_unchanged(self) -> None:
        before = [{m.name for m in g.members} for g in self._verdict(_ED84_PARENT)]
        after = [{m.name for m in g.members} for g in self._verdict(_ED84_CHILD)]
        assert before == after

    def test_distinct_bodies_stay_clean_across_the_swap(self) -> None:
        """The other half of c1: a non-duplicate file stays at zero groups."""
        parent = (
            "\ndef one(a: int) -> tuple[list[dict[str, Any]], str]:\n"
            '    return (sorted(a), "one")\n\n\n'
            "def two(\n    b: int,\n) -> tuple[list[dict[str, Any]], str]:\n"
            '    return (len(b) + 1, "two")\n'
        )
        child = (
            "\ndef one(a: int) -> View:\n"
            '    return (sorted(a), "one")\n\n\n'
            "def two(b: int) -> View:\n"
            '    return (len(b) + 1, "two")\n'
        )
        assert self._verdict(parent) == [] == self._verdict(child)


# --- exo-4be: the size floor measured the SPAN, so prose decided the verdict --
#
# The defect is bidirectional. Moving a docstring OUT drops a function under the
# floor and hides a group; writing one IN pushes a function over and manufactures
# one. Both are edits that change no behaviour.
_PROSE_HEAVY_A = '''
def error_template() -> list[str]:
    """The bug-report battery.

    Ten keys, including the three ODC open-time attributes, reached through the
    error door. A filer answers each one; a blank answer is refused at the door
    rather than carried into the pebble body, because a capture that collected
    nothing is a provenance anchor pointing at nothing.

    See exo-4b9 for the expected-versus-actual rule this battery encodes.
    """
    return list(_ERROR_QUESTIONS)
'''
_PROSE_HEAVY_B = '''
def feature_template() -> list[str]:
    """The feature-request battery.

    Seven keys reached through the feature door. A feature asks for a capability
    that does not exist yet, so there is no observed-versus-expected pair to
    record and the battery is correspondingly shorter.

    The door choice is the filer's, and it is not inferred from the prose.
    """
    return list(_FEATURE_QUESTIONS)
'''
_BODYLESS_HOOK = '''
class Backend:
    def cancel(self, task_id: str) -> None:
        """Cancel one in-flight task.

        A default no-op. A backend that can cancel overrides this; one that
        cannot inherits the no-op rather than raising, because a fleet-wide
        cancellation is not what a CLOSED pebble asks for (exo-6ff).
        """

    def cleanup(self, task_id: str) -> None:
        """Release a resource that outlives the worker process.

        A default no-op. The tmux backend overrides it to kill the pane; the
        subprocess backend has nothing to release once the process is reaped.
        """
'''


class TestFloorMeasuresCodeNotSpan:
    """``--min-lines`` is a floor on CODE; a docstring does not clear it (exo-4be)."""

    def test_code_size_excludes_the_docstring(self) -> None:
        (record,) = extract_function_records(_PROSE_HEAVY_A, "templates.py")
        assert record.n_lines > 5
        assert record.n_code_lines == 2

    def test_prose_does_not_carry_a_pair_over_the_floor(self) -> None:
        records = extract_function_records(_PROSE_HEAVY_A, "a.py") + extract_function_records(
            _PROSE_HEAVY_B, "b.py"
        )
        assert records[0].normalized_hash == records[1].normalized_hash, "same shape"
        assert find_duplicate_groups(records, min_lines=5, allowlist=frozenset()) == []

    def test_a_body_less_hook_is_never_reported(self) -> None:
        """Two docstring-only overrides have no code to be a clone of."""
        records = extract_function_records(_BODYLESS_HOOK, "backend.py")
        assert [r.n_code_lines for r in records] == [1, 1]
        assert find_duplicate_groups(records, min_lines=5, allowlist=frozenset()) == []

    def test_writing_a_docstring_manufactures_nothing(self) -> None:
        """The other direction: documenting a sub-floor helper adds no group."""
        bare = "def a(x):\n    return sorted(x)\n\n\ndef b(y):\n    return sorted(y)\n"
        documented = (
            'def a(x):\n    """Sort it."""\n    return sorted(x)\n\n\n'
            'def b(y):\n    """Sort it."""\n    return sorted(y)\n'
        )
        floor = 3
        assert find_duplicate_groups(
            extract_function_records(bare, "a.py"), floor, frozenset()
        ) == find_duplicate_groups(extract_function_records(documented, "b.py"), floor, frozenset())


# --- exo-314, one level deeper: a total dispatcher's discriminants ARE its code -
#
# `match cell.<aspect>: case <flagged>: return <Situation>; case _: assert_never`
# says nothing else. Normalization erased the aspect, the flagged value and the
# returned member, so nine unrelated band checks became one group that must never
# be folded: with match + assert_never mypy --strict rejects a newly added aspect
# value, and a generic helper leaves mypy silent.
_DISPATCH_MAIN_CHECKOUT = '''
def _check_main_checkout(cell: PebbleFacts) -> Situation | None:
    """Band 0."""
    match cell.main_checkout_cleanliness:
        case "dirty_foreign_tree":
            return Situation.MAIN_CHECKOUT_DIRTY_AFTER_FAILED_MERGE
        case "clean":
            return None
        case _:
            assert_never(cell.main_checkout_cleanliness)
'''
_DISPATCH_CLAIM = '''
def _check_claim(cell: PebbleLifecycleCell) -> LifecycleSituation | None:
    """Band 2."""
    match cell.claim:
        case "held_by_dead_worker":
            return LifecycleSituation.CLAIM_STRANDED
        case "unheld":
            return None
        case _:
            assert_never(cell.claim)
'''
_DISPATCH_SAME_ASPECT_OTHER_ENUM = '''
def _check_main_checkout(cell: IntegrateLaneCell) -> LaneSituation | None:
    """Band 0 of the OTHER lane: same aspect, same flagged value, other enum."""
    match cell.main_checkout_cleanliness:
        case "dirty_foreign_tree":
            return LaneSituation.MAIN_CHECKOUT_DIRTY_FOREIGN_TREE
        case "clean":
            return None
        case _:
            assert_never(cell.main_checkout_cleanliness)
'''
_DISPATCH_COPY_PASTE = '''
def _check_main_checkout_again(cell: PebbleFacts) -> Situation | None:
    """A real copy-paste of band 0 under a new name."""
    match cell.main_checkout_cleanliness:
        case "dirty_foreign_tree":
            return Situation.MAIN_CHECKOUT_DIRTY_AFTER_FAILED_MERGE
        case "clean":
            return None
        case _:
            assert_never(cell.main_checkout_cleanliness)
'''


class TestTotalDispatchersKeepTheirDiscriminants:
    """The subject, patterns and returned values of a total dispatcher are code.

    This is NOT an exemption: nothing is suppressed. The hash stops discarding
    the only part of a total dispatcher that differs, so genuinely different
    dispatchers are DISTINGUISHED and a genuine copy-paste is still caught.
    """

    def _groups(self, *sources: str) -> list:
        records: list = []
        for index, source in enumerate(sources):
            records += extract_function_records(source, f"m{index}.py")
        return find_duplicate_groups(records, min_lines=1, allowlist=frozenset())

    def test_different_aspects_are_not_duplicates(self) -> None:
        assert self._groups(_DISPATCH_MAIN_CHECKOUT, _DISPATCH_CLAIM) == []

    def test_the_returned_member_alone_separates_them(self) -> None:
        """Same attribute, same flagged value; only the enum member differs.

        Subject and patterns alone would leave these two colliding, which is why
        the returned expression is part of the discriminant and not optional.
        """
        assert self._groups(_DISPATCH_MAIN_CHECKOUT, _DISPATCH_SAME_ASPECT_OTHER_ENUM) == []

    def test_a_genuine_copy_paste_is_still_reported(self) -> None:
        """Main's proof (a): the fix keys on discriminants, never on ``match``."""
        groups = self._groups(_DISPATCH_MAIN_CHECKOUT, _DISPATCH_COPY_PASTE)
        assert len(groups) == 1
        assert {m.name for m in groups[0].members} == {
            "_check_main_checkout",
            "_check_main_checkout_again",
        }

    def test_a_non_dispatcher_duplicate_is_still_reported(self) -> None:
        """Main's proof (b): fixing the floor did not quietly raise it."""
        body = "\n".join(
            [
                "def {name}(items, limit):",
                "    kept = [x for x in items if x > limit]",
                "    kept.sort()",
                "    total = sum(kept)",
                "    if not kept:",
                "        return 0",
                "    return total / len(kept)",
            ]
        )
        groups = self._groups(body.format(name="mean_above"), body.format(name="avg_over"))
        assert len(groups) == 1
        assert groups[0].n_lines >= 7

    def test_the_rule_is_selectors_not_the_match_keyword(self) -> None:
        """A partial match separates on selectors too; ``assert_never`` is not the rule."""
        partial = (
            "def pick(cell):\n    match cell.a:\n"
            '        case "x":\n            return One.A\n'
            "        case _:\n            return None\n"
        )
        other = (
            "def choose(cell):\n    match cell.b:\n"
            '        case "y":\n            return Two.B\n'
            "        case _:\n            return None\n"
        )
        assert self._groups(partial, other) == []
        assert len(self._groups(partial, partial.replace("pick", "pick_again"))) == 1

    def test_a_selector_only_difference_separates_two_projections(self) -> None:
        """exo-314, third layer: keys, keywords and constructed types are selectors."""
        one = (
            "def parse_list_all(raw):\n"
            "    return _map(raw, lambda item: PebbleRecord(\n"
            '        id=PebbleId(str(item["id"])),\n'
            '        status=str(item.get("status", "")),\n'
            '        priority=str(item.get("priority", "")),\n'
            "    ))\n"
        )
        two = (
            "def parse_all_goals(raw):\n"
            "    return _map(raw, lambda item: GoalRecord(\n"
            '        id=PebbleId(str(item["id"])),\n'
            '        title=str(item.get("title", "")),\n'
            '        description=str(item.get("description", "")),\n'
            "    ))\n"
        )
        assert self._groups(one, two) == []
        assert len(self._groups(one, one.replace("parse_list_all", "parse_again"))) == 1
