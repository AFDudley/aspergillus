# Aspergillus multi-language restructure — design

Date: 2026-04-24

## Goal

Restructure aspergillus to hold Python, TypeScript, and Rust side-by-side so
it can be applied uniformly across many polyglot repos (TrashScan-Explorer,
dumpster-backend, dumpster-frontend, future Node/TS repos, future Rust repos).
Optimize for **ease of adoption** and **ease of extension to future levels**.

## Prior art

A reference polyglot repo has already applied the aspergillus model across
Python, TypeScript, Rust, and Swift. Key observations from that integration:

- **Python:** `uv tool install /path/to/aspergillus`, then
  `[tool.fixit] enable = ["aspergillus.rules"]` in the consuming
  `pyproject.toml`. Pre-commit runs `fixit lint`. Not vendored as a subtree.
- **TypeScript:** No subtree, no custom rules, no shared npm package. One
  hand-written `eslint.config.js` composing stock plugins
  (`eslint-plugin-functional`, `boundaries`, `@okee-tech/neverthrow`).
  ASP202 (assertion density) documented as "Manual" — enforced in code review.
- **Rust:** Stock `clippy.toml` + `Cargo.toml` lints. No dylint.
- **Swift (FFI glue):** Stock SwiftLint.
- **The one portable artifact**: an internal `code-quality.md` document that
  mirrors aspergillus's rule-mapping table. For non-Python languages,
  aspergillus today is functionally a *spec*, not code.

That reference integration also establishes a **per-rule severity-flip
workflow**: every rule lands at `warn`, stays there until violations reach 0,
then flips to `error` in a dedicated PR. This — not level-preset-swapping —
is the incremental axis.

## What "Level N" actually means

Clarified against `docs/design.md`:

- **Level 1** — external tooling baseline (ruff/mypy/black for Python;
  ESLint + `typescript-eslint` + Prettier + strict tsc for TS;
  clippy + rustfmt for Rust). **Not aspergillus code.** Aspergillus only
  ships reference configs.
- **Level 2** — ASP201–206. Python: Fixit rules in `rules/level2.py`.
  TS/Rust: mapped to stock lint rules where possible; "Manual" otherwise.
- **Level 3** — ASP301–302. Same pattern.
- **Level 4/5** — planned, not implemented.

Current Python aspergillus implements Levels 2 and 3. It does **not**
implement Level 1 (Level 1 is external tooling, not aspergillus).

## Non-goal: preset packages per level

We considered shipping `@aspergillus/eslint-config/level1`,
`…/level2`, `…/level3` so consumers flip one string to progress.
Rejected: the prior-art integration proves nobody uses that axis. All
Level 2+3 rules ship together in a single config; rollout is per-rule
severity flip, not per-level preset swap.

## Repository structure

```
aspergillus/
├── README.md                         # entry point, links per-language READMEs
├── docs/
│   ├── design.md                     # updated: multi-language spec-first model
│   ├── implementation-plan.md
│   └── superpowers/specs/            # design docs (this file lives here)
├── python/                           # current src/aspergillus → moves here
│   ├── pyproject.toml
│   ├── src/aspergillus/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── io_blocklist.py
│   │   ├── rules/ (level2.py, level3.py)
│   │   └── configs/ (level1-pyproject.toml, level1-pre-commit-config.yaml)
│   └── tests/
├── typescript/
│   ├── configs/
│   │   ├── eslint.config.js          # reference config for Node + React/Vite projects
│   │   ├── tsconfig.base.json        # strict, ES2022, noUncheckedIndexedAccess, …
│   │   ├── prettier.config.cjs
│   │   └── pre-commit-config.yaml    # husky + lint-staged template
│   ├── cli/                          # stub `aspergillus-ts` — adoption UX
│   │   ├── package.json              # bin: aspergillus-ts
│   │   ├── src/index.ts              # commands: init, check
│   │   └── README.md
│   └── README.md                     # adoption guide + severity-flip workflow
└── rust/
    ├── configs/
    │   ├── clippy.toml
    │   └── cargo-lints.toml          # snippet to paste into consumer Cargo.toml
    └── README.md                     # placeholder; notes future dylint rule for ASP202
```

