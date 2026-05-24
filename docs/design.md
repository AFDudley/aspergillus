# aspergillus — NASA-grade multi-language linter

A rule set inspired by NASA's Power of 10, implemented as a Fixit/LibCST
rule-pack for Python and as reference configs composing stock linters for
TypeScript and Rust. Named after *Aspergillus nidulans*, the first fungus
NASA intentionally grew on the International Space Station.

## Repository layout

```
aspergillus/
├── docs/                       # design, this file, implementation notes
├── python/                     # Python: actual code (Fixit rules)
├── typescript/                 # TS: reference configs + stub CLI
└── rust/                       # Rust: reference configs (placeholder)
```

Each language subtree stands alone. Consumers pull aspergillus as a git
subtree and use only the language subtree(s) they need.

## Multi-engine architecture

Aspergillus is the unified rule catalog. Consumers see one tool with one
rule set; engines underneath are an internal implementation detail. The
catalog uses three engines, chosen per-rule by what the rule's trigger
and rewrite shapes require:

| Engine | Languages | What it's good at |
|---|---|---|
| Custom ESLint rules + boundary plugins | TypeScript | Constraint-shaped checks that need type info, data-flow, or multi-file context; architectural import boundaries via `eslint-plugin-boundaries`. Lives under [`typescript/rules/`](../typescript/rules/) (custom rules) and [`typescript/configs/`](../typescript/configs/) (composed stock baselines). |
| fixit / LibCST | Python | Constraint-shaped checks on the CST surface — function length, assertion density, I/O purity, raise-vs-Result. Lives under [`python/src/aspergillus/`](../python/src/aspergillus/). |
| [ast-grep](https://ast-grep.github.io/) | TypeScript, Python (cross-language) | Declarative shape rewrites — a YAML rule names a tree pattern and a replacement template, ast-grep applies the rewrite. Best fit for catalog moves whose trigger and fix are both expressible as tree shape (e.g. `.map().map()` → `.map()` over composed function). Lives under [`typescript/ast-grep-rules/`](../typescript/ast-grep-rules/) and [`python/ast-grep-rules/`](../python/ast-grep-rules/). Rust ast-grep coverage is planned but not yet scaffolded — the rust tree remains placeholder-tier (configs only). |

### How an engine gets chosen

A rule lands in `ast-grep-rules/` when **both** of these hold:

1. The violation's trigger is expressible as a tree-shape pattern (no
   type info, no data-flow analysis, no inter-module reasoning needed).
2. There is a *single mechanical rewrite* that resolves it.

If only (1) holds, the rule belongs in ESLint or fixit (constraint
check, no autofix). If neither holds, the rule isn't expressible
mechanically and isn't a candidate for aspergillus at all — it's
review-time concern.

This split aligns with the severity-graduation ADR
([`docs/decisions/2026-05-19-severity-graduation.md`](decisions/2026-05-19-severity-graduation.md)):
ast-grep rules ship at `error` with `fix:` populated, because ast-grep's
value is *applying* the rewrite. Constraint-without-autofix rules
(ASP201 function length, ASP204 unbounded loops) live in the ESLint /
fixit surface where "error without autofix, agent applies the catalog
move" is the contract.

### Consumer's view

