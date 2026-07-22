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
