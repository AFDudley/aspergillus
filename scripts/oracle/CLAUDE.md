# scripts/oracle/

Behavioral acceptance oracles for the Rust duplicate-type check (pebble
asp-ce6.4, `contracts/specs/derived-asp-ce6.4.spec.json`). Each script
builds the real `aspergillus-rust-dup-type-check` binary (`../../rust/`),
runs it over a throwaway synthetic workspace or the committed real-lobaria
fixture (`../../rust/fixtures/lobaria-a027fb9/`), and emits one
`stdout_json` observation (or, for the one metamorphic oracle, its own
exit code). A script judges nothing itself except where noted — the
linked spec's `then` clauses own the verdict.

This directory is named `scripts/oracle/` (singular), distinct from the
pre-existing `scripts/oracles/` (plural, pebble asp-ce6.1's gate oracles)
and the `scripts/asp_rust_dup_*` probes (pebble asp-ce6.3's
duplicate-function oracles) — the spec that names these paths fixed the
singular form.

- `lib_rust_dup_type_check.sh` — shared setup: locates the repo root,
  builds the check binary (`rust_dup_type_build`), resolves and copies the
  committed real-lobaria fixture (`rust_dup_type_lobaria_fixture`,
  `rust_dup_type_lobaria_copy`), writes a throwaway fixture crate
  (`rust_dup_type_write_crate`), and builds a PATH with named binaries
  (e.g. `python3`, `node`) truly absent rather than merely shadowed
  (`rust_dup_type_path_without`). Sourced by every other script here,
  never invoked directly.
- `cross_crate_scope.sh` — clause C1: a concept two DIFFERENT crates
  declare is reported; the same concept declared twice in ONE crate is
  not.
- `lobaria_nanos_findings.sh` — clause C2: the real `Nanos` duplicate
  reports at all three real lobaria locations.
- `lobaria_receipt_findings.sh` — clause C3: the real `Receipt` duplicate
  reports at all three real lobaria locations.
- `lobaria_name_only_types.sh` — clause C4: the real `Refused`, `Carried`,
  `Hit` and `Finding` names, which repeat without sharing a shape, are
  never reported.
- `finding_line_format.sh` — clause C5: every reported line reads as
  `path:line: ASPnnn`.
- `allowlist_suppresses_named_pair.sh` — clause C6 (metamorphic): adding
  `Nanos` to an `--allowlist` file between two runs drops only its
  findings and keeps every other finding unchanged. This oracle's own
  exit code is the verdict — the spec names no separate `then` clause for
  a metamorphic type.
- `no_files_modified.sh` — clause C7: running the check over a throwaway
  copy of the real-lobaria fixture leaves every file byte-identical
  afterward.
- `cargo_build_and_dependencies.sh` — clause C8: `cargo build` succeeds
  from a clean target directory, and `cargo tree` names all three
  `ast-grep-core`/`ast-grep-config`/`ast-grep-language` dependencies.
- `run_gate_without_python_and_node.sh` — clause C9: the check still
  reports findings with `python3` and `node` truly unresolvable on PATH.
- `python_and_typescript_rules_untouched.sh` — clause C10: `git diff
--name-only` against this pebble's recorded base commit names no file
  under a Python or TypeScript rules directory.
