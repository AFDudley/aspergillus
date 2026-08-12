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
   placeholder and every literal VALUE collapses to a type-only marker, so
   functions that differ ONLY by naming / literal values hash the same. The
   literal's KIND and its internal structure survive: an f-string keeps its
   interpolations and a concatenation keeps its parts, because those are
   code, not values.
3. Hash the normalized node's STRUCTURE — node kinds and their surviving
   token values, with whitespace, layout and comments dropped, which is
   exactly what the standard type-2 definition ignores. Group records by
   hash across ALL files (``find_duplicate_groups``).
4. Report every member of a hash bucket that spans at least ``min_lines``
   lines, when two or more such members remain and the hash is not
   allow-listed.

All functions in this module are pure: they take source strings / records
and return records / groups / formatted text. Filesystem reads, argument
parsing and stdout writes live in ``__main__.py`` (the imperative shell).
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections import defaultdict
from collections.abc import Iterator
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
# An f-string's literal TEXT is a value and collapses; its interpolated
# expressions are code and are normalized in place, so arity and shape
# survive. The quote style is canonicalized so `f"x"` and `f'''x'''` agree.
_FSTRING_TEXT_MARKER = "_STR"
_FSTRING_START = 'f"'
_FSTRING_END = '"'

#: CST node kinds that carry only layout. A type-2 clone signature ignores
#: whitespace, line breaks and comments, so the structural walk skips these
#: subtrees whole — this is what makes the hash survive a reformat (exo-ed84).
#:
#: The punctuation entries are here because a formatter owns them: ruff adds a
#: magic trailing comma when it wraps an argument list, and grouping parens
#: when it wraps an expression. Neither changes arity or shape, both of which
#: the surrounding node's own children already record.
_LAYOUT_NODES = (
    cst.BaseParenthesizableWhitespace,
    cst.EmptyLine,
    cst.Comment,
    cst.Newline,
    cst.TrailingWhitespace,
    cst.Comma,
    cst.Semicolon,
    cst.LeftParen,
    cst.RightParen,
)

#: String-valued dataclass fields that hold layout rather than syntax.
_LAYOUT_FIELDS = frozenset({"indent", "default_indent", "default_newline", "encoding"})


@dataclass(frozen=True)
class FunctionRecord:
    """One function/method, with its type-2-normalized structural hash.

    ``normalized_hash`` is equal for two functions that are identical up to
    identifier renaming and literal values. ``n_lines`` is the physical source
    span, which is what a reader uses to find the function. ``n_code_lines``
    is that span minus the function's own docstring, and it is what the
    ``min_lines`` floor is applied to.

    The two are separate because the floor asks how much CODE is at stake, and
    a span answers a different question. Counting prose let a three-line body
    under twelve lines of documentation clear a five-line floor, and made the
    verdict move in BOTH directions on edits that changed no behaviour:
    relocating a docstring hid a group, writing one manufactured a group
    (exo-4be).
    """

    path: str
    name: str
    line: int
    n_lines: int
    n_code_lines: int
    normalized_hash: str


@dataclass(frozen=True)
class DuplicateGroup:
    """A hash bucket with more than one member — a duplicate cluster."""

    normalized_hash: str
    n_lines: int
    members: tuple[FunctionRecord, ...]


