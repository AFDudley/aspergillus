"""Whole-project type-2 duplicate-function detector (functional core).

This is the pure computation behind the ``aspergillus check-duplicates``
CLI subcommand (wired in ``__main__.py``). It exists as a SEPARATE
whole-project CLI tool rather than a ``fixit.LintRule`` because fixit's
LintRule mechanism is single-file only, and the thing worth detecting —
the SAME function body copy-pasted across MANY different files (e.g. the
22 duplicated ``_git()`` test helpers exophial's exo-c3a consolidated) —
is a cross-file fact a per-file CST rule structurally cannot see. LibCST
is just the parser here; the grouping happens across the whole corpus.
Pebble: asp-21d.

Approach (standard type-2 clone normalization):

1. Parse each file with LibCST (``extract_function_records``).
2. For every ``FunctionDef`` (including methods and nested functions),
   normalize the node: every identifier (``Name``) collapses to a single
   placeholder and every literal collapses to a type-only marker, so
   functions that differ ONLY by naming / literal values hash the same.
3. Hash the rendered normalized node; group records by hash across ALL
   files (``find_duplicate_groups``).
4. Report any hash bucket with >1 member whose function span is at least
   ``min_lines`` and whose hash is not allow-listed.

All functions in this module are pure: they take source strings / records
and return records / groups / formatted text. Filesystem reads, argument
parsing and stdout writes live in ``__main__.py`` (the imperative shell).
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

# Placeholder every identifier collapses to under type-2 normalization.
_NAME_PLACEHOLDER = "_ID"
# Type-only markers literals collapse to (type-2 drops literal VALUES but
# keeps the token TYPE). Each numeric marker must itself be a syntactically
# valid literal of that node's kind — libcst validates on construction.
_STR_MARKER = '"_STR"'
_INT_MARKER = "0"
_FLOAT_MARKER = "0.0"
_IMAGINARY_MARKER = "0j"


@dataclass(frozen=True)
class FunctionRecord:
    """One function/method, with its type-2-normalized structural hash.

    ``normalized_hash`` is equal for two functions that are identical up to
    identifier renaming and literal values; ``n_lines`` is the source span
    (end line - start line + 1) used for the ``min_lines`` size floor.
    """

    path: str
    name: str
    line: int
    n_lines: int
    normalized_hash: str


@dataclass(frozen=True)
class DuplicateGroup:
    """A hash bucket with more than one member — a duplicate cluster."""

    normalized_hash: str
    n_lines: int
    members: tuple[FunctionRecord, ...]


class _Normalizer(cst.CSTTransformer):
    """Collapse identifiers to a placeholder and literals to type markers.

    This is what makes the hash a *type-2* clone signature: two functions
    that differ only in the names of their locals/args/attributes or in the
    concrete values of their literals normalize to the same tree. Operators,
    call/attribute/statement STRUCTURE and control flow are all preserved, so
    genuinely different logic keeps a different hash.
    """

    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name) -> cst.Name:
        return updated_node.with_changes(value=_NAME_PLACEHOLDER)

    def leave_SimpleString(
        self, original_node: cst.SimpleString, updated_node: cst.SimpleString
    ) -> cst.SimpleString:
        return updated_node.with_changes(value=_STR_MARKER)

    def leave_FormattedString(
        self, original_node: cst.FormattedString, updated_node: cst.FormattedString
    ) -> cst.BaseString:
        return cst.SimpleString(value=_STR_MARKER)

    def leave_ConcatenatedString(
        self, original_node: cst.ConcatenatedString, updated_node: cst.ConcatenatedString
    ) -> cst.BaseString:
        return cst.SimpleString(value=_STR_MARKER)

    def leave_Integer(self, original_node: cst.Integer, updated_node: cst.Integer) -> cst.Integer:
        return updated_node.with_changes(value=_INT_MARKER)

    def leave_Float(self, original_node: cst.Float, updated_node: cst.Float) -> cst.Float:
        return updated_node.with_changes(value=_FLOAT_MARKER)

    def leave_Imaginary(
        self, original_node: cst.Imaginary, updated_node: cst.Imaginary
    ) -> cst.Imaginary:
        return updated_node.with_changes(value=_IMAGINARY_MARKER)


class _FunctionCollector(cst.CSTVisitor):
    """Collect every ``FunctionDef`` with its source-span start/end lines."""

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self) -> None:
        self.functions: list[tuple[cst.FunctionDef, int, int]] = []

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        pos = self.get_metadata(PositionProvider, node)
        self.functions.append((node, pos.start.line, pos.end.line))


def _hash_function(module: cst.Module, func: cst.FunctionDef) -> str:
    """Render ``func`` under type-2 normalization and return its sha256 hex."""
    normalized = func.visit(_Normalizer())
    # _Normalizer only rewrites leaf values; it never removes the root node,
    # so visiting a FunctionDef always yields a FunctionDef. Narrow for mypy.
    assert isinstance(normalized, cst.FunctionDef)
    code = module.code_for_node(normalized)
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def extract_function_records(source: str, path: str) -> list[FunctionRecord]:
    """Parse ``source`` and return a normalized record per function it defines.

    Pure: parsing and hashing only, no IO. Raises ``cst.ParserSyntaxError``
    on unparseable input — the caller (shell) decides how to handle a file
    that will not parse.
    """
    module = cst.parse_module(source)
    wrapper = MetadataWrapper(module)
    collector = _FunctionCollector()
    wrapper.visit(collector)
    return [
        FunctionRecord(
            path=path,
            name=node.name.value,
            line=start,
            n_lines=end - start + 1,
            normalized_hash=_hash_function(module, node),
        )
        for node, start, end in collector.functions
    ]


def parse_allowlist(text: str) -> frozenset[str]:
    """Parse an allowlist file body into the set of accepted hashes.

    Format mirrors exophial's ``scripts/vulture_whitelist.py`` intent — a
    config file of accepted false positives, each with a citing comment.
    Here each non-comment, non-blank line is one accepted ``normalized_hash``
    (the value ``check-duplicates`` prints for every reported group, so a
    reviewer copies it in with a ``#`` comment explaining WHY the structural
    similarity is legitimate).
    """
    return frozenset(
        stripped for line in text.splitlines() if (stripped := line.split("#", 1)[0].strip())
    )


def find_duplicate_groups(
    records: list[FunctionRecord],
    min_lines: int,
    allowlist: frozenset[str],
) -> list[DuplicateGroup]:
    """Group records by hash; return buckets that are real duplicate clusters.

    A bucket qualifies when it has >1 member, its largest member spans at
    least ``min_lines`` lines, and its hash is not in ``allowlist``. Groups
    are returned largest-span first (most significant duplication on top).
    """
    buckets: dict[str, list[FunctionRecord]] = defaultdict(list)
    for record in records:
        buckets[record.normalized_hash].append(record)

    groups = [
        DuplicateGroup(
            normalized_hash=hash_,
            n_lines=max(member.n_lines for member in members),
            members=tuple(sorted(members, key=lambda member: (member.path, member.line))),
        )
        for hash_, members in buckets.items()
        if len(members) > 1
        and hash_ not in allowlist
        and max(member.n_lines for member in members) >= min_lines
    ]
    return sorted(groups, key=lambda group: (-group.n_lines, group.normalized_hash))


def format_report(groups: list[DuplicateGroup]) -> str:
    """Render duplicate groups as a human-readable report string."""
    if not groups:
        return "check-duplicates: no duplicate functions found."

    total = sum(len(group.members) for group in groups)
    header = f"check-duplicates: {len(groups)} duplicate group(s), {total} function(s) involved.\n"
    blocks = [
        "\n".join(
            [
                f"  group {group.normalized_hash[:12]} "
                f"({len(group.members)} copies, ~{group.n_lines} lines each):",
                *[f"    {member.path}:{member.line}  {member.name}" for member in group.members],
                f"    allowlist with: {group.normalized_hash}",
            ]
        )
        for group in groups
    ]
    return header + "\n\n".join(blocks) + "\n"