A consumer adds aspergillus once (npm install for TS, `uv tool install`
for Python — see [Distribution](#distribution) below) and gets one
rule corpus. Whether a given rule is enforced by ESLint, fixit, or
ast-grep is an implementation detail the consumer doesn't manage. The
catalog of canonical moves (function-too-long → Extract Function;
double-`map` → fused `map`; impure function → boundary lift; etc.) is
the user-facing surface; the engine routing is internal.

### Catalog corpus

The authoritative list of catalog moves — both constraint-driven
(reject-on-violation) and clarity/perf (rewrite-on-detection) — is
maintained downstream in consumer repos that have adopted aspergillus
and accumulated their own move citations. The canonical reference home
for a consumer that wants to centralize their catalog in aspergillus
is `docs/refactoring-catalog.md` in this repo (not yet seeded; see the
slop-to-production doctrine in
[`docs/slop_to_production.md`](slop_to_production.md) for how the L2/L3
layer consumes the corpus).

## Rule set

### Level 1 — External tooling baseline (not aspergillus code)

Handled by existing tools, configured via aspergillus's reference configs:

| Language   | Tools |
|------------|-------|
| Python     | ruff, ruff-format, mypy, bandit, pre-commit |
| TypeScript | ESLint, typescript-eslint, Prettier, tsc strict, pre-commit |
| Rust       | clippy, rustfmt |

Reference configs live in `python/src/aspergillus/configs/`,
`typescript/configs/`, and `rust/configs/` respectively.

### Level 2 — Blocking

| Rule   | Description                              | Python (Fixit)                   | TypeScript                                                | Rust |
|--------|------------------------------------------|----------------------------------|-----------------------------------------------------------|------|
| ASP201 | Function ≤ 60 lines                      | `FunctionTooLong`                | `max-lines-per-function`                                  | `clippy::too_many_lines` |
| ASP202 | Assertion density ≥ 2 per function       | `LowAssertionDensity`            | `aspergillus/asp202-min-assertions` (custom)              | Manual (planned dylint rule) |
| ASP203 | No global mutable state                  | `GlobalMutableState`             | `no-restricted-syntax` (module-level `let`/`var`/`export let`) | Language (no safe `static mut`) |
| ASP204 | No unbounded loops                       | `UnboundedLoop`                  | `functional/no-loop-statements` (strict; revisit)         | Manual (prefer iterators) |
| ASP205 | No impure functions outside I/O boundary | `ImpureFunction`                 | `eslint-plugin-boundaries` + layout templates from `aspergillus-ts init` | Module structure (pure core) |
| ASP206 | Functional core / imperative shell       | `MixedIOAndLogic`                | `eslint-plugin-boundaries` + layout templates from `aspergillus-ts init` | Module structure |

#### TypeScript Level 2 — design notes

- **ASP202 (assertion density):** No off-the-shelf TS rule exists for assertion density. Aspergillus ships its own `asp202-min-assertions` rule via the `./eslint-rules` plugin export. Default behavior: skip functions under 10 lines; require ≥2 assertion-like calls (`assert`, `invariant`, `console.assert`, `assert.X`); configurable via rule options. Two extension points cover common precondition-enforcement patterns that aren't named `assert`: `methodNames` matches a method name regardless of receiver (e.g. `methodNames: ['parse']` counts every Zod `schema.parse(input)`), and `countThrowStatements` counts `throw` statements as assertions (NASA's `assert(cond)` is logically `if (!cond) throw`).

- **ASP203 (no global mutable state):** Implemented via `no-restricted-syntax` patterns banning module-level `let`/`var` and `export let`/`export var`. Local `let` inside functions remains allowed — NASA's intent is "global" mutable state, not a blanket ban on `let`.

- **ASP204 (no unbounded loops):** NASA's rule requires loops to have a statically-determinable iteration bound (no `while(true)`). There is no off-the-shelf ESLint rule for that predicate, so the current implementation uses `functional/no-loop-statements` — which bans **all** loops, including bounded `for(let i=0; i<N; i++)`. This is a strict over-approximation chosen because it lands at `warn` and surfaces something useful. **To revisit:** replace with a custom `aspergillus/asp204-bounded-loops` rule that detects only unbounded loop patterns (`while(true)`, `for(;;)`, `while(condition)` where condition isn't statically bounded). Tracked under the next aspergillus TS milestone.

