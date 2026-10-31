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
   resolves its rule directory at run time — either an explicit `--rules <dir>`
   argument, or the `CARGO_MANIFEST_DIR` environment variable (set by `cargo
run`). It never falls back to a compiled-in path, so a binary built from
   one checkout and run from another reads the right `ast-grep-rules/`
   directory.

   The crate's `Cargo.toml` declares an empty `[workspace]` table, so when
   `rust/` is vendored inside a consumer's own Cargo workspace, cargo treats
   it as its own workspace root rather than erroring that the package
   "believes it's in a workspace when it's not". No consumer-side change is
   needed; run its binaries directly with `--manifest-path rust/Cargo.toml`.

2. Run the gate over the workspace: `cargo run --manifest-path
rust/Cargo.toml -- path/to/workspace [--rules DIR]` (default target: `.`).
   The gate resolves its rule directory at run time — the `--rules` argument
   or `CARGO_MANIFEST_DIR` (set by `cargo run`) — never a compiled-in path.
   It exits 0 with no blocking finding, non-zero with at least one.
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

| ASP    | Tooling                                                                   |
| ------ | ------------------------------------------------------------------------- |
| ASP201 | `clippy::too_many_lines` (threshold 60), forced at `warn`, blocking       |
| ASP202 | `src/purity.rs::assertion_density_findings` (gate check)                  |
| ASP204 | `ast-grep-rules/asp204-no-infinite-loop.yml` (severity `error`)           |
| ASP205 | `src/purity.rs::impure_function_findings` (gate check)                    |
| ASP206 | `src/purity.rs::mixed_io_logic_findings` (gate check)                     |
| ASP301 | `clippy::unwrap_used`/`expect_used`/`panic`, forced at `warn`, blocking   |
| ASP403 | `clippy::redundant_closure`, forced at `warn`, blocking                   |
| ASP404 | `ast-grep-rules/asp404-redundant-conditional-bool.yml` (severity `error`) |

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

The gate treats a finding as blocking exactly when the rule is a blocking
rule: an ast-grep rule with `severity: error`, a gate check that returns
`blocking: true`, or a clippy-backed rule (all five block). Every Aspergillus
Rust rule reports as blocking, so a gate run with any finding exits non-zero.

## Clippy-backed rules: determinism and the test exemption

Five rules are backed by clippy lints run over the same workspace —
ASP201 (`too_many_lines`), ASP301 (`unwrap`/`expect`/`panic`), ASP303
(`let_underscore_must_use`/`unused_must_use`), ASP403 (`redundant_closure`)
and ASP413 (`wildcard_enum_match_arm`). `src/clippy.rs` forces each lint at
`-W` (warn), never `-D` (deny), and assigns the finding its blocking
severity itself rather than reading clippy's emitted level.

Warn — not deny — is what makes the gate's clippy counts DETERMINISTIC and
COMPLETE across a cold, warm or already-checked target dir:

- A denied lint is emitted as an `error`, which fails the crate's build.
  cargo then never checks the crates that depend on it, so their findings
  vanish — a cold run reports FEWER clippy findings than a warm one. At
  `warn` every crate compiles, so every crate (and everything downstream of
  it) is checked and reports.
- cargo caches a compilation unit's warnings and REPLAYS them, verbatim in
  the JSON stream, whenever the unit is unchanged; it does not replay a
  build error. So at `warn` a warm or repeated run re-emits exactly the
  diagnostics a cold run produced, and the counts are identical run to run.

The cost is a full clippy CHECK of every workspace crate the first time the
gate runs against a given target dir (a denied cascade would have stopped
at the first violating crate). That is a `cargo clippy --all-targets` check,
not a codegen build, and it reuses the target dir's cached dependency
artifacts; every subsequent run against that dir is a fast warning REPLAY.
No separate gate-owned target dir, source `touch`, or per-run `RUSTFLAGS`
churn is needed — cargo's own warning cache carries the determinism.

The five clippy-backed rules get the SAME test-code exemption the AST
analyzers apply (ASP202/ASP206): a finding under a `tests/` path, in a
`#[test]` function, or in a `#[cfg(test)]` module is test infrastructure,
not shipped debt, and is dropped. The gate applies it in
`is_clippy_test_exempt` (`src/bin/aspergillus_rust_gate.rs`), reusing
`is_test_path` for the path component and `anti_special_casing::line_in_test_scope`
for the `#[test]`/`#[cfg(test)]` scope.
