# L3 Error Handling Mechanism (TypeScript)

**Status:** Decided 2026-05-08
**Decision:** `neverthrow` with layout-stratified severities, plus a reference
discriminated-union error type shipped at `@afdudley/aspergillus/errors`.

## Context

Aspergillus Level 3 enforces NASA Power of 10 Rule 7: *errors must be visible
in types and impossible to silently drop.* In TypeScript, errors propagate
via `throw` by default. Throw is invisible to the type signature
(`(): T` says nothing about the error path) and trivially ignorable by the
caller. L3 must close both gaps.

The original `docs/design.md` listed `functional/no-throw-statements` plus
`neverthrow` as the implementation hint, but the choice of mechanism was
never argued through. This document captures the options considered and
why we landed on neverthrow.

The decision is informed by a survey of the codebases that will adopt
L3 (three TypeScript projects of different shapes — fullstack web app,
backend service, frontend SPA — totalling roughly 95k LOC). We are the
only consumers of aspergillus today.

## Decision

L3 in TypeScript uses **`neverthrow`** as the Result-type library, with:

- `functional/no-throw-statements` in functional-core layers, `off`
  in imperative-shell layers
- `@okee-tech/neverthrow/must-consume-result` everywhere it's wired
  (type-aware; lints on the type, not the import path)
- `@typescript-eslint/strict-boolean-expressions` (type soundness
  for `if (result)` patterns)
- `tsconfig.strictNullChecks: true` (covers ASP302 — no null/undefined as
  error signal)

> **Severity note:** the rule severities specified in this ADR's option
> survey (`error`) predate the severity-graduation ADR
> ([`docs/decisions/2026-05-19-severity-graduation.md`](../decisions/2026-05-19-severity-graduation.md)).
> All three new L3 rules land at **`warn`** per that workflow and are
> promoted to `error` per layer once violations reach zero. The
> implementation reflects the post-graduation severities; this section's
> historical wording is preserved for context.

Severities are stratified per `boundaries/elements` layer via the layout
itself, not by consumer-side `files:` overrides.

`ResultAsync<T, E>` is the default for async paths; `Promise<Result<T, E>>`
is allowed where one-step async is more readable. Both are lint-clean.

A reference error type ships at `@afdudley/aspergillus/errors`. Consumers
may use it, build their own, or skip the helper — aspergillus rules enforce
shape, not import.

## Options considered

### A. Throw + boundary discipline (no Result types)

Keep exceptions. Custom rule forbids `throw` escaping the functional core.
`try/catch` is allowed only in declared shell layers. Errors propagate via
exception until they hit a boundary handler.

**Pros**
- Smallest migration delta — one of the surveyed codebases already
  follows this pattern by convention, and most try/catch sites in the
  others already form de facto boundaries at HTTP / hook layers
- No runtime dependency, no library lock-in
- No type signature changes to existing functions
- Compatible with third-party libs that throw (zod `.parse`, `fetch`,
  ORM clients, wallet SDKs)

**Cons**
- Relaxes Rule 7. The strict reading is "every caller inspects every
  return value" — boundary discipline only guarantees "errors reach a
  declared boundary." Different semantic guarantee.
- Type signatures still lie — `(): T` doesn't reveal the error union
- Aspergillus must build and maintain a custom rule. No off-the-shelf
  plugin does "throws restricted to types extending X, boundary-aware,"
  so we'd own the implementation, edge cases, type-inference quirks,
  and ongoing maintenance ourselves

### B. Plain discriminated unions

Every fallible function returns `{ ok: true; value: T } | { ok: false; error: E }`.
No library. Custom aspergillus rule enforces the shape. Standard TS
exhaustiveness checking forces handling.

**Pros**
- No runtime dependency, no library lock-in
- Strict Rule 7 — TS exhaustiveness on `switch (r.ok)` forces inspection
- Lightest type surface; trivial to migrate to/from another shape later

**Cons**
- No combinator helpers (`.andThen`, `.map`, `.match`) — callers write
  more boilerplate, especially for chained async
- Must build a small helper module in every consumer (`bind`, `mapAsync`,
  etc.) or accept verbose call sites
- Aspergillus must build and maintain a custom rule for the shape
  requirement; no plugin enforces "discriminated union with `ok`
  discriminator." Same maintenance burden as option A.

### C. `neverthrow` ← **chosen**

`Result<T, E>` and `ResultAsync<T, E>` from a small (~1k LOC) library.
Lint enforcement via `@okee-tech/eslint-plugin-neverthrow`'s
`must-consume-result` rule (type-aware; checks the resolved type, not
the import).

**Pros**
- Strict Rule 7 — `must-consume-result` is type-aware and forces handling
- Mature library, stable API, narrow scope (Result types only — no DI,
  no streams, no schema)
- Small surface area is hard to misuse; contributors can't accidentally
  reach for advanced features
- Standard combinator API (`andThen`, `map`, `match`, `unwrapOr`) familiar
  from Rust / fp-ts / Haskell

