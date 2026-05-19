# Aspergillus — Python ast-grep rules

Declarative, pattern-based rewrite rules for Python, expressed as
[ast-grep](https://ast-grep.github.io/) YAML. ast-grep is the third
engine in aspergillus's multi-engine architecture (see
[`../../docs/design.md`](../../docs/design.md) §"Multi-engine
architecture"); the other two are fixit/LibCST rules (in
[`../src/aspergillus/rules/`](../src/aspergillus/rules/)) and stock
external tooling (ruff, mypy, bandit) configured via
[`../src/aspergillus/configs/`](../src/aspergillus/configs/).

## What lives here vs. in `../src/aspergillus/rules/`

| Concern | Engine | Lives in |
|---|---|---|
| Constraint-shaped checks (function length, assertion density, I/O purity, raise-instead-of-Result) | fixit/LibCST | [`../src/aspergillus/rules/`](../src/aspergillus/rules/) |
| Declarative shape rewrites (e.g. catalog moves like map-fusion, comprehension-from-loop) | ast-grep, YAML pattern + rewrite | this directory |
| Stock-tool baselines (ruff, mypy, bandit) | external | [`../src/aspergillus/configs/`](../src/aspergillus/configs/) |

The split is engine-by-engine, not by category. A rule belongs in
`ast-grep-rules/` when its trigger and its rewrite are both expressible
as a tree pattern + a replacement template — i.e. the rule has a single
mechanical rewrite that needs no semantic reasoning beyond AST shape
matching. Rules that need type information, control-flow analysis, or
the CST-level surface fixit exposes go to fixit instead.

## Authoring a rule

ast-grep rules are YAML files. The minimal shape:

```yaml
id: asp-py-double-map-collapse
language: Python
severity: error
message: Two consecutive map() calls collapse to one map() over the composed function.
rule:
  pattern: list(map($G, map($F, $X)))
fix: list(map(lambda x: $G($F(x)), $X))
```

Reference docs: <https://ast-grep.github.io/guide/rule-config.html>.
Test fixtures live alongside each rule as `<rule-id>.test.yaml` (see
ast-grep test runner: <https://ast-grep.github.io/guide/test-rule.html>).

## Severity discipline

All rules in this directory ship at `error` with `fix:` populated.
Rules without a mechanical rewrite belong in fixit
([`../src/aspergillus/rules/`](../src/aspergillus/rules/)), not here.
The reasoning is the severity-graduation ADR
([`../../docs/decisions/2026-05-19-severity-graduation.md`](../../docs/decisions/2026-05-19-severity-graduation.md)):
ast-grep's value is *applying* the rewrite, not surfacing a suggestion.
A pattern-with-no-fix is a fixit check, not an ast-grep rule.

New rules MAY transit `warn` per the graduation workflow in that ADR,
but reach mature state only when they ship at `error` with the
mechanical rewrite encoded.

## Cross-references

- [`../../docs/design.md`](../../docs/design.md) §"Multi-engine
  architecture" — how this directory fits into the three-engine model.
- [`../../docs/slop_to_production.md`](../../docs/slop_to_production.md) —
  ast-grep's role in the L1b ODC patterns layer and L2/L3
  constraint-enforcement layer of the slop-to-production cascade.
- [`../../docs/decisions/2026-05-19-severity-graduation.md`](../../docs/decisions/2026-05-19-severity-graduation.md) —
  warn-then-promote workflow and mature-state targets.
- [`../src/aspergillus/rules/`](../src/aspergillus/rules/) — the
  sibling fixit/LibCST rules surface.
