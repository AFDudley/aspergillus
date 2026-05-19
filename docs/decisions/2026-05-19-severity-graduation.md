# Severity graduation — warn-then-promote workflow and mature-state targets

**Status**: Accepted, 2026-05-19.

**Scope**: Aspergillus rules across all three engines (custom ESLint
rules, fixit / LibCST, ast-grep). Consumer-side projects may impose
stricter discipline; this ADR governs aspergillus's own defaults.

## Decision

### Default starting severity

New aspergillus rules MAY land at `warn` (or `info`, but `warn` is the
default — `info` is rarely the right starting point; see "Anti-patterns"
below). The `warn` window exists to let a rule prove itself across real
consumer traffic before it's elevated to commit-blocking.

### Graduation to `error`

A `warn`-level rule graduates to `error` when **all** of these hold:

1. The rule has been live across consumer commits for a window large
   enough to exercise it. Baseline target: **≥50 consumer commits
   exercising the rule's language, OR 2 weeks of consumer activity —
   whichever lands first.** Authors may pick stricter numbers per-rule
   when the rule covers a narrow surface.
2. Zero false-positives observed in that window. A false-positive is a
   rule firing on code the rule's author would not have flagged on
   review. Track these as issues against the rule; a single
   false-positive resets the graduation window.
3. The mechanical rewrite (autofix) is encoded — `fix:` on an ast-grep
   rule, a fixer function on an ESLint rule, `replacement` or
   `@invoke_after` on a fixit rule. **If the mechanical rewrite is
   not expressible**, the rule graduates only to *error-without-autofix*,
   and that constraint is documented in the rule's source file. The
   only rules legitimately in this subset are those whose violation
   has no single mechanical resolution — function-too-long (the agent
   must pick where to split), unbounded-loop (the agent must impose a
   bound that fits the context).

### Mature-state target

**Every aspergillus rule reaches one of two terminal states:**

- `error` **with autofix** — the rule's value is *applying* the
  rewrite. The pre-commit run rewrites staged files; the developer /
  agent sees the rewrite in the commit diff and can reject by
  amending.
- `error` **without autofix** — for the narrow subset where no single
  mechanical rewrite exists. The pre-commit run blocks the commit; the
  developer / agent picks the appropriate catalog move and applies it
  by hand.

**No rule is permanent-`warn`.** A rule that has lived at `warn` for
its graduation window without reaching `error` is one of:

- Untrusted by its author → remove it.
- Conceptually unfinished → close as wontfix, file a follow-up when
  the missing piece (autofix template, false-positive triage, etc.)
  is ready.
- Out of scope for aspergillus → move to a consumer's project-local
  config.

Permanent-`warn` is the antipattern this ADR exists to prevent.

### Consumer override (downstream discipline is theirs)

Aspergillus's defaults govern aspergillus's own development. Downstream
consumers MAY impose stricter rules for their own state — for example,
a consumer's project may decide that *all* aspergillus rules consume at
`error+autofix` or `absent`, with no `warn` middle state. That's a
consumer choice expressed in the consumer's ESLint / fixit config; it
does not change aspergillus's defaults.

A representative example: MTM (a consumer) has a project-state ADR
declaring it past the warn-then-promote phase — every rule MTM
consumes is either `error+autofix` or absent. Aspergillus's
graduation workflow is still valid in the abstract for any
new-to-consumers rule; MTM's stance is a downstream choice, not a
contradiction.

## Why

### Why a `warn` window exists at all

Rules that look correct on the author's machine can mis-fire on
patterns that didn't appear in the author's test corpus. The `warn`
window surfaces these without breaking consumer commits. Once the
window closes with zero false-positives, blocking new violations
costs nothing — the rewrite is mechanical and the rule has been
exercised.

### Why the window must close

The `warn` state is transitional. A rule that never graduates is a
rule the author didn't trust enough to enforce, which means it's
*also* not trusted enough to consume LLM attention, reviewer
attention, or pre-commit runtime. Every `warn`-level output is a
token cost (for refinement agents), a cognitive cost (for human
reviewers), and a maintenance cost (false-positives accumulate
silently because nothing blocks on them). Permanent `warn` is the
linter analogue of permanent `optional: true` in test fixtures: it
*looks* like cautious rollout, but it's actually selecting for rules
that happen not to trigger rather than rules that are correct.

### Why mature-state is binary (autofix or no-autofix)

