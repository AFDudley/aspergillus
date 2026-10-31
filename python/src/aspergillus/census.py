"""Census of every I/O-bearing function in a tree.

The retired ASP205 (see the retirement note in ``rules/level2.py``)
reported a per-function verdict, which was wrong: a boundary function
exists in order to perform its effect, so the finding had no legal
passing form. But the verdict was not the only thing ASP205 produced.
It also produced a STANDING ENUMERATION — one line for every function
in the tree that performs an effect — and the enumeration was correct.
Deleting the rule deleted both.

This module restores the enumeration alone. It reports where the
effects are. It states no floor, it reaches no verdict, and the command
that wraps it always exits 0. That is the whole point: the same content
is a defect as a lint rule and an instrument as a census.

It is also the input to a layer rule. Once a tree separates a shell
layer from a core layer, "an effect outside the shell layer" is this
same enumeration with a predicate on it — and THAT predicate can fail,
because a core module has a legal passing form: move the effect.

The effect signal is ``rules.level2._find_io_calls`` — the SAME
``io_blocklist`` predicate ASP205 used and ASP202/ASP206 still use, so
this census and those rules never disagree about what an effect is.

Attribution follows ``_find_io_calls``: a function owns the effects in
its OWN body, never those of a nested ``def`` or ``lambda``, which the
census reports as functions in their own right.

Pure logic lives here; the imperative shell (argument parsing,
filesystem reads, stdout) lives in ``__main__.py``, the same split
``duplicates.py`` uses.
"""

from __future__ import annotations

from dataclasses import dataclass

import libcst as cst

from aspergillus.rules.level2 import _find_io_calls


@dataclass(frozen=True)
class EffectSite:
    """One function that performs an effect, and which effects."""

    path: str
    line: int
    qualname: str
    io_calls: tuple[str, ...]


@dataclass(frozen=True)
class Census:
    """Every effect-bearing function in a corpus, and the corpus size.

    ``scanned`` is every function the census looked at, effect-bearing
    or not. It is reported so a reader can see the population the
    enumeration came from. It is NOT a denominator: this census
    computes no ratio, because a ratio moves when a pure function is
    added and no effect has moved.
    """

    scanned: int
    sites: tuple[EffectSite, ...]

    @property
    def modules(self) -> tuple[str, ...]:
        """Every module holding at least one effect, in path order."""
        return tuple(sorted({site.path for site in self.sites}))


def census_of_module(path: str, source: str) -> tuple[int, list[EffectSite]]:
    """Scan one module: (functions seen, effect-bearing ones) (pure)."""
    module = cst.parse_module(source)
    wrapper = cst.MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(cst.metadata.PositionProvider)
    seen = 0
    sites: list[EffectSite] = []
    for prefix, node in _iter_functions(wrapper.module, ()):
        seen += 1
        io_calls = _find_io_calls(node.body)
        if not io_calls:
            continue
        sites.append(
            EffectSite(
                path=path,
                line=positions[node].start.line,
                qualname=".".join(prefix),
                io_calls=tuple(sorted(io_calls)),
            )
        )
    return seen, sites


def merge_censuses(parts: list[tuple[int, list[EffectSite]]]) -> Census:
    """Fold per-module scans into one corpus census (pure)."""
    scanned = 0
    sites: list[EffectSite] = []
    for seen, found in parts:
        scanned += seen
        sites.extend(found)
    sites.sort(key=lambda site: (site.path, site.line, site.qualname))
    return Census(scanned=scanned, sites=tuple(sites))


def format_census(census: Census) -> str:
    """Render the enumeration for a terminal (pure)."""
    lines = [
        f"{site.path}:{site.line}: {site.qualname} — {', '.join(site.io_calls)}"
        for site in census.sites
    ]
    lines.append(
        f"io-census: {len(census.sites)} effect-bearing functions"
        f" in {len(census.modules)} modules, {census.scanned} functions scanned"
    )
    return "\n".join(lines) + "\n"


def _iter_functions(
    node: cst.CSTNode, prefix: tuple[str, ...]
) -> list[tuple[tuple[str, ...], cst.FunctionDef]]:
    """Every function in ``node``, each with its dotted qualified name.

    A class and a nested ``def`` both extend the name, so
    ``Integrator.land_branch`` and ``load.<locals>`` style nesting read
    back to a single source location without a second lookup.
    """
    out: list[tuple[tuple[str, ...], cst.FunctionDef]] = []
    for child in node.children:
        if isinstance(child, cst.FunctionDef):
            here = (*prefix, child.name.value)
            out.append((here, child))
            out.extend(_iter_functions(child, here))
        elif isinstance(child, cst.ClassDef):
            out.extend(_iter_functions(child, (*prefix, child.name.value)))
        else:
            out.extend(_iter_functions(child, prefix))
    return out
