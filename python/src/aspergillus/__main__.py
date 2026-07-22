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
      Whole-project type-2 duplicate-function detector (cross-file — the
      thing a single-file fixit LintRule structurally cannot do). Exit 0 =
      clean, 1 = duplicates found, 2 = input error. Pure logic lives in
      ``duplicates.py``; this module is the imperative shell (argument
      parsing, filesystem reads, stdout). Pebble: asp-21d.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from fixit.api import fixit_bytes
from fixit.ftypes import Config, QualifiedRule
from libcst import ParserSyntaxError

from aspergillus.duplicates import (
    FunctionRecord,
    extract_function_records,
    find_duplicate_groups,
    format_report,
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


def _load_allowlist(path: str | None) -> frozenset[str]:
    """Load the accepted-hash allowlist file, or an empty set if none (IO)."""
    if path is None:
        return frozenset()
    return parse_allowlist(Path(path).read_text(encoding="utf-8"))


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
    groups = find_duplicate_groups(records, ns.min_lines, allowlist)

    if ns.json:
        payload = [
            {
                "normalized_hash": g.normalized_hash,
                "n_lines": g.n_lines,
                "members": [{"path": m.path, "line": m.line, "name": m.name} for m in g.members],
            }
            for g in groups
        ]
        json.dump(payload, sys.stdout)
        print(file=sys.stdout)
    else:
        print(format_report(groups), end="")

    return 1 if groups else 0


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
