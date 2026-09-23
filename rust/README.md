# Aspergillus — Rust

A runnable Rust gate, plus reference clippy and Cargo lint configs.

## What's here

- `ast-grep-rules/` — the declarative ast-grep rules the gate runs. Each
  file names a rule id, a severity, and a `rule:` tree pattern; no file
  carries a `fix:` block, so the gate reports only and never rewrites code.
- `src/` — the `aspergillus-rust-gate` crate: loads the rules above with
  the `ast-grep-core`, `ast-grep-config` and `ast-grep-language` libraries
  (not the ast-grep CLI), runs the reference clippy lints over the same
  workspace, and prints every finding as `path:line: ASPnnn`.
- `configs/clippy.toml` — clippy thresholds (line count, complexity).
- `configs/cargo-lints.toml` — snippet to paste into consumer `Cargo.toml`.

## Adoption

1. Copy the `rust/` directory into the consumer repo (or depend on it by
   path), the same way `configs/clippy.toml` is adopted today. The gate
   reads `ast-grep-rules/` from beside its own `Cargo.toml`, so the rules
   travel with it either way.
2. Run the gate over the workspace: `cargo run --manifest-path
rust/Cargo.toml -- path/to/workspace` (default target: `.`). It exits
   0 with no blocking finding, non-zero with at least one.
3. Paste `configs/cargo-lints.toml` contents into the consumer's
   `Cargo.toml` under `[lints.clippy]`, and copy `configs/clippy.toml` to
   the consumer repo root, so a plain `cargo clippy` run (outside the
   gate) surfaces the same lints.

## Mapping

See `../docs/design.md` for the authoritative ASP ID ↔ per-language tool
mapping. Rust summary:

| ASP    | Tooling                                                           |
| ------ | ----------------------------------------------------------------- |
| ASP201 | `clippy::too_many_lines` (threshold 60), forced at `warn`         |
| ASP203 | `ast-grep-rules/asp203-no-static-mut.yml` (severity `error`)      |
| ASP204 | `ast-grep-rules/asp204-no-infinite-loop.yml` (severity `warning`) |
| ASP301 | `clippy::unwrap_used`/`expect_used`/`panic`, forced at `deny`     |

The gate treats a finding as blocking exactly when the underlying tool
reports it at `error` level: an ast-grep rule with `severity: error`, or a
clippy lint the gate forces to `deny`. `clippy::too_many_lines` stays at
`warn` until a dedicated PR promotes it, matching the TypeScript
severity-flip workflow.

ASP202 (assertion density) and ASP206 (functional core / imperative
shell) are not yet covered by a Rust check; see `../docs/design.md`.
