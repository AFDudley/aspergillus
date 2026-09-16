"""Whole-project type-1/type-2 duplicate-function detector (functional core).

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

A second, stricter category is detected the same way: type-1 (exact)
clones per the Roy & Cordy (2007) clone taxonomy. Two function bodies are
a type-1 clone when they are identical once only comments and whitespace
are stripped — no identifier renaming, no literal normalization
(``find_type1_duplicate_groups``). Each function's exact-clone signature
is the sha256 of ``ast.dump`` of its body: the standard ``ast`` module
already discards comments and layout while preserving identifier names
and literal values exactly, which is precisely the type-1 equivalence.
Trivial boilerplate (dunders, one-line getters, pass-only bodies) is
excluded from type-1 reports (``is_boilerplate``) — pebble asp-d88.1.

All functions in this module are pure: they take source strings / records
and return records / groups / formatted text. Filesystem reads, argument
parsing and stdout writes live in ``__main__.py`` (the imperative shell).
"""

from __future__ import annotations

import ast
import hashlib
import re
import textwrap
from collections import defaultdict
from dataclasses import dataclass

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

# A dunder method name: "__init__", "__repr__", etc.
_DUNDER_NAME_RE = re.compile(r"^__[A-Za-z0-9_]+__$")

TYPE1_LABEL = "type-1"

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
    identifier renaming and literal values; ``n_lines`` is the CODE-line span —
    the function span minus a leading docstring — used for the ``min_lines``
    size floor, so prose never inflates a clone's measured size.

    ``type1_hash`` is equal only for functions identical once comments and
    whitespace are stripped (the Roy & Cordy (2007) type-1/exact clone
    signature). ``is_boilerplate`` marks a trivial dunder, one-line getter,
    or pass-only body, excluded from type-1 reports regardless of its hash.
    """

    path: str
    name: str
    line: int
    n_lines: int
    normalized_hash: str
    type1_hash: str
    is_boilerplate: bool


@dataclass(frozen=True)
class DuplicateGroup:
    """A hash bucket with more than one member — a duplicate cluster."""

    normalized_hash: str
    n_lines: int
    members: tuple[FunctionRecord, ...]


@dataclass(frozen=True)
class Type1DuplicateGroup:
    """A cluster of functions that are type-1 (exact) clones of each other.

    ``similarity`` is always 1.0: type-1, by the Roy & Cordy (2007)
    definition, means identical once comments and whitespace are stripped —
    there is no partial-match case to score below a perfect clone.
    """

    type1_hash: str
    clone_type: str
    similarity: float
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

    def visit_MatchSingleton(self, node: cst.MatchSingleton) -> bool:
        # A MatchSingleton's value must stay exactly `True`, `False`, or
        # `None` -- libcst rejects any other Name there. It is a keyword,
        # not an identifier to normalize, and `case True` / `case False`
        # are distinct patterns that must keep distinct hashes. Returning
        # False skips this subtree so leave_Name never sees its value.
        return False

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


def _is_docstring(statement: cst.BaseStatement) -> bool:
    """Whether ``statement`` is a lone string expression — a docstring."""
    if not isinstance(statement, cst.SimpleStatementLine) or len(statement.body) != 1:
        return False
    expr = statement.body[0]
    return isinstance(expr, cst.Expr) and isinstance(
        expr.value, (cst.SimpleString, cst.ConcatenatedString)
    )


class _FunctionCollector(cst.CSTVisitor):
    """Collect every ``FunctionDef`` with its start line and CODE-line span.

    The span excludes a leading docstring: two distinct functions that differ
    only in their docstring and share a one-line body are not real code
    duplication, so their prose must not push them over the ``min_lines`` floor.
    """

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self) -> None:
        self.functions: list[tuple[cst.FunctionDef, int, int]] = []

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        pos = self.get_metadata(PositionProvider, node)
        span = pos.end.line - pos.start.line + 1
        self.functions.append((node, pos.start.line, span - self._docstring_lines(node)))

    def _docstring_lines(self, node: cst.FunctionDef) -> int:
        block = node.body
        if not isinstance(block, cst.IndentedBlock) or not block.body:
            return 0
        first = block.body[0]
        if not _is_docstring(first):
            return 0
        pos = self.get_metadata(PositionProvider, first)
        return pos.end.line - pos.start.line + 1


def _hash_function(module: cst.Module, func: cst.FunctionDef) -> str:
    """Render ``func`` under type-2 normalization and return its sha256 hex."""
    normalized = func.visit(_Normalizer())
    # _Normalizer only rewrites leaf values; it never removes the root node,
    # so visiting a FunctionDef always yields a FunctionDef. Narrow for mypy.
    assert isinstance(normalized, cst.FunctionDef)
    code = module.code_for_node(normalized)
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _hash_function_type1(module: cst.Module, func: cst.FunctionDef) -> str:
    """Return the sha256 of ``func``'s type-1 (exact) clone signature.

    The signature is ``ast.dump`` of the function's body: the standard
    ``ast`` module already discards comments and layout on parse, while
    keeping every identifier name and literal value exactly as written.
    That is precisely the Roy & Cordy (2007) type-1 equivalence — no
    normalization beyond stripping comments and whitespace.
    """
    code = textwrap.dedent(module.code_for_node(func))
    dumped = ast.dump(ast.parse(code), annotate_fields=False)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


def _non_docstring_statements(func: cst.FunctionDef) -> tuple[cst.BaseStatement, ...]:
    """The function's body statements, minus a leading docstring line."""
    block = func.body
    if not isinstance(block, cst.IndentedBlock):
        return ()
    statements = tuple(block.body)
    if statements and _is_docstring(statements[0]):
        return statements[1:]
    return statements


