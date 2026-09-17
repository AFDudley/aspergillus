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

Approach (type-2 clone normalization, two granularities):

1. Parse each file with LibCST (``extract_function_records``).
2. For every ``FunctionDef`` (including methods and nested functions),
   normalize the node: every VARIABLE-position identifier (``Name``) collapses
   to a single placeholder, while literal VALUES, called-function names,
   attribute names, keyword-argument names, and ``True``/``False``/``None``
   are kept EXACT. Functions that differ only by variable naming hash the
   same; functions that differ in what they call or the literals they emit do
   NOT. Detection is deterministic and threshold-free, and deliberately
   conservative -- it errs toward missing a clone over flagging two genuinely
   different functions (an earlier version collapsed every literal to a marker
   too, which made distinct string renderers hash identically).
3. Whole-body matching (``find_duplicate_groups``): hash the rendered
   normalized node; group records by hash across ALL files. This catches a
   clone only when the ENTIRE normalized body matches — a renamed copy of
   one whole function.
4. Fragment matching (``find_fragment_duplicates``): also render each body
   statement individually and slide a window of normalized statements
   across each function, hashing each window. This catches a copied
   statement spine (e.g. an identical inner closure plus an identical call)
   embedded inside two otherwise differently-shaped functions — the case
   whole-body hashing cannot see by construction, because the surrounding
   code makes the whole-body hashes differ. Pebble: asp-d88.2.
5. ``find_all_duplicate_groups`` combines both, each pair carrying a
   clone-type label and a similarity score. Boilerplate bodies (trivial
   dunders, one-line getters, pass-only bodies) are excluded from both, even
   when they match verbatim — they are scaffolding, not duplication.

A separate, stricter category is detected the same way: type-1 (exact)
clones per the Roy & Cordy (2007) clone taxonomy. Two function bodies are
a type-1 clone when they are identical once only comments and whitespace
are stripped — no identifier renaming, no literal normalization
(``find_type1_duplicate_groups``). Each function's exact-clone signature
is the sha256 of ``ast.dump`` of its body: the standard ``ast`` module
already discards comments and layout while preserving identifier names
and literal values exactly, which is precisely the type-1 equivalence.
The same boilerplate exclusion applies. Pebble: asp-d88.1.

