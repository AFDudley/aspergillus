# Slop to Production

**User**: A developer who writes quick hacks, prototypes, and incomplete
code. They don't want friction. They want to ship fast.

**Input**: Developer commits slop to a dev repo. No tests, no docs, no
type hints, hardcoded values, no error handling. Valid code that works
on their machine.

**What happens**: An orchestrator (today: exophial; see
[exophial's user story](https://github.com/AFDudley/exophial/blob/main/docs/user_stories/slop_to_production.md))
watches for commits and triggers a refinement pipeline. The pipeline is
a *grammar cascade*: each layer enforces a more refined set of
constraints, and aspergillus is the L2/L3 implementer.

## The cascade

1. **L0 (program lifting)**: Generate behavior tests from existing
   code. These are informal schema entries — composable types and
   process verbs captured by running the code. Also classify defects
   by ODC type.
2. **L1a (formatting / linting / types / security baseline)**: Apply
   ruff / mypy / bandit (Python), ESLint / Prettier / tsc (TypeScript),
   clippy / rustfmt (Rust). L0 schema entries must stay green —
   behavior preserved.
3. **L1b (ODC pattern detection)**: Mechanical defects — hardcoded
   values, missing error handling, wrong API usage — detected via
   tree-pattern queries. Aspergillus's `ast-grep-rules/` directories
   contribute here when the pattern + fix is shape-expressible.
4. **L2/L3 (aspergillus)**: Structural quality — function length,
   purity, assertion density, type safety, Result-vs-exceptions. The
   grammar cascade applies catalog moves to satisfy these constraints,
   only rejecting when no mechanical move resolves the violation.
5. **Validation**: All grammar layers pass. Constraint ratio meets
   threshold.
6. **Merge**: Push to a prod repo. Only validated, production-quality
   code lands.

If refinement fails: escalate to a human. The developer is never
blocked.

## Aspergillus's role: L2/L3 (and part of L1b)

Aspergillus implements the L2/L3 layer of the cascade. It is *the*
unified rule corpus the orchestrator runs at this layer. Internally,
aspergillus uses three engines (see
[`design.md`](design.md) §"Multi-engine architecture"):

- **Custom ESLint rules + plugins** for TypeScript constraint checks
  (function length, assertion density, FC/IS boundaries).
- **fixit / LibCST** for Python constraint checks (the same constraints
  expressed on Python's CST surface).
- **ast-grep** for declarative shape rewrites that apply uniformly
  across TypeScript and Python — this engine also contributes to L1b
  (mechanical ODC patterns whose trigger and fix are tree-shape
  expressible).

The orchestrator does not pick an engine. It runs aspergillus, which
internally routes each rule to the engine that fits it. Autofix is
per-engine: ast-grep applies its `fix:` clause, ESLint applies its
fixer function, fixit applies its `replacement` / `@invoke_after`.
From the consumer's perspective, there is one tool with one rule
corpus.

### Catalog corpus

The list of canonical refinement moves — Extract Function, Split
Phase, map-fusion, Tupling, Worker/Wrapper, comprehension-from-loop,
etc. — is the consumer-facing surface. The reference home for this
corpus is `docs/refactoring-catalog.md` in this repo (not yet seeded;
expected to grow as consumers migrate their move catalogs to
aspergillus). The orchestrator's "agent refines slop" step consults
the catalog; aspergillus mechanically applies the subset of moves
expressible as engine rules.

## Example

Developer commits:

```python
def get_user(id):
    return requests.get(f"http://localhost:3000/users/{id}").json()
```

Grammar cascade detects:

- **L1a**: missing type hints (mypy), hardcoded URL (ruff).
- **L1b**: Assignment defect (hardcoded URL), Checking defect (no
  error handling). Aspergillus contributes pattern matches via
  `python/ast-grep-rules/` where the rewrite is shape-expressible.
- **L2/L3 (aspergillus)**: ASP205 (impure function — `requests.get`
  inside the function body), ASP206 (mixed I/O and logic). The
  agent applies catalog moves (lift I/O to a boundary, return a
  `Result`-typed wrapper, parameterize the URL).

Behavior tests from L0 verify the refined code still fetches users
correctly. Constraint ratio improves at every layer.

## Severity discipline

Aspergillus rules ship at `error` once they're proven. New rules MAY
land at `warn` per the graduation workflow in
[`decisions/2026-05-19-severity-graduation.md`](decisions/2026-05-19-severity-graduation.md);
they reach mature state only when promoted to `error` with autofix
encoded (or `error` without autofix, for rules whose violation has
no single mechanical resolution — ASP201 function length is the
canonical example: the agent must pick where to split).

"Info severity" is not part of the discipline. An info-level finding
either resolves a constraint (in which case it should block) or
doesn't (in which case it shouldn't exist). See the ADR for full
reasoning.

## Timeline

15 minutes from slop commit to production deployment, on the happy
path.

## What the developer sees

Nothing changes. They commit to the dev repo as usual. 10 minutes
later: "Your commit deployed to production as v1.2.3." The refined
version, not the original slop.

## Phased rollout

- **Phase 1 (Shadow)**: Refinement runs, prod repo not deployed.
  Prove the cascade works.
- **Phase 2 (Cutover)**: Prod deploys from the refined repo.
  Developer workflow unchanged.
- **Phase 3 (Adoption)**: Developers shift to the orchestrator's
  CLI / issue automation.
- **Phase 4 (Consolidation)**: Dev repo becomes an optional escape
  hatch.

## Key principle

Don't force workflow change. The grammar cascade provides invisible
quality improvement. Let benefits drive adoption.

## For critical paths

The lift path (L0 → L4 → L5) applies. Schema entries from L0 project
directly to PDDL via the orchestrator's `manage_schema project`
verb; Lean proofs verify correctness. See the orchestrator's
DESIGN_BY_CONTRACT.md for the lift mechanics. This document scopes
to L1a → L2/L3 — the path the typical dev commit travels.

## Cross-references

- [`design.md`](design.md) §"Multi-engine architecture" — how
  aspergillus's three engines (ESLint, fixit, ast-grep) compose
  under one rule corpus.
- [`decisions/2026-05-19-severity-graduation.md`](decisions/2026-05-19-severity-graduation.md)
  — the warn-then-promote workflow and mature-state target this
  doc references.
- The orchestrator's user story for slop-to-production lives in
  exophial's `docs/user_stories/slop_to_production.md`. This
  aspergillus copy is the L2/L3 implementer's perspective; the
  exophial copy is the orchestrator's perspective on the full
  cascade including program lifting, dagster-composable pipelines,
  and merge-to-prod mechanics.