class _Normalizer(cst.CSTTransformer):
    """Collapse identifiers to a placeholder and literal VALUES to type markers.

    This is what makes the hash a *type-2* clone signature: two functions
    that differ only in the names of their locals/args/attributes or in the
    concrete values of their literals normalize to the same tree. Operators,
    call/attribute/statement STRUCTURE and control flow are all preserved, so
    genuinely different logic keeps a different hash.

    A string's KIND is part of that structure, not part of its value. A
    docstring, an interpolated f-string and a multi-part concatenation are
    three different constructs, so they normalize to three different trees
    (exo-314.2). Only the literal TEXT inside them collapses.
    """

    def visit_MatchSingleton(self, node: cst.MatchSingleton) -> bool:
        """Do not descend into ``case None:`` / ``case True:`` / ``case False:``.

        The singleton's child is a ``Name``, but it is the literal itself, not
        an identifier: ``MatchSingleton`` validates that the name is exactly
        ``True``, ``False`` or ``None`` and rejects the ``_ID`` placeholder,
        which crashed the whole scan on one valid file (exo-eec). It carries
        no identifier to normalize, so skipping the subtree loses nothing and
        keeps the three singletons distinct from each other.
        """
        return False

    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name) -> cst.Name:
        return updated_node.with_changes(value=_NAME_PLACEHOLDER)

    def leave_SimpleString(
        self, original_node: cst.SimpleString, updated_node: cst.SimpleString
    ) -> cst.SimpleString:
        return updated_node.with_changes(value=_STR_MARKER)

    def leave_FormattedStringText(
        self, original_node: cst.FormattedStringText, updated_node: cst.FormattedStringText
    ) -> cst.FormattedStringText:
        """The literal run between interpolations is a value; it collapses."""
        return updated_node.with_changes(value=_FSTRING_TEXT_MARKER)

    def leave_FormattedString(
        self, original_node: cst.FormattedString, updated_node: cst.FormattedString
    ) -> cst.BaseString:
        """Keep the f-string and its interpolations; canonicalize the quoting.

        The interpolated expressions are CODE — already normalized by this
        same transformer — so ``f"worker/{id}"`` keeps one interpolation and a
        six-part prompt template keeps six. Collapsing the whole node to one
        token is what put 17 unrelated functions in one group (exo-314.2).
        """
        return updated_node.with_changes(start=_FSTRING_START, end=_FSTRING_END)

    def leave_Integer(self, original_node: cst.Integer, updated_node: cst.Integer) -> cst.Integer:
        return updated_node.with_changes(value=_INT_MARKER)

    def leave_Float(self, original_node: cst.Float, updated_node: cst.Float) -> cst.Float:
        return updated_node.with_changes(value=_FLOAT_MARKER)

    def leave_Imaginary(
        self, original_node: cst.Imaginary, updated_node: cst.Imaginary
    ) -> cst.Imaginary:
        return updated_node.with_changes(value=_IMAGINARY_MARKER)


class _FunctionCollector(cst.CSTVisitor):
    """Collect every ``FunctionDef`` with its span and its docstring's span."""

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self) -> None:
        self.functions: list[tuple[cst.FunctionDef, int, int, int]] = []

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        pos = self.get_metadata(PositionProvider, node)
        self.functions.append((node, pos.start.line, pos.end.line, self._docstring_lines(node)))

    def _docstring_lines(self, node: cst.FunctionDef) -> int:
        """How many physical lines this function's own docstring occupies."""
        docstring = _leading_docstring(node)
        if docstring is None:
            return 0
        pos = self.get_metadata(PositionProvider, docstring)
        return pos.end.line - pos.start.line + 1


def _structural_tokens(node: cst.CSTNode) -> Iterator[str]:
    """Yield the layout-free token stream of ``node``: kinds and syntax values.

    Whitespace, line breaks and comments are skipped whole. The standard
    type-2 definition ignores them, and hashing the RENDERED source instead
    made a duplicate verdict turn on how ruff happened to wrap a signature
    (exo-ed84).
    """
    if isinstance(node, _LAYOUT_NODES):
        return
    yield type(node).__name__
    for field in dataclasses.fields(node):
        if field.name in _LAYOUT_FIELDS:
            continue
        value = getattr(node, field.name)
        if isinstance(value, str):
            yield f"{field.name}={value}"
    yield "("
    for child in node.children:
        yield from _structural_tokens(child)
    yield ")"


def _leading_docstring(func: cst.FunctionDef) -> cst.BaseString | None:
    """The function's own docstring node, or ``None`` when it has none."""
    body = func.body
    if not isinstance(body, cst.IndentedBlock) or not body.body:
        return None
    first = body.body[0]
    if not isinstance(first, cst.SimpleStatementLine) or not first.body:
        return None
    statement = first.body[0]
    if isinstance(statement, cst.Expr) and isinstance(statement.value, cst.BaseString):
        return statement.value
    return None


def _calls_assert_never(node: cst.CSTNode) -> bool:
    """Whether ``assert_never`` is called anywhere inside ``node``."""

    class _Finder(cst.CSTVisitor):
        found = False

        def visit_Call(self, call: cst.Call) -> None:
            callee = call.func
            named = isinstance(callee, cst.Name) and callee.value == "assert_never"
            attribute = isinstance(callee, cst.Attribute) and callee.attr.value == "assert_never"
            if named or attribute:
                self.found = True

    finder = _Finder()
    node.visit(finder)
    return finder.found


def _exhaustive_dispatch(func: cst.FunctionDef) -> cst.Match | None:
    """The ``match`` of a TOTAL dispatcher, or ``None`` when ``func`` is not one.

    A total dispatcher's whole body, after an optional docstring, is one
    ``match`` whose wildcard arm calls ``assert_never``. That shape is what
    makes mypy --strict reject a newly added variant, which is why folding two
    of them behind a generic helper is not available: the helper leaves mypy
    silent and lets an unknown value fall through instead of raising.
    """
    body = func.body
    if not isinstance(body, cst.IndentedBlock):
        return None
    statements = list(body.body)
    if statements and _leading_docstring(func) is not None:
        statements = statements[1:]
    if len(statements) != 1 or not isinstance(statements[0], cst.Match):
        return None
    match_node = statements[0]
    return match_node if _calls_assert_never(match_node) else None


