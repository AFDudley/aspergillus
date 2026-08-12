"""Corpus purity ratio — the criterion ASP205 could not evaluate.

NASA's Power of 10 Level-2 guidance, as this rule set states it, asks
that most of a program be pure. The retired ASP205 (see the retirement
note in ``rules/level2.py``) tried to enforce that per function: it
reported every function whose body called a name in ``io_blocklist``.
That is the wrong unit. "Too little of this program is pure" is a claim
about a corpus, and a fixit ``LintRule`` sees one file, so it cannot
decide it. Reported per function the claim also had no legal passing
form, because a boundary function exists in order to perform its effect.

This module states the criterion where it can be decided: over a whole
tree, as one ratio, against one floor. Pure logic lives here; the
imperative shell (argument parsing, filesystem reads, stdout) lives in
``__main__.py``, the same split ``duplicates.py`` uses.

The effect signal is ``rules.level2._find_io_calls`` — the SAME
``io_blocklist`` predicate ASP205 used and ASP202/ASP206 still use, so
this command and those rules never disagree about what an effect is.
"""

from __future__ import annotations

from dataclasses import dataclass

import libcst as cst

from aspergillus.rules.level2 import _find_io_calls

#: NASA Level 2 target: at least this share of a corpus's functions are pure.
DEFAULT_MIN_PURE_RATIO = 0.70


@dataclass(frozen=True)
class FunctionPurity:
    """One function and the effect names attributed to its OWN body."""

    path: str
    line: int
    name: str
    io_calls: tuple[str, ...]

    @property
    def pure(self) -> bool:
        return not self.io_calls


@dataclass(frozen=True)
class PurityReport:
    """A corpus's purity ratio against a floor."""

    total: int
    impure: int
    min_ratio: float
    worst: tuple[tuple[str, int], ...]

    @property
    def pure(self) -> int:
        return self.total - self.impure

    @property
    def ratio(self) -> float:
        """Share of functions with no effect. An empty corpus is pure."""
        if self.total == 0:
            return 1.0
        return self.pure / self.total

    @property
    def meets_target(self) -> bool:
        return self.ratio >= self.min_ratio


def function_purities(path: str, source: str) -> list[FunctionPurity]:
    """Attribute effects to each function in ``source`` (pure).

    Attribution follows ``_find_io_calls``: a function owns the effects
    in its OWN body, never those of a nested ``def`` or ``lambda``, which
    are counted as their own functions.
    """
    module = cst.parse_module(source)
    wrapper = cst.MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(cst.metadata.PositionProvider)
    out: list[FunctionPurity] = []
    for node in _iter_functions(wrapper.module):
        out.append(
            FunctionPurity(
                path=path,
                line=positions[node].start.line,
                name=node.name.value,
                io_calls=tuple(sorted(_find_io_calls(node.body))),
            )
        )
    return out


def summarize(purities: list[FunctionPurity], min_ratio: float, worst_n: int = 10) -> PurityReport:
    """Fold per-function verdicts into one corpus ratio (pure)."""
    assert 0.0 <= min_ratio <= 1.0, "a purity floor is a ratio in [0, 1]"
    assert worst_n >= 0, "worst_n counts files and cannot be negative"
    per_file: dict[str, int] = {}
    impure = 0
    for item in purities:
        if item.pure:
            continue
        impure += 1
        per_file[item.path] = per_file.get(item.path, 0) + 1
    worst = tuple(sorted(per_file.items(), key=lambda kv: (-kv[1], kv[0]))[:worst_n])
    return PurityReport(total=len(purities), impure=impure, min_ratio=min_ratio, worst=worst)


def format_report(report: PurityReport) -> str:
    """Render a report for a terminal (pure)."""
    verdict = "OK" if report.meets_target else "BELOW TARGET"
    lines = [
        f"purity-ratio: {report.pure}/{report.total} functions pure "
        f"({report.ratio:.1%}), floor {report.min_ratio:.0%} — {verdict}",
    ]
    if report.worst:
        lines.append("effect-bearing functions by file:")
        lines.extend(f"  {count:5d}  {path}" for path, count in report.worst)
    return "\n".join(lines) + "\n"


def _iter_functions(node: cst.CSTNode) -> list[cst.FunctionDef]:
    out: list[cst.FunctionDef] = []
    stack = [node]
    while stack:
        current = stack.pop()
        for child in current.children:
            if isinstance(child, cst.FunctionDef):
                out.append(child)
            stack.append(child)
    return out
