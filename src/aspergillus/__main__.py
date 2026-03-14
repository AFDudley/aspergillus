"""CLI entry point: python -m aspergillus <filepath>.

Runs all aspergillus Fixit rules against the given file and outputs
structured JSON to stdout. Exit code 0 = clean, 1 = violations found,
2 = input error (missing file, bad args).

Output format (JSON array):
    [{"file": "path.py", "line": 10, "rule": "ASP201",
      "message": "...", "severity": "high"}, ...]

Severity mapping:
    Level 2 (ASP2xx) -> "high"
    Level 3 (ASP3xx) -> "medium"
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from fixit.api import fixit_bytes
from fixit.ftypes import Config, QualifiedRule


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


def main(argv: list[str] | None = None) -> int:
    """Run aspergillus lint on a single file, output JSON to stdout."""
    args = argv if argv is not None else sys.argv[1:]

    if len(args) != 1:
        print("Usage: python -m aspergillus <filepath>", file=sys.stderr)
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
