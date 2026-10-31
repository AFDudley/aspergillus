# scripts/oracles/

Behavioral acceptance probes for the Aspergillus Rust gate (pebble
asp-ce6.1, `contracts/specs/derived-asp-ce6.1.spec.json`). Each script
builds the real `aspergillus-rust-gate` crate (`../../rust/`), writes a
throwaway fixture Cargo package under a temp directory, runs the real
binary over it, and emits one `stdout_json` observation. A script judges
nothing itself — the linked spec's `then` clauses own the verdict.

- `lib_rust_gate.sh` — shared setup: locates the repo root, builds the
  gate binary (`rust_gate_build`), and writes fixture workspaces
  (`rust_gate_write_fixture` plus three fixed source bodies: clean, a
  blocking `static mut` + `.unwrap()`, and a clippy-only `.expect()`).
  Sourced by every other script here, never invoked directly.
- `rust_gate_runs_over_cargo_workspace.sh` — clause C1: the gate runs via
  `cargo run` and reads the workspace's source files.
- `rust_gate_finding_line_format.sh` — clause C2: every reported line
  reads as `path:line: ASPnnn`.
- `rust_gate_blocking_finding_fails_run.sh` — clause C3: a blocking
  finding (ASP203 or ASP301) makes the run exit non-zero.
- `rust_gate_clean_workspace_passes.sh` — clause C4: no violation, no
  finding, exit 0.
- `rust_gate_runs_without_python_or_node.sh` — clause C5: the gate still
  finds and reports with python/python3/node/npm/npx stripped from PATH.
- `rust_gate_reports_clippy_findings.sh` — clause C8: a clippy-only
  violation (`.expect(...)`, no ast-grep-matched construct) is reported.
- `rust_gate_does_not_modify_sources.sh` — clause C9: the fixture's
  `Cargo.toml` and `src/lib.rs` are byte-identical before and after the
  run (build byproducts like `target/` and a generated `Cargo.lock` are
  excluded — they are cargo's own, not a rewrite of the consumer's code).
- `python_and_typescript_rules_still_pass.sh` — clause C12: the existing
  Python (`uv run --directory python pytest tests -q`) and TypeScript
  (`bun test typescript/rules typescript/layouts typescript/errors`)
  suites both still pass, unaffected by the Rust gate addition.