def _dispatch_discriminants(module: cst.Module, func: cst.FunctionDef) -> list[str]:
    """A total dispatcher's identity: its subject, patterns and returned values.

    Type-2 normalization erases identifiers and literal values, which for a
    total dispatcher erases everything the function says. Nine band checks in
    exophial read nine different aspects against nine different flagged values
    and return members of three different enums; normalized to one token they
    became one duplicate group that must never be folded (exo-314).

    This is NOT an exemption — nothing is suppressed. For this shape, and only
    this shape, the subject, the case patterns and each arm's returned
    expression are carried VERBATIM into the hash, so the hash stops discarding
    the part that differs. Two dispatchers that discriminate differently then
    hash differently, and a genuine copy-paste of one still hashes the same as
    its original. It is the same argument as an f-string's interpolations being
    code rather than value: in a total dispatcher, what it matches on IS the
    function.

    All THREE parts are needed. ``situation._check_main_checkout`` and
    ``integrate_lane_situation._check_main_checkout`` read the same attribute
    against the same flagged value and differ only in the member they return,
    declared in different contracts and consumed by disjoint machinery.

    Only the RETURNED expression of each arm is taken, never the whole arm; an
    arm that does anything else contributes nothing here and is still covered
    by the structural token stream.
    """
    match_node = _exhaustive_dispatch(func)
    if match_node is None:
        return []
    parts = [module.code_for_node(match_node.subject).strip()]
    for case in match_node.cases:
        parts.append(module.code_for_node(case.pattern).strip())
        body = case.body
        statements = body.body if isinstance(body, cst.IndentedBlock) else ()
        for statement in statements:
            if not isinstance(statement, cst.SimpleStatementLine):
                continue
            for small in statement.body:
                if isinstance(small, cst.Return) and small.value is not None:
                    parts.append(module.code_for_node(small.value).strip())
    return parts


def _hash_function(module: cst.Module, func: cst.FunctionDef) -> str:
    """Normalize ``func`` under type-2 rules and return its structural sha256."""
    normalized = func.visit(_Normalizer())
    # _Normalizer only rewrites leaf values; it never removes the root node,
    # so visiting a FunctionDef always yields a FunctionDef. Narrow for mypy.
    assert isinstance(normalized, cst.FunctionDef)
    parts = list(_structural_tokens(normalized))
    discriminants = _dispatch_discriminants(module, func)
    if discriminants:
        parts += ["#total-dispatch", *discriminants]
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


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
            n_code_lines=end - start + 1 - docstring_lines,
            normalized_hash=_hash_function(module, node),
        )
        for node, start, end, docstring_lines in collector.functions
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

    ``min_lines`` is a floor on EVERY reported member, not on the bucket: a
    member below the floor is dropped before the bucket is judged, and what is
    left is a group only if two or more members survive. Judging the bucket on
    its LARGEST member reported 19 functions of 3 and 4 lines under a
    documented floor of 5 (exo-314.1).

    The floor is applied to ``n_code_lines``, never to the physical span. A
    span counts the docstring, which made the verdict depend on how a function
    is documented rather than on what it does: over one 6632-function corpus,
    632 functions cleared a 5-line floor on prose alone, and 29 groups covering
    73 members were reported with no member above the floor by code (exo-4be).

    A group's ``n_lines`` is the SMALLEST code size it reports — the honest
    "every copy is at least this big" figure. Groups are returned largest
    first (most significant duplication on top).
    """
    buckets: dict[str, list[FunctionRecord]] = defaultdict(list)
    for record in records:
        if record.n_code_lines >= min_lines:
            buckets[record.normalized_hash].append(record)

    groups = [
        DuplicateGroup(
            normalized_hash=hash_,
            n_lines=min(member.n_code_lines for member in members),
            members=tuple(sorted(members, key=lambda member: (member.path, member.line))),
        )
        for hash_, members in buckets.items()
        if len(members) > 1 and hash_ not in allowlist
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
                f"({len(group.members)} copies, {group.n_lines}+ code lines each):",
                *[
                    f"    {member.path}:{member.line}  {member.name} "
                    f"({member.n_code_lines} code lines of {member.n_lines})"
                    for member in group.members
                ],
                f"    allowlist with: {group.normalized_hash}",
            ]
        )
        for group in groups
    ]
    return header + "\n\n".join(blocks) + "\n"
