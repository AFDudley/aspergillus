# scripts/

Standalone, dependency-free acceptance probes invoked directly by the
exophial reducer as `<interpreter> <script> <args>` (some read source from
stdin instead) — see each pebble's linked
`contracts/specs/derived-*.spec.json`. These are not part of the
`aspergillus` package or its `fixit`/`libcst` rule catalog
(`python/src/aspergillus/rules/`); they run with the system interpreter, no
venv, so a pebble's acceptance spec can shell out to a fixed script path
without depending on the package's install state, and they use only the
standard library (`ast`, `json`, `sys`).

Each script emits exactly one `stdout_json` observation and judges nothing
itself — the linked spec's `then` clauses own the verdict.

The four original standalone ASP-FSM checker scripts have been retired:
their behavior now lives as real `LintRule`s in
`python/src/aspergillus/rules/catalog/` — `FsmEnumDispatchExhaustive`
(ASP413), `FsmRedundantBranches` (ASP411), `FsmEdgeDuration` (ASP412), and
`FsmStringlyDispatch` (ASP414) — enforced through the real `fixit lint` CLI
instead of an ad-hoc script no gate invoked (pebble asp-fd1.5).

- `verify_fsm_enum_dispatch_lint.py` / `verify_fsm_enum_dispatch_pytest.py`
  (pebble asp-fd1.1) — behavioral oracle probes for `FsmEnumDispatchExhaustive`
  (ASP413, `python/src/aspergillus/rules/catalog/fsm_enum_dispatch_exhaustive.py`).
  Drive the real `uv run --directory python fixit lint` / `pytest tests`
  CLIs as subprocesses rather than calling the rule in-process.
- `verify_fsm_redundant_branches_lint.py` / `verify_fsm_redundant_branches_pytest.py`
  (asp-fd1.3): shell out to `uv run --directory python fixit lint` / `pytest`
  to verify the ASP411 `FsmRedundantBranches` rule
  (`python/src/aspergillus/rules/catalog/fsm_redundant_branches.py`) fires
  through the real, installed fixit CLI and repo `[tool.fixit]` config, not
  just via in-repo pytest fixtures.
- `verify_fsm_stringly_dispatch_lint.py` — asp-fd1.4: arg-dispatched
  (`invalid` / `boundary_marker`); writes a fixture INSIDE `python/` (fixit's
  config discovery walks up from the file's own path, so a fixture outside
  the `python/` tree never sees `[tool.fixit] enable`) and runs the real
  `uv run --directory python fixit lint` CLI against it, emitting
  `{"reports_violation": bool}` for the ASP414 `FsmStringlyDispatch` rule.
- `verify_fsm_stringly_dispatch_pytest.py` — asp-fd1.4: runs the real
  `uv run --directory python pytest tests -q -rA` suite, emitting
  `{"exit_code": int, "mentions_rule": bool}` — `mentions_rule` confirms
  ASP414's fixture-based tests ran as part of the full suite, not in
  isolation.
- `run_fixit_edge_duration_fixture.sh` (pebble asp-fd1.2) — behavioral oracle
  for `FsmEdgeDuration` (ASP412): runs the real `fixit lint` CLI against a
  fixture containing the disallowed edge-duration shape, emitting one
  `stdout_json` object.
- `verify_readme_rule_table.py` / `verify_design_doc_rule_table.py` /
  `verify_asp4xx_numbers_unique.py` (pebble asp-fd1.5) — documentation-
  consistency probes: confirm README.md / docs/design.md name all four
  ASP-FSM rules next to a distinct rule number, and that no ASP4xx number is
  claimed by more than one rule anywhere in the rule source or docs.
- `lib_rust_dup_check.sh` (pebble asp-ce6.3) — shared setup sourced by the
  `asp_rust_dup_*` probes below: builds the `aspergillus-rust-dup-check`
  binary (`rust/`) and writes throwaway fixture crates. Judges nothing
  itself.
- `asp_rust_dup_cross_crate_probe.sh` / `asp_rust_dup_detect_probe.sh` /
  `asp_rust_dup_clean_probe.sh` / `asp_rust_dup_format_probe.sh` /
  `asp_rust_dup_readonly_probe.sh` / `asp_rust_dup_cargo_deps_probe.sh` /
  `asp_rust_dup_no_python_no_node_probe.sh` (pebble asp-ce6.3) — behavioral
  oracle probes for the Rust whole-workspace duplicate-function check
  (`rust/src/duplicates.rs`, `rust/src/bin/aspergillus_rust_dup_check.rs`).
  Each drives the real `cargo build`/`cargo run` and emits one
  `stdout_json` observation.