def _is_pass_only(statements: tuple[cst.BaseStatement, ...]) -> bool:
    """Whether ``statements`` is exactly a single ``pass``."""
    if len(statements) != 1 or not isinstance(statements[0], cst.SimpleStatementLine):
        return False
    body = statements[0].body
    return len(body) == 1 and isinstance(body[0], cst.Pass)


def _is_simple_getter_return(statements: tuple[cst.BaseStatement, ...]) -> bool:
    """Whether ``statements`` is a single ``return <name-or-attribute>``.

    A getter that hands back a stored value with no computation — the
    Roy & Cordy boilerplate carve-out never intends to hide a real
    ``return f(x, y)`` behind this check, so only a bare name/attribute
    qualifies.
    """
    if len(statements) != 1 or not isinstance(statements[0], cst.SimpleStatementLine):
        return False
    body = statements[0].body
    if len(body) != 1 or not isinstance(body[0], cst.Return) or body[0].value is None:
        return False
    return isinstance(body[0].value, (cst.Name, cst.Attribute))


def is_boilerplate(name: str, func: cst.FunctionDef) -> bool:
    """Whether ``func`` is trivial boilerplate: a pass-only body, a one-line
    getter, or a single-statement dunder method.

    Boilerplate is excluded from type-1 reports even when it hashes equal —
    two unrelated classes each defining ``def __repr__(self): return ...``
    are not the copy-pasted duplication the detector exists to catch.
    """
    statements = _non_docstring_statements(func)
    if _is_pass_only(statements):
        return True
    if len(statements) == 1 and _DUNDER_NAME_RE.match(name):
        return True
    return _is_simple_getter_return(statements)


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
            n_lines=code_lines,
            normalized_hash=_hash_function(module, node),
            type1_hash=_hash_function_type1(module, node),
            is_boilerplate=is_boilerplate(node.name.value, node),
        )
        for node, start, code_lines in collector.functions
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


def find_type1_duplicate_groups(
    records: list[FunctionRecord],
    min_lines: int,
    allowlist: frozenset[str],
) -> list[Type1DuplicateGroup]:
    """Group records by type-1 (exact) hash; return real duplicate clusters.

    Boilerplate records never enter a bucket, so two unrelated ``__repr__``
    one-liners never form a group no matter how many files repeat them. A
    bucket otherwise qualifies exactly as ``find_duplicate_groups`` does:
    >1 member, largest member at least ``min_lines`` lines, hash not
    allow-listed. Groups are returned largest-span first.
    """
    buckets: dict[str, list[FunctionRecord]] = defaultdict(list)
    for record in records:
        if record.is_boilerplate:
            continue
        buckets[record.type1_hash].append(record)

    groups = [
        Type1DuplicateGroup(
            type1_hash=hash_,
            clone_type=TYPE1_LABEL,
            similarity=1.0,
            n_lines=max(member.n_lines for member in members),
            members=tuple(sorted(members, key=lambda member: (member.path, member.line))),
        )
        for hash_, members in buckets.items()
        if len(members) > 1
        and hash_ not in allowlist
        and max(member.n_lines for member in members) >= min_lines
    ]
    return sorted(groups, key=lambda group: (-group.n_lines, group.type1_hash))


def format_type1_report(groups: list[Type1DuplicateGroup]) -> str:
    """Render type-1 duplicate groups as a human-readable report string."""
    if not groups:
        return "check-duplicates: no type-1 duplicate functions found."

    total = sum(len(group.members) for group in groups)
    header = (
        f"check-duplicates: {len(groups)} type-1 duplicate group(s), "
        f"{total} function(s) involved.\n"
    )
    blocks = [
        "\n".join(
            [
                f"  group {group.type1_hash[:12]} [{group.clone_type}, "
                f"similarity {group.similarity:.2f}] "
                f"({len(group.members)} copies, ~{group.n_lines} lines each):",
                *[f"    {member.path}:{member.line}  {member.name}" for member in group.members],
                f"    allowlist with: {group.type1_hash}",
            ]
        )
        for group in groups
    ]
    return header + "\n\n".join(blocks) + "\n"