The canonical rule-mapping table (ASP ID ↔ per-language tool/rule) lives in
`docs/design.md` as part of the multi-language design narrative. Consumer
repos reproduce that table in their own `docs/code-quality.md` (or equivalent)
so it is readable without pulling the aspergillus subtree.

## TypeScript reference configs — contents

### `typescript/configs/eslint.config.js`

Level 1 baseline only at first commit; ASP-mapped rules appended in follow-up
work. The ASP-mapped rule set below mirrors the prior-art integration's
TypeScript config.

**Level 1 (baseline, lands enabled):**

- `@eslint/js` recommended
- `typescript-eslint` recommended
- `eslint-plugin-unused-imports` — auto-fix dead imports
- `eslint-plugin-import` — import ordering, no-cycle
- `@typescript-eslint/no-floating-promises: error`
- `no-console: warn` (allow `warn`, `error`)
- `no-var: error`, `no-param-reassign: error`
- `@typescript-eslint/no-explicit-any: warn` (promotes to `error` at Level 2)
- Prettier integration via `eslint-config-prettier` (no formatting rules in ESLint)

**Level 2 mapped rules (added later; start at `warn`):**

- `max-lines-per-function` — ASP201 — `{ max: 60, skipBlankLines: true, skipComments: true }`
- `functional/no-let`, `functional/immutable-data` — ASP203
- `functional/no-loop-statements` — ASP204
- `boundaries/element-types` — ASP205/206 (requires `settings.boundaries/elements`)
- `@typescript-eslint/strict-boolean-expressions` — strict-null defense
- ASP202 (assertion density) — Manual; documented as code-review responsibility.

**Level 3 mapped rules (added later; start at `warn`):**

- `functional/no-throw-statements`, `functional/no-try-statements` — ASP301
- `@okee-tech/neverthrow/must-consume-result` — ASP301
- `strictNullChecks` in tsconfig + neverthrow-driven return types — ASP302

