# rust/src/

The `aspergillus-rust-gate` crate. Functional core / imperative shell split:

- `lib.rs` — the pure core. Given already-loaded ast-grep rules and an
  already-read source string, `source_findings` returns the findings a file
  carries; no file, process, or exit code appears here.
- `clippy.rs` — the imperative shell around `cargo clippy`: runs it as a
  subprocess, maps its lint codes to ASP ids (`FORCED_LINTS`), and turns its
  JSON diagnostics into `Finding`s.
- `bin/` — the CLI entry point; see `bin/CLAUDE.md`.

The CLI (`bin/aspergillus_rust_gate.rs`) is the only caller of both modules;
see its own doc comment for how a consumer runs the gate.
