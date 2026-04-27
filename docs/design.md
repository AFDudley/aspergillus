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
| ASP205 | No impure functions outside I/O boundary | `ImpureFunction`                 | `eslint-plugin-boundaries` *(planned)*                    | Module structure (pure core) |
| ASP206 | Functional core / imperative shell       | `MixedIOAndLogic`                | `eslint-plugin-boundaries` *(planned)*                    | Module structure |

#### TypeScript Level 2 — design notes

- **ASP202 (assertion density):** Originally specified as "manual code review" because no off-the-shelf TS rule exists. Aspergillus 0.1.0-rc.2 ships its own `asp202-min-assertions` rule via the `./eslint-rules` plugin export. Default behavior: skip functions under 10 lines; require ≥2 assertion-like calls (`assert`, `invariant`, `console.assert`, `assert.X`); configurable via rule options.

- **ASP203 (no global mutable state):** Implemented via `no-restricted-syntax` patterns banning module-level `let`/`var` and `export let`/`export var`. This is narrower than the original `functional/no-let` mapping — local `let` inside functions remains allowed, matching NASA's actual "global mutable state" intent rather than a blanket ban on `let`.

- **ASP204 (no unbounded loops):** NASA's rule requires loops to have a statically-determinable iteration bound (no `while(true)`). There is no off-the-shelf ESLint rule for that predicate, so the current implementation uses `functional/no-loop-statements` — which bans **all** loops, including bounded `for(let i=0; i<N; i++)`. This is a strict over-approximation chosen because it lands at `warn` and surfaces something useful. **To revisit:** replace with a custom `aspergillus/asp204-bounded-loops` rule that detects only unbounded loop patterns (`while(true)`, `for(;;)`, `while(condition)` where condition isn't statically bounded). Tracked under the next aspergillus TS milestone.

### Level 3 — Warning

| Rule   | Description                        | Python (Fixit)            | TypeScript                                       | Rust |
|--------|------------------------------------|---------------------------|--------------------------------------------------|------|
| ASP301 | Result types, no exceptions        | `RaiseInsteadOfResult`    | `functional/no-throw-statements`, neverthrow     | `Result<T, E>`; `clippy::unwrap_used`/`expect_used`/`panic` |
| ASP302 | No Optional/None returns           | `OptionalReturnType`      | `strictNullChecks` + neverthrow                  | No null in language |

### Levels 4–5 — Planned, not implemented

Contracts, property-based tests (L4), and formal verification (L5). See
`python/src/aspergillus/` for the fullest current implementation, and
this document's history for research pointers.

## I/O blocklist (ASP205/206)

Python's purity and FC/IS rules rely on a curated I/O blocklist (see
`python/src/aspergillus/io_blocklist.py`). Consumers extend it per-project
via `[tool.aspergillus] extra_io_functions`. TypeScript's equivalent is
encoded as architectural boundaries (`eslint-plugin-boundaries`) rather
than a name blocklist — `core/` is forbidden from importing I/O modules,
which is more precise than pattern-matching call sites.

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
