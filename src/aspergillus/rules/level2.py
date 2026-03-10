"""NASA Level 2 rules: pure functions + immutability."""

from __future__ import annotations

import libcst as cst
from fixit import Invalid, LintRule, Valid


class FunctionTooLong(LintRule):
    """ASP201: Functions must fit on one page (<=60 lines).

    NASA Power of 10 Rule #4: Functions should fit on a single
    printed page. This improves readability and testability.
    """

    MESSAGE = "ASP201: Function has {actual} lines (max {max_lines})"
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)
    MAX_LINES = 60

    VALID = [
        Valid(
            "def short():\n" + "".join(f"    x{i} = {i}\n" for i in range(58)) + "    return x0\n"
        ),
        Valid("def one_liner(): pass"),
        Valid("class Foo:\n" "    def method(self):\n" "        pass\n"),
    ]
    INVALID = [
        Invalid(
            "def too_long():\n"
            + "".join(f"    x{i} = {i}\n" for i in range(61))
            + "    return x0\n"
        ),
    ]

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        pos = self.get_metadata(cst.metadata.PositionProvider, node)
        line_count = pos.end.line - pos.start.line + 1
        if line_count > self.MAX_LINES:
            self.report(
                node,
                self.MESSAGE.format(actual=line_count, max_lines=self.MAX_LINES),
            )