**Cons**
- Runtime dependency on `neverthrow`
- Heavy migration cost on the largest consumer codebase — every service
  signature changes, hundreds of inline `try/catch` + status-code sites
  need refactoring
- Lock-in: type signatures across consumer code reference `Result` /
  `ResultAsync` from neverthrow. Migrating away is a per-consumer
  rewrite (see Risks)
- Validation libraries that throw (zod `.parse`) require a `.safeParse`
  + adapter migration in any codebase that uses them in core layers
  (mechanical but not free)

### D. `effect-ts`

`Effect<A, E, R>` from a much larger library. Three type parameters
(Success, Error, Requirements). Lazy / runnable computation model.
Lint via `@effect/eslint-plugin`.

**Pros**
- Most active TS error-handling ecosystem in 2025–2026
- Richer feature set if we need it later: dependency injection (Layer),
  schema (replaces zod), streaming, structured concurrency
- Generators (`Effect.gen`) read like async/await, less awkward than
  combinator chains for long sequences

**Cons**
- Paradigm shift, not just an error-handling change. Lazy computation
  model is foreign to most TS code (every Effect must be `runPromise`d
  at the boundary)
- Gravitational pull toward `Layer` / `Schema` / `Stream` once it's in
  the codebase. Hard to lint "use only the Effect-as-Result subset"
- ~500 modules vs neverthrow's tight surface — bigger lock-in to a
  bigger paradigm
- Three type parameters even when DI isn't used (`Effect<A, E, never>`)
  — more ceremony per signature

### E. `fp-ts`

Rejected outright. The project has been folded into `effect-ts`; new
fp-ts adoption in 2026 is a dead end.

## Survey data

Counts gathered 2026-05-07 across the three consumer codebases (source
files only; no node_modules / dist / generated dirs). Codebases anonymized
by shape.

| | Fullstack web app | Backend service | Frontend SPA |
|---|---|---|---|
| TS files / LOC | 166 / 63k | 137 / 9.6k | 202 / 23k |
| `throw` statements | 67 | 32 | 26 |
| `try {` blocks | 639 (>300 in one file) | 37 | 25 |
| `await` keywords | 1580 | 408 | 97 |
| `Promise.all*` | 42 | 28 | 12 |
| Existing `Result` / neverthrow types | 0 | 0 | 0 |
| Local `{ ok: ... }` shapes | 7 | 2 | 1 |
| Error class hierarchy | none | discriminated `AppError` + subclasses | single `ApiError` |
| zod `.parse` / `.safeParse` | 91 / 0 | 6 / 3 | 4 / 32 |

Findings that drive the decision:

- Zero existing adoption of Result types across any consumer. No partial
  migration to leverage for any library-based mechanism.
- Throws cluster at edges (≈125 total across 95k LOC). The functional
  cores are largely throw-free already; most of the work is in services
  and edge translators.
- One consumer's catch sites are concentrated in a single large file
  (>300 in one route module), which is also a pending L2 cleanup target.
  Sequencing concerns flagged separately.
- One consumer already has a discriminated error hierarchy and a thin
  catch layer at the framework boundary — closest to mechanism A's
  shape today.
- Validation throws (`zod .parse`) are concentrated in the largest
  consumer; the frontend has already shifted toward `.safeParse`.

## Why neverthrow over the alternatives

Two arguments converge on neverthrow.

### 1. Strict Rule 7 over relaxed Rule 7

The first axis is whether L3 should enforce the strict reading of Rule
7 (every caller inspects every return value, B/C/D) or the relaxed
reading (errors typed and reach a declared boundary, A). We chose
strict because L3 is the level where aspergillus stops being "good
defaults" and starts being a discipline — relaxing the fundamental
rule at this level undermines what L3 is for.

### 2. Use an existing implementation rather than ship our own

The second axis is whether to build the enforcement mechanism ourselves
(A and B both require aspergillus to write and maintain a custom rule)
or to compose existing tools (C and D pull in a published library plus
a published lint plugin).

Building our own custom rule is a recurring liability:

- The rule must handle TypeScript's full type-inference surface (union
  types, generics, conditional types, mapped types, `unknown` vs `any`).
  Type-aware ESLint rules are notoriously fragile across compiler
  versions.
- Edge cases for "throw of value that extends X" or "shape with `ok`
  discriminator" multiply quickly with intersections, computed
  property names, and legitimate framework patterns.
- Aspergillus is a small project; every custom rule we ship is a piece
  of code we own forever. `must-consume-result` already exists, is
  battle-tested, and has external maintainers tracking typescript-eslint
  compat — that's leverage we'd throw away by reinventing it.

This pushes against A and B independently of the strict/relaxed split.

### Among the library options

- **D (effect-ts)** is overkill. We don't need DI, streaming, or schema.
  The gravitational pull toward `Layer` / `Schema` / `Stream` is a
  liability when we want focused enforcement of error-handling
  discipline. If the goal were "build TS apps in a functional-effects
  paradigm" it would be the right call — but it's not.
