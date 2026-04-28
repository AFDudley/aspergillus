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

- **ASP202 (assertion density):** No off-the-shelf TS rule exists for assertion density. Aspergillus ships its own `asp202-min-assertions` rule via the `./eslint-rules` plugin export. Default behavior: skip functions under 10 lines; require ≥2 assertion-like calls (`assert`, `invariant`, `console.assert`, `assert.X`); configurable via rule options.

- **ASP203 (no global mutable state):** Implemented via `no-restricted-syntax` patterns banning module-level `let`/`var` and `export let`/`export var`. Local `let` inside functions remains allowed — NASA's intent is "global" mutable state, not a blanket ban on `let`.

- **ASP204 (no unbounded loops):** NASA's rule requires loops to have a statically-determinable iteration bound (no `while(true)`). There is no off-the-shelf ESLint rule for that predicate, so the current implementation uses `functional/no-loop-statements` — which bans **all** loops, including bounded `for(let i=0; i<N; i++)`. This is a strict over-approximation chosen because it lands at `warn` and surfaces something useful. **To revisit:** replace with a custom `aspergillus/asp204-bounded-loops` rule that detects only unbounded loop patterns (`while(true)`, `for(;;)`, `while(condition)` where condition isn't statically bounded). Tracked under the next aspergillus TS milestone.

- **ASP205/206 (purity boundary, FC/IS):** TypeScript's I/O surface is overwhelmingly import-shaped (`import { writeFile } from 'fs'`, `import http from 'node:http'`, the global `fetch`, ORM/RPC clients) rather than named-call-shaped, so `eslint-plugin-boundaries` enforces the FC/IS pattern more precisely than a Python-style I/O name blocklist would. Aspergillus ships several `./layouts/*` config exports (`node-service`, `rn-app`, `react-spa`, `fullstack-monorepo`, `generic-3-layer`) covering common project shapes. `aspergillus-ts init` prompts for a layout (or `--layout=<name>` non-interactively); the chosen layout is imported into the consumer's `eslint.config.js`, where its element/rule definitions can be overridden by appending a later flat-config block. `--layout=none` skips the import (consumer declares elements themselves). Plan: `docs/superpowers/plans/2026-04-28-typescript-asp205-asp206-purity.md`.

### Level 3 — Warning

| Rule   | Description                        | Python (Fixit)            | TypeScript                                       | Rust |
|--------|------------------------------------|---------------------------|--------------------------------------------------|------|
| ASP301 | Result types, no exceptions        | `RaiseInsteadOfResult`    | `functional/no-throw-statements`, neverthrow     | `Result<T, E>`; `clippy::unwrap_used`/`expect_used`/`panic` |
| ASP302 | No Optional/None returns           | `OptionalReturnType`      | `strictNullChecks` + neverthrow                  | No null in language |

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
