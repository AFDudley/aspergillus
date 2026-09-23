# rust/src/

The `aspergillus-rust-gate` crate. Functional core / imperative shell split:

- `lib.rs` — the pure core. Given already-loaded ast-grep rules and an
  already-read source string, `source_findings` returns the findings a file
  carries; no file, process, or exit code appears here.
- `clippy.rs` — the imperative shell around `cargo clippy`: runs it as a
  subprocess, maps its lint codes to ASP ids (`FORCED_LINTS`), and turns its
  JSON diagnostics into `Finding`s.
- `duplicates.rs` — the pure core of the whole-workspace duplicate-function
  check. Given an already-read source string, `function_occurrences` walks
  its ast-grep parse tree and returns each function's type-2 normalized
  body; `duplicate_groups` buckets occurrences by that body across every
  scanned file; `findings_for_groups` renders a group as `ASP501` findings.
  No file, process, or exit code appears here.
- `workspace.rs` — the imperative shell shared by both binaries:
  `rust_source_files` walks a Cargo workspace's `*.rs` files, skipping
  `target/` and hidden directories.
- `bin/` — the CLI entry points; see `bin/CLAUDE.md`.

`bin/aspergillus_rust_gate.rs` calls `lib.rs`, `clippy.rs`, and
`workspace.rs`. `bin/aspergillus_rust_dup_check.rs` calls `duplicates.rs`
and `workspace.rs`. See each binary's own doc comment for how a consumer
runs it.