- **C (neverthrow)** is the smallest library that delivers strict Rule 7.
  Narrow scope is a feature: hard to misuse, no paradigm leakage.

### On the lock-in concern

If we later need an effect system, migrating from neverthrow to
effect-ts is roughly the same scope as migrating from throw to either
— a type-signature flag day. We're not painting ourselves into a
corner that isn't already inherent in the strict-Rule-7 choice.

## Consequences

### Aspergillus changes (must land before any consumer migration)

1. **Layout API refactor.** Layouts currently export a single config
   block. They must export an array of blocks with `files:` selectors
   per `boundaries/elements` layer, so the layout itself owns L3
   severity stratification. This is a breaking change to the layout API
   — accepted because we are the only consumers.

2. **L3 rule wiring** in the base eslint config: `functional/no-throw-statements`,
   `@okee-tech/neverthrow/must-consume-result`,
   `@typescript-eslint/strict-boolean-expressions`. Plugins added to
   peer dependencies.

3. **Reference error module** at `@afdudley/aspergillus/errors`:
   `AspError<TTag, TData>` type + `aspError()` constructor. Optional;
   aspergillus rules enforce shape, not import.

4. **`docs/design.md` update** — rewrite the L3 row of the rule table
   and the L3 prose to reflect this decision. Cross-link this document.

### Out of scope for this decision

- ASP303+ rules beyond the three named above
- Python and Rust L3 — same NASA Rule 7 spirit, different mechanisms
  (Python = AST-based, Rust = native `Result` + clippy). Cross-language
  consistency is at the *spec* level, not the implementation level.
- ASP204 custom-rule replacement (still on `functional/no-loop-statements`
  over-approximation) — L2 cleanup, not blocking L3
- A `ci-gate` test helper that asserts effective rule severities by
  reading `eslint --print-config` output — useful for locking severities
  against silent drift, but separate from the mechanism choice
- Per-consumer migration sequencing and timelines — tracked separately

## Risks and mitigations

### Migration half-finishes

L3 migrations are the kind of large mechanical refactor that's easy to
abandon at 60%. Half-migrated codebases are worse than either fully-
migrated or untouched — Result types in some places, throw in others,
inconsistent at the seams.

*Mitigation.* Sequence consumer migrations by layer, not by file. Keep
all of `services/` at warn until 100% of `services/` is migrated, then
flip to error in the same PR that completes the layer. Atomic flips
prevent silent regression.

### Aspirational-config drift

A common failure mode when adopting strict lint rules: turn the rule
on at `error` everywhere, then suppress every site that fails with
`eslint-disable`. The config looks rigorous but the codebase is not
migrated. The end state is worse than not turning the rule on at all
— violations are no longer visible in lint output, and a periodic
audit is the only way to discover the drift.

*Mitigation.* Three guardrails:

1. Rules land at `warn` and only flip to `error` once the relevant
   layer reaches zero violations (the existing severity-flip workflow).
2. `eslint-disable` for L3 rules requires a justification comment,
   enforced via `eslint-comments/require-description`. PRs that add
   disables without justification get rejected.
3. A periodic audit script (could ship as the optional `ci-gate`
   helper) counts disables per rule per consumer and reports drift.

### neverthrow ecosystem lock-in

If the TS ecosystem moves to effect-ts or a native Result, every
consumer codebase has neverthrow types in every public function
signature. Migration is a per-consumer rewrite.

*Mitigation.* Aspergillus's own coupling stays at the lint-plugin layer
(`must-consume-result`), never at imports. We don't write a custom rule
that hardcodes `from 'neverthrow'`. If a competing library shipped an
equivalent type-aware rule, aspergillus could swap one config line and
release a new layout version. Consumers still own their migration —
that cost is fundamental to the strict-Rule-7 choice and can't be
eliminated.

The risk is real but bounded. neverthrow is mature, narrow-scope, and
the only credible alternative (effect-ts) is a deliberately different
paradigm — nobody migrates to it accidentally. Accepted.

### Validation libraries that throw

zod's `.parse` throws on invalid input, and consumer codebases have
adopted it heavily inside what will become functional-core layers.
These call sites are incompatible with `no-throw-statements` and won't
quietly comply just by enabling the rule.

*Mitigation.* Treat zod (and similar validators) as third-party-throws,
same category as `fetch` or wallet SDKs. Wrap with a small
`safeParseResult` helper at the validator call site, returning
`Result<T, ValidationError>`. Schema *definitions* can live in core;
parsing happens at the FC/IS boundary. Aspergillus may ship the helper
in `@afdudley/aspergillus/errors` or a sibling utility module.

### Layout API breaking change

Refactoring layouts from single-block to array-of-blocks breaks any
consumer currently spreading them.

*Mitigation.* We are the only consumers. The change lands atomically
with the L3 rollout and the consumer wrappers update at the same time.
No deprecation path needed.

## References

- `docs/design.md` — L3 row of the rule table (to be updated)
- `@okee-tech/eslint-plugin-neverthrow` — type-aware lint rule that
  makes neverthrow load-bearing rather than optional