Aspergillus's value at L2/L3 of the slop-to-production cascade
(see [`../slop_to_production.md`](../slop_to_production.md)) is
*applying catalog moves to satisfy constraints*. Rules with a known
mechanical rewrite ship that rewrite. Rules without one are reserved
for the small set of cases where the agent's judgment is needed (where
to split a function, what bound to impose on a loop). There is no
third "rule that detects but won't auto-fix and won't block" state —
that's permanent-`warn` in disguise, which this ADR forbids.

### Why this is doctrine, not just policy

The graduation workflow is the inverse of "fire and forget." Without
this rule, a maintainer who adds a `warn`-level rule has no obligation
to revisit it. Over time the corpus accumulates rules that fire but
don't block, which the engine-routing in
[`../design.md`](../design.md) §"Multi-engine architecture" cannot
sensibly route. The graduation rule keeps the corpus coherent.

## Anti-patterns

- **Permanent `warn` severity.** If a rule has lived at `warn` past
  its graduation window, decide: promote, remove, or move to a
  consumer's local config. "Leave it at `warn` because we might
  enforce it eventually" is the antipattern.
- **`info` severity as a starting point.** `info` is even further
  from blocking than `warn` and even less likely to graduate. Reserve
  `info` for the narrow case of a rule whose output is purely
  diagnostic (a metric report, a complexity number) and which is
  *not* meant to graduate — and document that intent in the rule's
  source. Don't use `info` as a "softer warn."
- **Adding a rule without a `fix:` clause when one is mechanically
  expressible.** If the rule's trigger pattern is "shape A" and the
  rule's documented resolution is "rewrite to shape B," the `fix:`
  MUST encode B before the rule graduates. Shipping at `error`
  without `fix:` is reserved for the subset where no single
  mechanical resolution exists.
- **Bumping the graduation-window thresholds upward to "give the rule
  more time."** If the rule isn't graduating, it isn't going to —
  see "Permanent `warn`" above. Lowering the threshold for a rule
  with strong evidence is fine; raising it past the documented
  baseline as a stalling tactic isn't.
- **Counting `warn`-level findings as "the rule is working."** The
  point of graduation is *blocking*. Findings without blocks don't
  prove the rule does work in the cascade; they prove the rule fires.

## Relationship to the slop-to-production cascade

Per [`../slop_to_production.md`](../slop_to_production.md), aspergillus
implements L2/L3 of the cascade. Mature-state rules (`error+autofix`)
*apply* catalog moves at this layer; the downstream agent only handles
what catalog moves couldn't resolve. Permanent-`warn` rules would
short-circuit this contract — they would fire without doing the work
the layer is responsible for. The graduation rule keeps the cascade's
L2/L3 layer doing actual refinement, not surfacing hints.

## Relationship to the multi-engine architecture

The graduation rule applies uniformly across all three engines:

- **ast-grep rules** in
  [`../../typescript/ast-grep-rules/`](../../typescript/ast-grep-rules/)
  and [`../../python/ast-grep-rules/`](../../python/ast-grep-rules/)
  encode their fix in the `fix:` field. A rule lacking `fix:` does
  not belong in `ast-grep-rules/` — see the README in each directory.
- **Custom ESLint rules** in
  [`../../typescript/rules/`](../../typescript/rules/) encode their
  fix as a `fixer` function on the rule's `meta` or in the
  `context.report({ fix })` call.
- **fixit / LibCST rules** in
  [`../../python/src/aspergillus/`](../../python/src/aspergillus/)
  encode their fix via `replacement` or `@invoke_after`.

The decision of *which* engine to use for a given rule is per-rule
(see [`../design.md`](../design.md) §"Multi-engine architecture"),
and is independent of severity. Severity is what this ADR governs.

## Cross-references

- [`../design.md`](../design.md) §"Multi-engine architecture" — the
  engine-routing model that severity sits on top of.
- [`../slop_to_production.md`](../slop_to_production.md) — the
  cascade aspergillus implements L2/L3 of; this ADR keeps that
  layer doing real refinement work.
- [`../../typescript/ast-grep-rules/README.md`](../../typescript/ast-grep-rules/README.md)
  and [`../../python/ast-grep-rules/README.md`](../../python/ast-grep-rules/README.md)
  — the rule-author surfaces this ADR governs.
- The catalog of refinement moves (consumer-facing corpus) is
  expected to live at `../refactoring-catalog.md` in this repo; not
  yet seeded.
