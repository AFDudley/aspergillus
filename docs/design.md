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

| Rule   | Description                              | Python (Fixit)                   | TypeScript                              | Rust |
|--------|------------------------------------------|----------------------------------|-----------------------------------------|------|
| ASP201 | Function ≤ 60 lines                      | `FunctionTooLong`                | `max-lines-per-function`                | `clippy::too_many_lines` |
| ASP202 | Assertion density ≥ 2 per function       | `LowAssertionDensity`            | Manual (code review)                    | Manual (planned dylint rule) |
| ASP203 | No global mutable state                  | `GlobalMutableState`             | `functional/no-let`, `immutable-data`   | Language (no safe `static mut`) |
| ASP204 | No unbounded loops                       | `UnboundedLoop`                  | `functional/no-loop-statements`         | Manual (prefer iterators) |
| ASP205 | No impure functions outside I/O boundary | `ImpureFunction`                 | `eslint-plugin-boundaries`              | Module structure (pure core) |
| ASP206 | Functional core / imperative shell       | `MixedIOAndLogic`                | `eslint-plugin-boundaries`              | Module structure |

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

### Phase 1 — Subtree (current)

Consumers pull aspergillus as a git subtree at `vendor/aspergillus/`:

```bash
git subtree add --prefix vendor/aspergillus <repo-url> main --squash
```

- **Python consumer:** `uv tool install ./vendor/aspergillus/python`; set
  `[tool.fixit] enable = ["aspergillus.rules"]` in `pyproject.toml`.
- **TypeScript consumer:** build the CLI (`cd vendor/aspergillus/typescript/cli && bun install && bun run build`),
  run `node vendor/aspergillus/typescript/cli/dist/index.js init`,
  install printed devDependencies.
- **Rust consumer:** copy `vendor/aspergillus/rust/configs/clippy.toml` to
  repo root; paste `cargo-lints.toml` into `Cargo.toml`.

Updates: `git subtree pull --prefix vendor/aspergillus <repo-url> main --squash`.

### Phase 2 — Published packages (planned)

Once the reference configs stabilize across 3+ consumer repos:

- Python: already publishable from `python/` (uv, PyPI or private index).
- TypeScript: publish `@afdudley/eslint-config`, `@afdudley/tsconfig`,
  `@afdudley/prettier-config`, `@afdudley/aspergillus-ts` to
  GitHub Packages. Consumer config collapses to one-line `extends:`.
- Rust: publish a proc-macro crate or cargo-template (TBD) for cargo-lints
  injection.

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
