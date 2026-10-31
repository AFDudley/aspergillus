# rust/src/bin/

`aspergillus_rust_gate.rs` — the `aspergillus-rust-gate` binary's CLI: the
imperative shell. Loads the ast-grep rules from `../../ast-grep-rules/`
(resolved at compile time via `CARGO_MANIFEST_DIR`), walks the target
workspace's `*.rs` files via `aspergillus_rust_gate::workspace::rust_source_files`
(`../workspace.rs`), calls `aspergillus_rust_gate::source_findings`
(the pure core in `../lib.rs`) and `aspergillus_rust_gate::clippy::clippy_findings`
(the clippy shell in `../clippy.rs`), prints every finding as
`path:line: ASPnnn`, and exits non-zero when a blocking finding exists.

Usage: `cargo run --manifest-path rust/Cargo.toml -- [WORKSPACE_DIR]
[--core-config FILE]` (default workspace: `.`). `--core-config` names the
consumer's functional-core declaration file directly; when absent, the
gate looks for `WORKSPACE_DIR/aspergillus.toml` and, failing that, treats
the workspace as having no declared core (ASP205/ASP206 then report
nothing — `../core_declaration.rs`).

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
aspergillus-rust-dup-type-check -- [WORKSPACE_DIR] [--allowlist FILE]
[--exclude GLOB]...` (default workspace: `.`).

Every one of the three binaries above also accepts a repeatable
`--exclude GLOB` flag (pebble asp-f4c): each calls
`workspace::take_excludes` on its raw arguments before its own flag
parsing, then `workspace::build_excludes` to compile the extracted
patterns, then passes the result to `workspace::rust_source_files` so a
file whose workspace-relative path matches a glob is never read. A file
the binary never reads produces no finding from it, and — since a
duplicate group's members come only from scanned files — a concept whose
only OTHER declaration sat under an excluded path stops being a
cross-crate duplicate at all, not just an unreported one.
`aspergillus_rust_gate.rs` additionally filters `clippy::clippy_findings`'s
result by the same excludes after the fact, since `cargo clippy` compiles
the whole workspace regardless of which files the file walker skips.
