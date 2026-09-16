"""CLI entry point.

Two invocations:

  python -m aspergillus <filepath>
      Runs all aspergillus Fixit rules against ONE file and outputs
      structured JSON to stdout. Exit 0 = clean, 1 = violations, 2 = input
      error (missing file, bad args). Output is a JSON array of
      {"file", "line", "rule", "message", "severity"} objects; severity maps
      Level 2 (ASP2xx) -> "high", Level 3 (ASP3xx) -> "medium".

  python -m aspergillus check-duplicates <path>... [--min-lines N]
                                                    [--allowlist FILE] [--json]
      Whole-project type-1/type-2 duplicate-function detector (cross-file —
      the thing a single-file fixit LintRule structurally cannot do). Reports
      whole-body clones AND a copied statement spine embedded inside a
      differently-shaped function; each reported pair carries a clone-type
      label and a similarity score. Exit 0 = clean, 1 = duplicates found,
      2 = input error. Pure logic lives in ``duplicates.py``; this module is
      the imperative shell (argument parsing, filesystem reads, stdout).
      Pebble: asp-21d, asp-d88.1, asp-d88.2.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from fixit.api import fixit_bytes
from fixit.ftypes import Config, QualifiedRule
from libcst import ParserSyntaxError

from aspergillus.duplicates import (
    FunctionRecord,
    SemanticRecord,
    extract_function_records,
    extract_semantic_records,
    find_all_duplicate_groups,
    find_type1_duplicate_groups,
    find_type3_duplicate_groups,
    find_type4_candidates,
    format_report,
    format_type1_report,
    format_type3_report,
    format_type4_report,
    parse_allowlist,
)

# Matches "ASP201", "ASP302", etc. at the start of a message.
_RULE_CODE_RE = re.compile(r"^(ASP\d{3})")

# Explicit config so rules are found regardless of where the linted file lives.
_CONFIG = Config(enable=[QualifiedRule("aspergillus.rules")])


def _severity_for_code(code: str) -> str:
    """Map rule code to severity: ASP2xx -> high, ASP3xx -> medium."""
    if code.startswith("ASP2"):
        return "high"
    if code.startswith("ASP3"):
        return "medium"
    return "medium"


def _iter_python_files(paths: list[str]) -> list[Path]:
    """Expand path args into a sorted, de-duplicated list of .py files (IO)."""
    found: set[Path] = set()
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            found.update(p.rglob("*.py"))
        elif p.suffix == ".py":
            found.add(p)
    return sorted(found)


def _gather_records(files: list[Path]) -> tuple[list[FunctionRecord], list[str]]:
    """Read + parse each file into function records (IO shell around the core).

    Returns (records, parse_errors). A file that will not parse is reported
    in parse_errors (surfaced loudly to stderr by the caller) and skipped —
    a whole-tree scanner legitimately meets deliberately-broken fixtures; the
    error is never swallowed, but one bad file does not abort the scan.
    """
    records: list[FunctionRecord] = []
    parse_errors: list[str] = []
    for f in files:
        try:
            records.extend(extract_function_records(f.read_text(encoding="utf-8"), str(f)))
        except ParserSyntaxError as exc:
            parse_errors.append(f"{f}: {exc}")
    return records, parse_errors


def _gather_semantic(files: list[Path]) -> tuple[list[SemanticRecord], list[str]]:
    """Read + parse each file into semantic records for type-4 detection (IO).

    Returns (records, parse_errors), mirroring ``_gather_records``: a file that
    will not parse is reported and skipped, never aborting the scan.
    """
    records: list[SemanticRecord] = []
    parse_errors: list[str] = []
    for f in files:
        try:
            records.extend(extract_semantic_records(f.read_text(encoding="utf-8"), str(f)))
        except SyntaxError as exc:
            parse_errors.append(f"{f}: {exc}")
    return records, parse_errors


def _load_allowlist(path: str | None) -> frozenset[str]:
    """Load the accepted-hash allowlist file, or an empty set if none (IO)."""
    if path is None:
        return frozenset()
    return parse_allowlist(Path(path).read_text(encoding="utf-8"))


def _reported_pairs(*group_lists: list[Any]) -> frozenset[frozenset[tuple[str, str, int]]]:
    """Every (path, name, line) member PAIR already reported by the given tiers.

    Fed to ``find_type4_candidates`` as its exclude set, so type-4 surfaces
    only semantic similarity that type-1/2/3 did not already catch.
    """
    pairs: set[frozenset[tuple[str, str, int]]] = set()
    for groups in group_lists:
        for group in groups:
            keys = [(m.path, m.name, m.line) for m in group.members]
            for i in range(len(keys)):
                for j in range(i + 1, len(keys)):
                    pairs.add(frozenset((keys[i], keys[j])))
    return frozenset(pairs)


def _group_json(group: Any, hash_: str) -> dict[str, Any]:
    """One clone group as a JSON-serializable dict (shared across all tiers)."""
    return {
        "normalized_hash": hash_,
        "clone_type": group.clone_type,
        "similarity": group.similarity,
        "n_lines": group.n_lines,
        "members": [{"path": m.path, "line": m.line, "name": m.name} for m in group.members],
    }


def _check_duplicates_main(argv: list[str]) -> int:
    """`check-duplicates` subcommand shell: parse args, scan, print, exit code."""
    parser = argparse.ArgumentParser(prog="aspergillus check-duplicates")
    parser.add_argument("paths", nargs="+", help="files or directories to scan")
    parser.add_argument(
        "--min-lines",
        type=int,
        default=5,
        help="minimum function span (lines) to report; default 5",
    )
    parser.add_argument(
        "--allowlist",
        default=None,
        help="file of accepted normalized-hashes (one per line, # comments)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    ns = parser.parse_args(argv)

    files = _iter_python_files(ns.paths)
    records, parse_errors = _gather_records(files)
    for err in parse_errors:
        print(f"check-duplicates: skipping unparseable file {err}", file=sys.stderr)

    allowlist = _load_allowlist(ns.allowlist)
    groups = find_all_duplicate_groups(records, ns.min_lines, allowlist)
    type1_groups = find_type1_duplicate_groups(records, ns.min_lines, allowlist)
    type3_groups = find_type3_duplicate_groups(records, ns.min_lines, min_statements=2)

    semantic_records, semantic_errors = _gather_semantic(files)
    for err in semantic_errors:
        print(f"check-duplicates: skipping unparseable file {err}", file=sys.stderr)
    # Type-4 is advisory: only surface semantically-similar pairs NOT already
    # reported by type-1/2/3, so exclude every pair those tiers found.
    exclude_pairs = _reported_pairs(groups, type1_groups, type3_groups)
    type4_candidates = find_type4_candidates(
        semantic_records, ns.min_lines, exclude_pairs=exclude_pairs
    )

    if ns.json:
        payload = (
            [_group_json(g, g.normalized_hash) for g in groups]
            + [_group_json(g, g.type1_hash) for g in type1_groups]
            + [_group_json(g, "") for g in type3_groups]
            + [_group_json(g, "") for g in type4_candidates]
        )
        json.dump(payload, sys.stdout)
        print(file=sys.stdout)
    else:
        print(format_report(groups), end="\n")
        print(format_type1_report(type1_groups), end="\n")
        print(format_type3_report(type3_groups), end="\n")
        print(format_type4_report(type4_candidates), end="")

    # Type-4 candidates are advisory and never on their own set a nonzero exit.
    return 1 if groups or type1_groups or type3_groups else 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch to a subcommand or run single-file lint (default)."""
    args = argv if argv is not None else sys.argv[1:]

    if args and args[0] == "check-duplicates":
        return _check_duplicates_main(args[1:])

    if len(args) != 1:
        print("Usage: python -m aspergillus <filepath>", file=sys.stderr)
        print(
            "       python -m aspergillus check-duplicates <path>... [--min-lines N]",
            file=sys.stderr,
        )
        return 2

    filepath = Path(args[0])
    if not filepath.is_file():
        print(f"Error: file not found: {filepath}", file=sys.stderr)
        return 2

    content = filepath.read_bytes()
    config = Config(path=filepath, enable=_CONFIG.enable)

    violations = []
    for result in fixit_bytes(filepath, content, config=config):
        if result.violation is None:
            continue
        v = result.violation
        message = v.message
        # Extract rule code from message (e.g., "ASP201: ...")
        match = _RULE_CODE_RE.match(message)
        code = match.group(1) if match else v.rule_name

        violations.append(
            {
                "file": str(filepath),
                "line": v.range.start.line,
                "rule": code,
                "message": message,
                "severity": _severity_for_code(code),
            }
        )

    json.dump(violations, sys.stdout)
    print(file=sys.stdout)  # trailing newline
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