- **ASP205/206 (purity boundary, FC/IS):** TypeScript's I/O surface is overwhelmingly import-shaped (`import { writeFile } from 'fs'`, `import http from 'node:http'`, the global `fetch`, ORM/RPC clients) rather than named-call-shaped, so `eslint-plugin-boundaries` enforces the FC/IS pattern more precisely than a Python-style I/O name blocklist would. Aspergillus ships several `./layouts/*` config exports (`node-service`, `rn-app`, `react-spa`, `fullstack-monorepo`, `generic-3-layer`) covering common project shapes. `aspergillus-ts init` prompts for a layout (or `--layout=<name>` non-interactively); the chosen layout is imported into the consumer's `eslint.config.js`, where its element/rule definitions can be overridden by appending a later flat-config block. `--layout=none` skips the import (consumer declares elements themselves). Plan: `docs/superpowers/plans/2026-04-28-typescript-asp205-asp206-purity.md`.

### Level 3 — Warning

| Rule   | Description                        | Python (Fixit)            | TypeScript                                       | Rust |
|--------|------------------------------------|---------------------------|--------------------------------------------------|------|
| ASP301 | Result types, no exceptions        | `RaiseInsteadOfResult`    | `functional/no-throw-statements` (FC layers only) + `@okee-tech/neverthrow/must-consume-result` (universal) | `Result<T, E>`; `clippy::unwrap_used`/`expect_used`/`panic` |
| ASP302 | No Optional/None returns           | `OptionalReturnType`      | `tsconfig.strictNullChecks` + `@typescript-eslint/strict-boolean-expressions` | No null in language |

#### TypeScript Level 3 — design notes

Level 3 enforces NASA Power of 10 Rule 7: errors must be visible in
types and impossible to silently drop. In TypeScript this is
implemented via three rules, two of which are universal and one of
which is layer-stratified:

- **`functional/no-throw-statements`** — bans `throw` in functional-core
  layers (`core`, `services`, `shared`, `db`, etc., per the layout).
  Imperative-shell layers (`routes`, `hooks`, `components`, `pages`,
  etc.) keep `throw` available — they are allowed to throw at framework
  boundaries (HTTP, IPC) and catch from third-party libraries that
  throw. Layer-stratification ships in the `./layouts/*` exports, not
  in the base config.
- **`@okee-tech/neverthrow/must-consume-result`** — type-aware; flags
  any `Result<T, E>` that's created and discarded. Universal (FC and
  shell). This is the rule that makes `neverthrow` load-bearing rather
  than optional.
