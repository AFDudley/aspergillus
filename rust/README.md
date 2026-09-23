# Aspergillus — Rust

A runnable Rust gate, plus reference clippy and Cargo lint configs.

## What's here

- `ast-grep-rules/` — the declarative ast-grep rules the gate runs. Each
  file names a rule id, a severity, and a `rule:` tree pattern; no file
  carries a `fix:` block, so the gate reports only and never rewrites code.
- `src/` — the `aspergillus-rust-gate` crate: loads the rules above with
  the `ast-grep-core`, `ast-grep-config` and `ast-grep-language` libraries
  (not the ast-grep CLI), runs the reference clippy lints over the same
  workspace, and prints every finding as `path:line: ASPnnn`. Also holds
  the whole-workspace duplicate-function (`ASP501`) and duplicate-type
  (`ASP502`) checks; see `src/CLAUDE.md`.
- `configs/clippy.toml` — clippy thresholds (line count, complexity).
- `configs/cargo-lints.toml` — snippet to paste into consumer `Cargo.toml`.
- `fixtures/lobaria-a027fb9/` — a verbatim, committed copy of the real
  `lobaria` files the duplicate-type check's acceptance oracles
  (`../scripts/oracle/`) run against; see its `PROVENANCE.md`.

## Adoption

1. Copy the `rust/` directory into the consumer repo (or depend on it by
   path), the same way `configs/clippy.toml` is adopted today. The gate
   reads `ast-grep-rules/` from beside its own `Cargo.toml`, so the rules
   travel with it either way.

   The crate's `Cargo.toml` declares an empty `[workspace]` table, so when
   `rust/` is vendored inside a consumer's own Cargo workspace, cargo treats
   it as its own workspace root rather than erroring that the package
   "believes it's in a workspace when it's not". No consumer-side change is
   needed; run its binaries directly with `--manifest-path rust/Cargo.toml`.

2. Run the gate over the workspace: `cargo run --manifest-path
rust/Cargo.toml -- path/to/workspace` (default target: `.`). It exits
   0 with no blocking finding, non-zero with at least one.
3. Paste `configs/cargo-lints.toml` contents into the consumer's
   `Cargo.toml` under `[lints.clippy]`, and copy `configs/clippy.toml` to
   the consumer repo root, so a plain `cargo clippy` run (outside the
   gate) surfaces the same lints.

## Mapping

See `../docs/rust-rules.md` for the full 27-rule ASP ID ↔ Rust
disposition table (every Level 2, Level 3 and ASP4xx rule), and
`../docs/design.md` for the cross-language summary. Checked rules —
the ones with a committed `../rust/fixtures/<ASPnnn>/{violating,satisfying}/`
fixture pair:

| ASP    | Tooling                                                                     |
| ------ | --------------------------------------------------------------------------- |
| ASP201 | `clippy::too_many_lines` (threshold 60), forced at `warn`                   |
| ASP202 | `src/purity.rs::assertion_density_findings` (gate check)                    |
| ASP204 | `ast-grep-rules/asp204-no-infinite-loop.yml` (severity `warning`)           |
| ASP205 | `src/purity.rs::impure_function_findings` (gate check)                      |
| ASP206 | `src/purity.rs::mixed_io_logic_findings` (gate check)                       |
| ASP301 | `clippy::unwrap_used`/`expect_used`/`panic`, forced at `deny`               |
| ASP403 | `clippy::redundant_closure`, forced at `warn`                               |
| ASP404 | `ast-grep-rules/asp404-redundant-conditional-bool.yml` (severity `warning`) |

ASP203 (no safe `static mut`), ASP302 (no `null`) and ASP413 (`match`
exhaustiveness) are language features: the compiler enforces them, so no
gate check runs. `ast-grep-rules/asp203-no-static-mut.yml` still flags a
`static mut` declaration as defense in depth.

The two whole-workspace checks run as their own binaries, not the gate:

| ASP    | Tooling                                                                                             |
| ------ | --------------------------------------------------------------------------------------------------- |
| ASP501 | `aspergillus-rust-dup-check` — whole-workspace duplicate-function check (`src/duplicates.rs`)       |
| ASP502 | `aspergillus-rust-dup-type-check` — whole-workspace duplicate-type check (`src/duplicate_types.rs`) |

`cargo run --manifest-path rust/Cargo.toml --bin aspergillus-rust-dup-type-check
-- path/to/workspace [--allowlist FILE]` (default target: `.`) runs
ASP502. Its acceptance is verified against the real `lobaria` workspace at
commit `a027fb9` — see `fixtures/lobaria-a027fb9/PROVENANCE.md` and
`../scripts/oracle/`.

The gate treats a finding as blocking exactly when the underlying tool
reports it at `error` level: an ast-grep rule with `severity: error`, a
clippy lint the gate forces to `deny`, or a gate check that returns
`blocking: true`. `clippy::too_many_lines` and `clippy::redundant_closure`
stay at `warn` until a dedicated PR promotes them, matching the
TypeScript severity-flip workflow.
