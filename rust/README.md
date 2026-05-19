# Aspergillus — Rust

Reference clippy and Cargo lint configs. No custom dylint rules yet;
Rust support is placeholder-tier.

## What's here

- `configs/clippy.toml` — clippy thresholds (line count, complexity)
- `configs/cargo-lints.toml` — snippet to paste into consumer `Cargo.toml`

## Adoption

1. Copy `configs/clippy.toml` to the consumer repo root.
2. Paste `configs/cargo-lints.toml` contents into the consumer's
   `Cargo.toml` under `[lints.clippy]`.
3. Run `cargo clippy --all-targets --all-features -- -D warnings`.
4. For each clippy rule at `warn`, fix violations and flip to `deny` in a
   dedicated PR. Matches the TypeScript severity-flip workflow.

## Mapping

See `../docs/design.md` for the authoritative ASP ID ↔ per-language tool
mapping. Rust summary:

| ASP | Tooling |
|-----|---------|
| 201 | `clippy::too_many_lines` (threshold 60) |
| 202 | Manual (future: custom dylint rule) |
| 203 | Language (no safe `static mut`) |
| 204 | Manual (prefer iterators) |
| 205 | Module structure (pure `core.rs`, I/O modules separate) |
| 206 | Module structure |
| 301 | `clippy::unwrap_used`, `expect_used`, `panic`; `Result<T, E>` |
| 302 | No null in the language; `Option` used sparingly |

## Future

A custom dylint rule for ASP202 (assertion density) is planned. Not started.