### `typescript/configs/tsconfig.base.json`

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noFallthroughCasesInSwitch": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "lib": ["esnext", "dom", "dom.iterable"]
  }
}
```

Consumer repos extend this and add project-specific `include`, `paths`, etc.

## Stub CLI — `aspergillus-ts`

Lives in `typescript/cli/`. Published later as `@afdudley/aspergillus-ts`
on the packaged-distribution milestone; in the subtree era consumers invoke
via `node vendor/aspergillus/typescript/cli/dist/index.js`.

**v0.1 commands:**

- `init` — copy `typescript/configs/eslint.config.js`, `tsconfig.base.json`,
  `prettier.config.cjs`, `pre-commit-config.yaml` into the consumer repo root.
  Print the list of devDependencies the consumer must install (and the exact
  `bun add -D …` command). Write a minimal `eslint.config.js` at repo root
  that imports and spreads the vendored reference config. Do **not** install
  deps itself — consumer runs `bun install`.
- `check` — diff the consumer's `eslint.config.js` against the reference.
  Report drift (missing rules, overridden severities still at `warn` for rules
  the reference has at `error`). Exit non-zero on drift; informational for now.

`check` is the drift-detection mechanism that substitutes for semver updates
during the subtree era. Users can run it in CI if they want.

**Explicitly not v0.1:**

- `upgrade` / level-switching flags (no preset packages, nothing to switch).
- Auto-dep installation (consumer owns their package manager).
- Adding individual rules from the CLI.

## Distribution: subtree now, package later

### Phase 1 — Subtree (this spec)

Consumer workflow:

1. `git subtree add --prefix vendor/aspergillus <repo-url> main --squash`
2. `node vendor/aspergillus/typescript/cli/dist/index.js init`
3. `bun add -D <printed devDependencies>`
4. `bun run lint --fix`
5. Flip rule severities from `warn` to `error` per rule as violations reach 0.

Update path: `git subtree pull --prefix vendor/aspergillus <repo-url> main --squash`
then re-run `aspergillus-ts check` to diff local overrides vs reference.

### Phase 2 — Published packages (documented, not built)

Noted in `typescript/README.md` under **"Future: published packages"**:
when the reference configs stabilize across 3+ consumer repos, publish
`@afdudley/eslint-config`, `@afdudley/tsconfig`,
`@afdudley/prettier-config`, and `@afdudley/aspergillus-ts` to
GitHub Packages. Consumer config collapses to:

```js
// eslint.config.js
import base from '@afdudley/eslint-config';
export default [...base, /* repo overrides */];
```
```json
// tsconfig.json
{ "extends": "@afdudley/tsconfig" }
```

Trigger criteria documented: N=3 TS consumers, or first breaking change
requiring coordinated update across consumers.

## Python — minimal change

`src/aspergillus/` → `python/src/aspergillus/`. `pyproject.toml` → `python/pyproject.toml`.
Existing code untouched. `uv tool install ./python` still works;
`[tool.fixit] enable = ["aspergillus.rules"]` still works. The Python tests
move with the code.

The repo-root `pyproject.toml` is removed — each language owns its own
build config.

## Rust — placeholder

`rust/configs/clippy.toml` and `rust/configs/cargo-lints.toml` lifted from the
prior-art integration's agent config. `rust/README.md` documents the mapping
table entries (`clippy::too_many_lines` for ASP201, etc.) and lists ASP202 as
a future dylint rule. No CLI, no custom rules yet.

## Documentation changes

- Update `docs/design.md`:
  - Title: "aspergillus — NASA-grade multi-language linter"
  - Fold in the canonical rule-mapping table (ASP ID ↔ per-language tool)
    so the repo has one authoritative copy.
  - Explicitly scope Python section as the Level 2/3 implementation.
  - Add TypeScript section summarizing the reference-config approach and
    why no custom rules (the stock-plugin mapping covers ASP201/203–206).
  - Add Rust placeholder section.
  - Remove "subtree" as the only integration model; document both
    subtree-now and package-later paths.
- Add `typescript/README.md` with: adoption steps, severity-flip workflow
  explanation, link to the rule-mapping table in `docs/design.md`,
  "Future: published packages" section.

## Incremental adoption model — summary

Consumers progress by **adding rules to one config and flipping severity**,
not by swapping between preset packages.

| Phase per repo | Action | Tool state |
|---|---|---|
| Adopt Level 1 | `aspergillus-ts init` + install deps + `bun run lint --fix` | Baseline rules `error`; `no-explicit-any` at `warn` |
| Add Level 2 rules | Pull subtree; append Level 2 section to local `eslint.config.js` (all `warn`) | Mixed: Level 1 at `error`, Level 2 at `warn` |
| Flip each Level 2 rule | Per-rule PR: fix remaining violations, flip `warn`→`error` | Level 2 rule at `error` |
| Add Level 3 | Same pattern | |

## What we lose vs a polished package+CLI now

Documented for transparency; accepted tradeoff:

- No semver — every subtree update is potentially breaking.
- devDependencies must be kept in sync by hand (mitigated by `aspergillus-ts init` printing them).
- No transitive plugin updates — consumers bump plugin versions manually.
- Drift detection only via optional `aspergillus-ts check` in CI.

Phase 2 (packages) addresses all of the above; the trigger criteria above make
the cutover concrete.

## Migration plan for existing code

1. Move `src/aspergillus/` → `python/src/aspergillus/`; `pyproject.toml` → `python/`. Update `uv.lock` path. Verify `fixit lint` still runs.
2. Scaffold `typescript/` with configs generalized for Node + React/Vite.
3. Scaffold `typescript/cli/` with `init` and `check` commands.
4. Scaffold `rust/` with clippy/Cargo snippets.
5. Update top-level README and `docs/design.md` to the multi-language model.
6. Dog-food by subtree-pulling aspergillus into TrashScan-Explorer and
   running `aspergillus-ts init` → Level 1 baseline lands.

## Verification

- `cd python && uv run pytest` — Python tests still pass after move.
- `cd typescript/cli && bun run build && bun test` — CLI builds, `init`/`check` work against a scratch directory.
- End-to-end dogfood: apply to TrashScan-Explorer; 0 ESLint errors at Level 1 baseline; `aspergillus-ts check` reports 0 drift immediately after `init`.

## Out of scope

- Publishing packages to GitHub Packages (Phase 2).
- Custom ESLint rules for ASP202/ASP205/ASP206 in TypeScript. Stock plugins
  + `boundaries` + "Manual" code-review entries cover the gap for now.
- Dylint rules for Rust.
- Level 4/5 implementation in any language.