All functions in this module are pure: they take source strings / records
and return records / groups / formatted text. Filesystem reads, argument
parsing and stdout writes live in ``__main__.py`` (the imperative shell).
"""

from __future__ import annotations

import ast
import hashlib
import textwrap
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

# Type-2 normalization renames every VARIABLE-position identifier to this single
# placeholder, but keeps every DISTINGUISHING token exact: literal values,
# called-function names, attribute names, keyword-argument names, and the
# True/False/None keywords. Abstracting those (an earlier version collapsed all
# literals to a "_STR" marker) made genuinely different functions -- e.g. two
# string renderers emitting different text -- hash identically, a false
# positive. Detection is deterministic and parameter-free (no similarity
# thresholds); it errs toward MISSING a clone that differs only in literal
# values over ever flagging two different functions.
_NAME_PLACEHOLDER = "_ID"

# Clone-type labels a reported DuplicateGroup / Type1DuplicateGroup carries.
# The type-2 pair are exact after identifier/literal normalization — they
# differ only in whether the match spans a whole function body or a
# statement fragment within one. Type-1 is exact once only comments and
# whitespace are stripped — no normalization beyond that.
CLONE_TYPE_WHOLE = "type-2-whole"
CLONE_TYPE_FRAGMENT = "type-2-fragment"
TYPE1_LABEL = "type-1"

# Separator joined between per-statement normalized texts before hashing a
# window. Chosen to never appear in rendered Python source.
_FRAGMENT_SEPARATOR = "\x00"


@dataclass(frozen=True)
class NormalizedStatement:
    """One body statement of a function, rendered under type-2 normalization.

    ``text`` is the statement's own rendered code (nested blocks render as
    part of their parent statement's text, so a compound statement like an
    ``if`` or ``for`` is one entry). ``start_line``/``end_line`` come from the
    UNNORMALIZED source and are used only to size a matched window in lines.
    """

    text: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class FunctionRecord:
    """One function/method, with its type-1 and type-2 clone signatures.

    ``normalized_hash`` is equal for two functions that are identical up to
    identifier renaming and literal values; ``n_lines`` is the CODE-line span —
    the function span minus a leading docstring — used for the ``min_lines``
    size floor, so prose never inflates a clone's measured size. ``statements``
    is the same body, minus a leading docstring, as individually normalized
    statements — the unit fragment matching slides its window over.
    ``type1_hash`` is equal only for functions identical once comments and
    whitespace are stripped (the Roy & Cordy (2007) type-1/exact clone
    signature). ``is_boilerplate`` marks trivial scaffolding (pass-only
    bodies, one-line getters, dunder methods with a single-statement body)
    that must never be reported as a duplicate even when it matches verbatim.
    """

    path: str
    name: str
    line: int
    n_lines: int
    normalized_hash: str
    type1_hash: str
    is_boilerplate: bool
    statements: tuple[NormalizedStatement, ...]


@dataclass(frozen=True)
class DuplicateGroup:
    """A cluster of functions sharing a type-2 clone, whole-body or fragment.

    ``similarity`` is the fraction of the largest member's statements the
    match covers: 1.0 for a whole-body match, less than 1.0 for a fragment
    embedded in a larger, differently-shaped function.
    """

    normalized_hash: str
    n_lines: int
    members: tuple[FunctionRecord, ...]
    clone_type: str
    similarity: float


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
    """Type-2 normalization by renaming VARIABLE-position identifiers only.

    Every ``Name`` used as a variable/parameter/object collapses to a single
    placeholder, so two functions that differ only by variable naming
    normalize identically. Kept EXACT (never abstracted): literal values,
    called-function names (``foo(...)``), attribute names (``x.attr``),
    keyword-argument names (``f(key=...)``), and the ``True``/``False``/
    ``None`` keywords -- these are the tokens that distinguish genuinely
    different functions, and abstracting them is what collapsed distinct
    string renderers to one hash. A single placeholder (rather than
    per-function consistent numbering) keeps a copied statement spine
    position-independent, so fragment matching still works. Deterministic and
    threshold-free; conservative by construction.
    """

    def __init__(self) -> None:
        super().__init__()
        #: ``id()`` of every ``Name`` node kept exact (callee/attr/kwarg names).
        self._protected: set[int] = set()

    def visit_Attribute(self, node: cst.Attribute) -> bool:
        # The attribute NAME (``.attr``) is API surface, kept exact; only the
        # base object (``.value``) is a variable to rename.
        self._protected.add(id(node.attr))
        return True

    def visit_Call(self, node: cst.Call) -> bool:
        # A bare callee (``foo(...)``) names an API, kept exact.
        if isinstance(node.func, cst.Name):
            self._protected.add(id(node.func))
        return True

    def visit_Arg(self, node: cst.Arg) -> bool:
        # A keyword-argument name (``f(key=...)``) is API surface, kept exact.
        if node.keyword is not None:
            self._protected.add(id(node.keyword))
        return True

    def visit_MatchSingleton(self, node: cst.MatchSingleton) -> bool:
        # ``case True`` / ``case False`` / ``case None`` must keep distinct,
        # exact values; skip so leave_Name never renames them.
        return False

    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name) -> cst.Name:
        if id(original_node) in self._protected or original_node.value in ("True", "False", "None"):
            return updated_node
        return updated_node.with_changes(value=_NAME_PLACEHOLDER)


def _is_docstring(statement: cst.BaseStatement) -> bool:
    """Whether ``statement`` is a lone string expression — a docstring."""
    if not isinstance(statement, cst.SimpleStatementLine) or len(statement.body) != 1:
        return False
    expr = statement.body[0]
    return isinstance(expr, cst.Expr) and isinstance(
        expr.value, cst.SimpleString | cst.ConcatenatedString
    )


def _is_pass_only(statement: cst.BaseStatement) -> bool:
    """Whether ``statement`` is a bare ``pass``."""
    return isinstance(statement, cst.SimpleStatementLine) and any(
        isinstance(small, cst.Pass) for small in statement.body
    )


def _is_simple_getter(statement: cst.BaseStatement) -> bool:
    """Whether ``statement`` is a single ``return <name-or-attribute>``."""
    if not isinstance(statement, cst.SimpleStatementLine) or len(statement.body) != 1:
        return False
    small = statement.body[0]
    if not isinstance(small, cst.Return) or small.value is None:
        return False
    return isinstance(small.value, cst.Name | cst.Attribute)


def _is_dunder(name: str) -> bool:
    """Whether ``name`` is a dunder method name (``__init__``, ``__eq__``, ...)."""
    return name.startswith("__") and name.endswith("__") and len(name) > 4


def _is_boilerplate(node: cst.FunctionDef, code_statements: Sequence[cst.BaseStatement]) -> bool:
    """Whether ``node`` is trivial scaffolding, never worth flagging as a clone.

    Boilerplate is a single-statement CODE body (docstring already excluded)
    that is a bare ``pass``, a one-line getter (``return`` of a name or
    attribute), or any dunder method — these compare identical after type-2
    normalization BY CONSTRUCTION (``pass`` is always ``pass``, every
    name/attribute collapses to the same placeholder), so without this
    exclusion any two unrelated trivial methods would falsely report as
    a clone. The same criteria also exclude a function from type-1 (exact)
    reports, where two unrelated ``def __repr__(self): return ...``
    definitions are not the copy-pasted duplication the detector exists
    to catch.
    """
    if len(code_statements) != 1:
        return False
    (statement,) = code_statements
    return _is_pass_only(statement) or _is_simple_getter(statement) or _is_dunder(node.name.value)


class _FunctionCollector(cst.CSTVisitor):
    """Collect every ``FunctionDef`` with its span and its CODE body statements.

    The span, and the collected statements, exclude a leading docstring: two
    distinct functions that differ only in their docstring and share a
    one-line body are not real code duplication, so their prose must not
    push them over the ``min_lines`` floor or seed a spurious fragment match.
    """

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self) -> None:
        self.functions: list[
            tuple[cst.FunctionDef, int, int, tuple[tuple[cst.BaseStatement, int, int], ...]]
        ] = []

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        pos = self.get_metadata(PositionProvider, node)
        span = pos.end.line - pos.start.line + 1
        code_statements = self._code_statements(node)
        docstring_lines = self._docstring_lines(node)
        self.functions.append((node, pos.start.line, span - docstring_lines, code_statements))

    def _code_statements(
        self, node: cst.FunctionDef
    ) -> tuple[tuple[cst.BaseStatement, int, int], ...]:
        block = node.body
        if not isinstance(block, cst.IndentedBlock) or not block.body:
            return ()
        statements = block.body
        if _is_docstring(statements[0]):
            statements = statements[1:]
        result = []
        for statement in statements:
            pos = self.get_metadata(PositionProvider, statement)
            result.append((statement, pos.start.line, pos.end.line))
        return tuple(result)

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
    """Render ``func`` under type-2 normalization and return its sha256 hex.

    A leading docstring is stripped before hashing: it is prose, not code, so
    two otherwise-identical functions with different docstrings are still the
    same type-2 clone. (Literals are kept verbatim now, so leaving the
    docstring in would wrongly split the hash.)
    """
    normalized = func.visit(_Normalizer())
    # _Normalizer only rewrites leaf values; it never removes the root node,
    # so visiting a FunctionDef always yields a FunctionDef. Narrow for mypy.
    assert isinstance(normalized, cst.FunctionDef)
    body = normalized.body
    if isinstance(body, cst.IndentedBlock) and len(body.body) > 1 and _is_docstring(body.body[0]):
        normalized = normalized.with_changes(body=body.with_changes(body=body.body[1:]))
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


def _normalize_statements(
    module: cst.Module,
    func: cst.FunctionDef,
    code_statements: tuple[tuple[cst.BaseStatement, int, int], ...],
) -> tuple[NormalizedStatement, ...]:
    """Render each of ``func``'s CODE body statements under type-2 normalization.

    ``code_statements`` pairs each body statement (docstring already
    excluded) with its (start_line, end_line) span from the UNNORMALIZED
    tree. ``_Normalizer`` only rewrites leaf values, so it never adds, drops,
    or reorders statements — the same index lines up in both trees, offset by
    however many leading statements (0 or 1: the docstring) were dropped.
    """
    if not code_statements:
        return ()
    normalized = func.visit(_Normalizer())
    assert isinstance(normalized, cst.FunctionDef)
    assert isinstance(normalized.body, cst.IndentedBlock)
    normalized_statements = normalized.body.body
    offset = len(normalized_statements) - len(code_statements)
    assert offset in (0, 1)
    return tuple(
        NormalizedStatement(
            text=module.code_for_node(normalized_statements[offset + i]),
            start_line=start,
            end_line=end,
        )
        for i, (_, start, end) in enumerate(code_statements)
    )


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
            is_boilerplate=_is_boilerplate(node, [s for s, _, _ in code_statements]),
            statements=_normalize_statements(module, node, code_statements),
        )
        for node, start, code_lines, code_statements in collector.functions
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
    """Group records by whole-body hash; return buckets that are real clusters.

    A bucket qualifies when it has >1 non-boilerplate member, its largest
    member spans at least ``min_lines`` lines, and its hash is not in
    ``allowlist``. Groups are returned largest-span first (most significant
    duplication on top).
    """
    buckets: dict[str, list[FunctionRecord]] = defaultdict(list)
    for record in records:
        if record.is_boilerplate:
            continue
        buckets[record.normalized_hash].append(record)

    groups = [
        DuplicateGroup(
            normalized_hash=hash_,
            n_lines=max(member.n_lines for member in members),
            members=tuple(sorted(members, key=lambda member: (member.path, member.line))),
            clone_type=CLONE_TYPE_WHOLE,
            similarity=1.0,
        )
        for hash_, members in buckets.items()
        if len(members) > 1
        and hash_ not in allowlist
        and max(member.n_lines for member in members) >= min_lines
    ]
    return sorted(groups, key=lambda group: (-group.n_lines, group.normalized_hash))


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


def _fragment_hash(statements: Sequence[NormalizedStatement]) -> str:
    """Sha256 hex of a window of normalized statements, joined unambiguously."""
    joined = _FRAGMENT_SEPARATOR.join(statement.text for statement in statements)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _window_n_lines(statements: Sequence[NormalizedStatement]) -> int:
    """Line span, in the UNNORMALIZED source, covered by a statement window."""
    return statements[-1].end_line - statements[0].start_line + 1


def _is_window_covered(covered: list[tuple[int, int]], start: int, end: int) -> bool:
    """Whether ``[start, end)`` sits entirely inside an already-found window."""
    return any(lo <= start and end <= hi for lo, hi in covered)


def _bucket_windows_at_length(
    candidates: list[FunctionRecord],
    length: int,
    covered: dict[tuple[str, str, int], list[tuple[int, int]]],
) -> dict[str, list[tuple[FunctionRecord, int]]]:
    """Group every not-yet-``covered`` window of ``length`` statements by hash."""
    buckets: dict[str, list[tuple[FunctionRecord, int]]] = defaultdict(list)
    for record in candidates:
        n_statements = len(record.statements)
        if n_statements < length:
            continue
        key = (record.path, record.name, record.line)
        for start in range(0, n_statements - length + 1):
            if _is_window_covered(covered[key], start, start + length):
                continue
            window = record.statements[start : start + length]
            buckets[_fragment_hash(window)].append((record, start))
    return buckets


def _groups_from_bucket(
    hash_: str,
    occurrences: list[tuple[FunctionRecord, int]],
    length: int,
    min_lines: int,
) -> list[tuple[DuplicateGroup, list[tuple[FunctionRecord, int]]]]:
    """The fragment match from a hash bucket, as a zero-or-one-element list.

    Empty when it doesn't qualify — no Optional-as-sentinel (ASP302): a list
    already expresses "found" (one element) or "not found" (none) without a
    separate null case. One occurrence per function: a function matching
    itself twice (a genuinely repeated internal block) is a different
    defect, out of scope here.
    """
    by_function = {
        (record.path, record.name, record.line): (record, start) for record, start in occurrences
    }
    if len(by_function) < 2:
        return []
    members_and_starts = list(by_function.values())
    n_lines = max(
        _window_n_lines(record.statements[start : start + length])
        for record, start in members_and_starts
    )
    if n_lines < min_lines:
        return []
    members = tuple(
        sorted(
            (record for record, _ in members_and_starts),
            key=lambda member: (member.path, member.line),
        )
    )
    similarity = length / max(len(member.statements) for member in members)
    group = DuplicateGroup(
        normalized_hash=hash_,
        n_lines=n_lines,
        members=members,
        clone_type=CLONE_TYPE_FRAGMENT,
        similarity=similarity,
    )
    return [(group, members_and_starts)]


def find_fragment_duplicates(
    records: list[FunctionRecord],
    min_lines: int,
    min_statements: int,
    allowlist: frozenset[str],
) -> list[DuplicateGroup]:
    """Find a duplicated statement SPINE embedded inside differently-shaped
    functions, via sliding windows of normalized statement sequences.

    Unlike ``find_duplicate_groups`` (which requires an ENTIRE normalized
    body to match), this catches a copied run of statements that sits inside
    a larger function alongside unrelated surrounding code — the case a
    whole-body hash cannot see by construction, since the surrounding code
    makes the whole-body hashes differ. Matches stay exact (type-2: identifier
    renaming and literal values only), just at fragment instead of whole-body
    granularity.

    Windows are scanned longest-first per length so a maximal spine is
    reported once: any shorter window fully inside an already-reported spine,
    for the SAME function, is skipped — it is a piece of a clone already
    found, not a separate one.
    """
    candidates = [
        record
        for record in records
        if not record.is_boilerplate and len(record.statements) >= min_statements
    ]
    if not candidates:
        return []

    covered: dict[tuple[str, str, int], list[tuple[int, int]]] = defaultdict(list)
    groups: list[DuplicateGroup] = []
    max_len = max(len(record.statements) for record in candidates)

    for length in range(max_len, min_statements - 1, -1):
        buckets = _bucket_windows_at_length(candidates, length, covered)
        for hash_, occurrences in buckets.items():
            if hash_ in allowlist:
                continue
            for group, members_and_starts in _groups_from_bucket(
                hash_, occurrences, length, min_lines
            ):
                groups.append(group)
                for record, start in members_and_starts:
                    key = (record.path, record.name, record.line)
                    covered[key].append((start, start + length))

    return sorted(groups, key=lambda group: (-group.n_lines, group.normalized_hash))


def find_all_duplicate_groups(
    records: list[FunctionRecord],
    min_lines: int,
    allowlist: frozenset[str],
    min_fragment_statements: int = 2,
) -> list[DuplicateGroup]:
    """Whole-body clones plus fragment-embedded clones, combined and sorted.

    A pair already reported as a whole-body match is not repeated as a
    fragment match covering that same pair in full — fragment detection
    widens the whole-body hash's blind spot, it does not restate its findings.
    """
    whole = find_duplicate_groups(records, min_lines, allowlist)
    whole_pairs = {
        frozenset((member.path, member.name, member.line) for member in group.members)
        for group in whole
    }

    fragments = [
        group
        for group in find_fragment_duplicates(
            records, min_lines, min_fragment_statements, allowlist
        )
        if group.similarity < 1.0
        or frozenset((member.path, member.name, member.line) for member in group.members)
        not in whole_pairs
    ]

    combined = whole + fragments
    return sorted(combined, key=lambda group: (-group.n_lines, group.normalized_hash))


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
                f"({len(group.members)} copies, ~{group.n_lines} lines each, "
                f"{group.clone_type}, similarity {group.similarity:.2f}):",
                *[f"    {member.path}:{member.line}  {member.name}" for member in group.members],
                f"    allowlist with: {group.normalized_hash}",
            ]
        )
        for group in groups
    ]
    return header + "\n\n".join(blocks) + "\n"


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
