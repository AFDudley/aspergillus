# rust/src/bin/

`aspergillus_rust_gate.rs` — the `aspergillus-rust-gate` binary's CLI: the
imperative shell. Loads the ast-grep rules from `../../ast-grep-rules/`
(resolved at compile time via `CARGO_MANIFEST_DIR`), walks the target
workspace's `*.rs` files via `aspergillus_rust_gate::workspace::rust_source_files`
(`../workspace.rs`), calls `aspergillus_rust_gate::source_findings`
(the pure core in `../lib.rs`) and `aspergillus_rust_gate::clippy::clippy_findings`
(the clippy shell in `../clippy.rs`), prints every finding as
`path:line: ASPnnn`, and exits non-zero when a blocking finding exists.

Usage: `cargo run --manifest-path rust/Cargo.toml -- [WORKSPACE_DIR]`
(default: `.`).

`aspergillus_rust_dup_check.rs` — the `aspergillus-rust-dup-check` binary's
CLI: the imperative shell for the whole-workspace duplicate-function check.
Walks the target workspace's `*.rs` files via the same
`rust_source_files`, calls `aspergillus_rust_gate::duplicates::function_occurrences`
and `duplicate_groups` (the pure core in `../duplicates.rs`) to find every
pair of functions with an identical type-2 normalized body across every
crate, prints each one as `path:line: ASP501`, and exits non-zero when it
reports a finding. Report-only: it never rewrites a scanned file.

Usage: `cargo run --manifest-path rust/Cargo.toml --bin
aspergillus-rust-dup-check -- [WORKSPACE_DIR]` (default: `.`).

`aspergillus_rust_dup_type_check.rs` — the `aspergillus-rust-dup-type-check`
binary's CLI: the imperative shell for the whole-workspace duplicate-type
check. Walks the target workspace's `*.rs` files and crate roots via
`rust_source_files`/`crate_roots` (`../workspace.rs`), calls
`aspergillus_rust_gate::duplicate_types::type_occurrences` and
`duplicate_groups` (the pure core in `../duplicate_types.rs`) to find
every struct or enum concept declared under the same name and shape in
more than one crate, drops any pair an `--allowlist FILE` names, prints
each occurrence as `path:line: ASP502`, and exits non-zero when it reports
a finding. Report-only: it never rewrites a scanned file.

Usage: `cargo run --manifest-path rust/Cargo.toml --bin
aspergillus-rust-dup-type-check -- [WORKSPACE_DIR] [--allowlist FILE]`
(default workspace: `.`).
