# Aspergillus — TypeScript ast-grep rules

Declarative, pattern-based rewrite rules for TypeScript, expressed as
[ast-grep](https://ast-grep.github.io/) YAML. ast-grep is the third
engine in aspergillus's multi-engine architecture (see
[`../../docs/design.md`](../../docs/design.md) §"Multi-engine
architecture"); the other two are ESLint custom rules (in
[`../rules/`](../rules/)) and stock ESLint baseline configs (in
[`../configs/`](../configs/)).

## What lives here vs. in `../rules/`

| Concern | Engine | Lives in |
|---|---|---|
| Constraint-shaped checks (function length, assertion density, FC/IS boundary) | ESLint, custom JS rules + plugins | [`../rules/`](../rules/) |
| Declarative shape rewrites (e.g. "`.map().map()` collapses to a single `.map()` over the composed function") | ast-grep, YAML pattern + rewrite | this directory |
| Stock-tool baselines (`typescript-eslint`, Prettier, tsc strict) | external | [`../configs/`](../configs/) |

The split is engine-by-engine, not by category. A rule belongs in
`ast-grep-rules/` when its trigger and its rewrite are both expressible
as a tree pattern + a replacement template — i.e. the rule has a single
mechanical rewrite that needs no semantic reasoning beyond AST shape
matching. Rules that need data-flow analysis, type information, or
multi-file context go to ESLint instead.

## Authoring a rule

ast-grep rules are YAML files. The minimal shape:

```yaml
id: asp-ts-double-map-collapse
language: TypeScript
severity: error
message: Two consecutive .map() calls collapse to one .map() over the composed function.
rule:
  pattern: $A.map($F).map($G)
fix: $A.map(x => $G($F(x)))
```

Reference docs: <https://ast-grep.github.io/guide/rule-config.html>.
Test fixtures live alongside each rule as `<rule-id>.test.yaml` (see
ast-grep test runner: <https://ast-grep.github.io/guide/test-rule.html>).

## Severity discipline

All rules in this directory ship at `error` with `fix:` populated.
Rules without a mechanical rewrite belong in ESLint
([`../rules/`](../rules/)), not here. The reasoning is the
severity-graduation ADR
([`../../docs/decisions/2026-05-19-severity-graduation.md`](../../docs/decisions/2026-05-19-severity-graduation.md)):
ast-grep's value is *applying* the rewrite, not surfacing a suggestion.
A pattern-with-no-fix is an ESLint check, not an ast-grep rule.

New rules MAY transit `warn` per the graduation workflow in that ADR,
but reach mature state only when they ship at `error` with the
mechanical rewrite encoded.

## Catalog moves deliberately NOT in this directory

Two HIGH-LEVERAGE FP catalog moves from
[`../../docs/refactoring-catalog.md`](../../docs/refactoring-catalog.md)
are absent here for reasons that aren't "we forgot" — they need
pattern logic ast-grep doesn't express:

- **Tupling** (Bird *Pearls* 2010 Pearl 9 / Pearl 11). Trigger is
  "two aggregation calls over the same iterable in the same scope"
  — a CROSS-STATEMENT pattern that requires identifying the iterable
  by name across separate statements and verifying the calls are
  consecutive. ast-grep matches a single tree pattern, not a
  multi-statement sequence with a named-binding identity test. The
  ESLint engine (the project's first engine choice for cross-statement
  analysis) is the better fit. A Tupling rule belongs in
  [`../rules/`](../rules/) if it's added on the TS side at all; the
  Python side ships ASP406 (detection-only) in
  [`../../python/src/aspergillus/rules/catalog/tupling.py`](../../python/src/aspergillus/rules/catalog/tupling.py).

- **Worker/Wrapper** (Gill + Hutton 2009). Trigger is "function whose
  body is a single pass-through call where args structurally match
  the function's params." That's expressible as an ast-grep pattern
  IF the args-match-params check could be encoded as a meta-variable
  constraint — but ast-grep's meta-variables identify subtrees by
  pattern, not by cross-position structural equality (i.e., "$ARGS in
  the call match $PARAMS in the def"). Without the structural-equality
  test, the rule overflags every single-statement return wrapper,
  which is too noisy to ship. The Python side ships ASP407 with the
  structural check encoded in LibCST in
  [`../../python/src/aspergillus/rules/catalog/worker_wrapper.py`](../../python/src/aspergillus/rules/catalog/worker_wrapper.py);
  the equivalent TS encoding needs ESLint (visiting both the
  function-def's params and the return-call's args under the same
  rule instance).

These two moves' value justifies the ESLint-or-LibCST encoding effort
in their respective consumer languages, but they're out of scope for
ast-grep specifically.

A third move (**ASP405 redundant-await-return** / `return await x`)
exists as an ast-grep rule on the TS side
([`redundant-await-return.yml`](redundant-await-return.yml)) but does
NOT have a Python analogue, because Python's async semantics differ
from JS in a way that makes the rewrite incorrect — see
[`../../python/src/aspergillus/rules/catalog/__init__.py`](../../python/src/aspergillus/rules/catalog/__init__.py)
§ "Why no ASP405 redundant-await-return" for the demonstration.

## Cross-references

- [`../../docs/design.md`](../../docs/design.md) §"Multi-engine
  architecture" — how this directory fits into the three-engine model.
- [`../../docs/slop_to_production.md`](../../docs/slop_to_production.md) —
  ast-grep's role in the L1b ODC patterns layer and L2/L3
  constraint-enforcement layer of the slop-to-production cascade.
- [`../../docs/decisions/2026-05-19-severity-graduation.md`](../../docs/decisions/2026-05-19-severity-graduation.md) —
  warn-then-promote workflow and mature-state targets.
- [`../rules/README.md`](../rules/) (if present) — the sibling ESLint
  custom-rules surface.
