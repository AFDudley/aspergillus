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
- `duplicate_types.rs` — the pure core of the whole-workspace duplicate-type
  check. Given an already-read source string and its crate id,
  `type_occurrences` walks its ast-grep parse tree and returns each struct
  or enum's declared name and shape fingerprint; `duplicate_groups` buckets
  occurrences by `(name, shape)` and keeps only a group spanning more than
  one crate; `apply_allowlist` drops a group whose type name is in an
  `--allowlist` file; `findings_for_groups` renders a group as `ASP502`
  findings. No file, process, or exit code appears here.
- `workspace.rs` — the imperative shell shared by every binary:
  `rust_source_files` walks a Cargo workspace's `*.rs` files, skipping
  `target/`, hidden directories, and any file whose workspace-relative
  path matches a `--exclude` glob; `crate_roots` walks the same tree for
  every directory holding a `Cargo.toml`, so the duplicate-type check can
  tell which crate a file belongs to. `take_excludes` extracts every
  `--exclude GLOB` pair from a binary's raw argument list, and
  `build_excludes` compiles the extracted patterns into a `GlobSet`
  (gitignore/fnmatch-style, e.g. `scripts/oracles/fixtures/**`) —
  pebble asp-f4c.
- `bin/` — the CLI entry points; see `bin/CLAUDE.md`.

`bin/aspergillus_rust_gate.rs` calls `lib.rs`, `clippy.rs`, and
`workspace.rs`. `bin/aspergillus_rust_dup_check.rs` calls `duplicates.rs`
and `workspace.rs`. `bin/aspergillus_rust_dup_type_check.rs` calls
`duplicate_types.rs` and `workspace.rs`. See each binary's own doc comment
for how a consumer runs it.
