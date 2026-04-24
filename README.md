# aspergillus

NASA-grade code quality rules, applied across multiple languages.

Named after *Aspergillus nidulans*, the first fungus NASA intentionally
grew on the International Space Station.

## What it is

A rule set derived from NASA's Power of 10, ported to:

- **Python** — Fixit/LibCST rule-pack. Implements ASP201–206 (Level 2)
  and ASP301–302 (Level 3) as custom lint rules.
- **TypeScript** — reference ESLint/tsconfig/Prettier configs plus a
  stub `aspergillus-ts` CLI. Composes stock plugins; no custom rules.
- **Rust** — reference clippy/Cargo-lints configs. Placeholder tier.

See [`docs/design.md`](docs/design.md) for the full rule table and
per-language mappings.

## Repository layout

| Path | Contents |
|------|----------|
| `docs/` | Design, implementation notes, this repo's spec/plan history |
| `python/` | Python package, tests, pre-commit config |
| `typescript/` | Reference configs + stub CLI |
| `rust/` | Reference clippy/Cargo lint configs (placeholder) |

## Adoption

Consumers pull aspergillus as a git subtree and use the language
subtree(s) they need:

- Python — see `python/` (install via `uv tool install ./python`).
- TypeScript — see `typescript/README.md`.
- Rust — see `rust/README.md`.

## Levels

- **Level 1** — external tooling baseline (ruff, ESLint, clippy, …).
  Not aspergillus code; aspergillus ships reference configs only.
- **Level 2** — structural rules (ASP201–206). Blocking.
- **Level 3** — error-handling rules (ASP301–302). Blocking in strict
  adopters.
- **Level 4/5** — planned (contracts; formal verification). Not implemented.

See [`docs/design.md`](docs/design.md) for the authoritative rule table.