- `asp_python_duplicates_regression_probe.sh` (pebble asp-ce6.3) — confirms
  the existing `aspergillus check-duplicates` Python CLI still reports a
  duplicate group, so the new Rust check did not disturb it.
- `lib_rust_exclude.sh` (pebble asp-f4c) — shared setup for the
  `rust_exclude_*` probes below: builds all three check binaries
  (`rust_exclude_build_all`) and writes the shared throwaway four-crate
  fixture (`rust_exclude_write_layered_fixture`): `kept-a`/`kept-b`
  declare a duplicated `Marker` type, a duplicated `AllowMe` enum, a
  duplicated function body, and a blocking `static mut`, never excluded
  by any probe; `alpha/dup`/`beta/dup` declare `Marker` and the function
  body again, each under its own glob-excludable subtree. Sourced by
  every `rust_exclude_*` probe except the two `lobaria_shape` ones, never
  invoked directly.
- `rust_exclude_flag_accepted_probe.sh` (clause C1) — all three binaries
  accept `--exclude` given twice and run to completion (exit 0 or 1,
  never the argument-parse-error code 2).
- `rust_exclude_two_crate_fixture_probe.sh` (clause C2) — run with
  `--exclude 'alpha/**'`, all three binaries still report the `Marker`/
  duplicate-function/`static mut` finding from `kept-a`, `kept-b` or
  `beta/dup`, and none from `alpha/`.
- `rust_exclude_union_probe.sh` (clause C3) — `aspergillus-rust-dup-type-check`
  run with `--exclude 'alpha/**' --exclude 'beta/**'` reports nothing
  from either folder and still reports `Marker` from `kept-a`/`kept-b`.
- `rust_exclude_allowlist_coexist_probe.sh` (clause C6) — one run of
  `aspergillus-rust-dup-type-check` with both `--allowlist` (naming
  `AllowMe`) and `--exclude 'alpha/**'` suppresses `AllowMe` by name,
  suppresses `alpha/` by path, and still reports `Marker`.
- `rust_exclude_no_write_probe.sh` (clause C8) — checksums the fixture
  before and after a `--exclude` run; nothing changes, and the run still
  prints findings.
- `rust_exclude_conservation_relation.py` (clause C7, metamorphic) —
  builds a throwaway three-crate fixture in Python, runs
  `aspergillus-rust-dup-type-check` with and without `--exclude 'alpha/**'`,
  and prints `{"flows": [without, -with, -under_excluded]}`; the linked
  spec's conservation relation requires this list sum to zero.
- `lib_rust_exclude_lobaria_shape.sh` / `rust_exclude_lobaria_shape_probe.sh`
  (clause C4) / `rust_exclude_lobaria_shape_default_probe.sh` (clause C5)
  — behavioral oracle probes for the request's consumer demonstration:
  the committed synthetic fixture `rust/fixtures/lobaria-exclude-shape/`
  (see its `PROVENANCE.md`) reproduces a `statechart/src/chart.rs`
  declaring `Owed`/`Hole` and a `scripts/oracles/fixtures/` subtree
  redeclaring them, alongside five production duplicate concepts
  (`Bps`, `SignedLamports`, `TrajectoryRow`, `Cut`, `Run`) that cross the
  `statechart`/`pump-strategy` crate boundary and are never excluded.
  Each probe locates a concept's declaration line by grepping the
  committed fixture rather than a hardcoded line number, so an edit to
  the fixture cannot silently desync the oracle from it.
- `oracle_type1_semantics.py` / `oracle_type1_report_fields.py` /
  `oracle_type1_boilerplate_exclusion.py` / `oracle_type1_editing_scenarios.py`
  (pebble asp-d88.1) — behavioral oracle probes for type-1 (exact) clone
  detection (`python/src/aspergillus/duplicates.py`:
  `find_type1_duplicate_groups`, `is_boilerplate`). Each reads a JSON
  object of function-source pairs from stdin, drives a child `python3`
  inside the project's uv-managed environment (`uv run --directory
python`) since the real detector needs the installed `libcst`
  dependency, and emits one `stdout_json` observation.
