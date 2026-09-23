# rust/src/bin/

`aspergillus_rust_gate.rs` — the `aspergillus-rust-gate` binary's CLI: the
imperative shell. Loads the ast-grep rules from `../../ast-grep-rules/`
(resolved at compile time via `CARGO_MANIFEST_DIR`), walks the target
workspace's `*.rs` files, calls `aspergillus_rust_gate::source_findings`
(the pure core in `../lib.rs`) and `aspergillus_rust_gate::clippy::clippy_findings`
(the clippy shell in `../clippy.rs`), prints every finding as
`path:line: ASPnnn`, and exits non-zero when a blocking finding exists.

Usage: `cargo run --manifest-path rust/Cargo.toml -- [WORKSPACE_DIR]`
(default: `.`).