- **`@typescript-eslint/strict-boolean-expressions`** — catches
  `if (result)` ambiguity (truthy on a `Result` object, since
  neverthrow's `Result` is a non-empty object) and similar
  truthy-on-objects patterns. Universal.

Plus `tsconfig.strictNullChecks: true` (covers the ASP302 bullet — no
`null`/`undefined` as error signal). The aspergillus reference
`tsconfig.base.json` already enables `strict: true`, which implies
`strictNullChecks`.

Result types come from the `neverthrow` library (`Result<T, E>` and
`ResultAsync<T, E>`). A reference discriminated-union error helper
ships at `@afdudley/aspergillus/errors` (`AspError<TTag, TData>` +
`aspError(tag, message, data?, cause?)`); consumers may use it, build
their own `AspError`-shaped union, or bring an existing convention.
Aspergillus rules enforce shape, not import.

Severity-flip workflow applies: rules land at `warn` and flip to
`error` once consumers reach zero violations on the relevant layer.
The shell `off` for `no-throw-statements` is permanent.

See `docs/design-decisions/2026-05-08-l3-error-handling-mechanism.md`
for the full rationale, options considered, and risks accepted.

### Levels 4–5 — Planned, not implemented

Contracts, property-based tests (L4), and formal verification (L5). See
`python/src/aspergillus/` for the fullest current implementation, and
this document's history for research pointers.

## Purity / FC/IS enforcement (ASP205/206)

The two languages take different approaches because their I/O surfaces are
shaped differently:

- **Python** uses a curated I/O blocklist (see
  `python/src/aspergillus/io_blocklist.py`). Calls to known I/O functions
  (`subprocess.run`, `urllib.urlopen`, etc.) are pattern-matched inside
  function bodies. Consumers extend the list per-project via
  `[tool.aspergillus] extra_io_functions`. The blocklist works because
  Python's stdlib is the dominant I/O surface and is stable.

- **TypeScript** uses architectural boundaries via `eslint-plugin-boundaries`.
  TS I/O is overwhelmingly import-shaped (`import { writeFile } from 'fs'`,
  global `fetch`, third-party clients), and the npm I/O surface turns over
  too rapidly for a name blocklist to stay current. `eslint-plugin-boundaries`
  enforces what `core/` may import from, which is more precise. Aspergillus
  ships preset layouts (`node-service`, `rn-app`, `react-spa`,
  `fullstack-monorepo`, `generic-3-layer`) consumers select at
  `aspergillus-ts init` time; the layout is imported as a flat-config block
  and can be overridden by the consumer.

## Distribution

Each language subtree has its own distribution path. TypeScript uses
npm; Python uses uv; Rust uses a file copy.

### TypeScript

- **Phase 1 (current): git-URL npm install.** Consumers add
  `github:AFDudley/aspergillus#main` as a devDependency. npm clones the
  repo, runs the root `prepare` script (builds `typescript/cli/dist/`
  via `tsc`), and exposes the package via the `exports` map:

  ```bash
  npm install -D github:AFDudley/aspergillus#main @eslint/js typescript-eslint \
    eslint-plugin-import eslint-plugin-unused-imports eslint-config-prettier \
    eslint prettier typescript
  npx aspergillus-ts init
  ```

  Wrappers reference the package directly:

  ```js
  // eslint.config.js
  import base from '@afdudley/aspergillus/eslint-config';
  export default [...base];
  ```
  ```json
  // tsconfig.json
  { "extends": "@afdudley/aspergillus/tsconfig" }
  ```
  ```cjs
  // prettier.config.cjs
  module.exports = { ...require('@afdudley/aspergillus/prettier-config') };
  ```

  No `vendor/` directory in consumers; aspergillus lives under
  `node_modules/@afdudley/aspergillus/` like any other dependency.

- **Phase 2 (planned): registry publish.** Once the package stabilizes
  across 3+ consumer repos, publish `@afdudley/aspergillus` to
  GitHub Packages. Consumer migration is one line:

  ```diff
  - "@afdudley/aspergillus": "github:AFDudley/aspergillus#main"
  + "@afdudley/aspergillus": "^0.1.0"
  ```

  Package name, `exports` paths, and import specifiers stay identical.

### Python

```bash
uv tool install git+https://github.com/AFDudley/aspergillus.git#subdirectory=python
```

Then in the consumer's `pyproject.toml`:

```toml
[tool.fixit]
enable = ["aspergillus.rules"]
```

### Rust

```bash
curl -fsSL https://raw.githubusercontent.com/AFDudley/aspergillus/main/rust/configs/clippy.toml -o clippy.toml
```

Paste `rust/configs/cargo-lints.toml` contents into the consumer's
`Cargo.toml` under `[lints.clippy]`.

## Enforcement model

- **Level 2 blocks** — pre-commit fails on any violation.
- **Level 3 also blocks** in strict adopters (recommended); warn elsewhere.
- **Severity-flip workflow**: every new rule lands at `warn`, stays there
  until violations reach 0, then flips to `error` in a dedicated PR.
- **Per-rule suppression**: `# noqa: ASP2XX` (Python), ESLint disable comments
  (TS), `#[allow(clippy::…)]` (Rust).

## What this is NOT

- Not a type checker (mypy/tsc/rustc handle that).
- Not a formatter (ruff-format/Prettier/rustfmt handle that).
- Not a general-purpose linter (ruff/ESLint recommended/clippy defaults).
- Not auto-fix (report-only in v0.1 for all three languages).
