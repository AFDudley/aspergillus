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

- `check_asp_fsm_enum_dispatch.py` — ASP-FSM-EXHAUSTIVE (asp-26e): rejects
  if/elif dispatch on an Enum-typed subject unless it is a `match` statement
  or ends in `else: assert_never(subject)`. Fixture:
  `tests/fixtures/asp_fsm_enum_dispatch.py`.
- `check_asp_fsm_redundant_branches.py` — ASP-FSM-REDUNDANT (asp-5a8): warns
  when two branch bodies of a single Enum-typed `match`/if-elif dispatch have
  identical location- and comment-stripped (but not alpha-renamed) ASTs.
  Fixture: `tests/fixtures/asp_fsm_redundant.py`.
- `check_edge_duration.py` — ASP-FSM-EDGE-DURATION (asp-fef): rejects an FSM
  transition ("edge") body that embeds unbounded work (a direct
  LLM/subprocess call, a call into another state machine's run/drive
  entrypoint, or an unbounded retry loop) instead of emitting a durable
  marker and returning. See the module docstring for the edge-recognition
  heuristics and documented blind spots (indirection through a helper
  function defeats detection by design).
- `check_stringly_dispatch.py` — ASP-FSM-STRINGLY (asp-5be): reads source
  from stdin; warns when an if/elif or `match` dispatches on `==`
  string-literal comparisons that shadow a same-module `Enum`'s values, so
  the dispatch bypasses exhaustiveness checking. Silenced by a
  `# asp-fsm: boundary-parse` marker comment anywhere in the flagged
  function's body (for serialization-boundary parsers), and silent when no
Before producing the resolution I verified the actual numbering against the code, since both sides' prose contradicts each other:

- Main's code: `FsmStringlyDispatch` = **ASP411** (fd1.4) and `FsmRedundantBranches` = **ASP411** (fd1.3) — the collision is real and still unresolved on main; `FsmEdgeDuration` = ASP412.
- Branch `worker/asp-fd1-1` code/design.md/README: `FsmEnumDispatchExhaustive` = **ASP413** (commit 95ff94d: "renumber ASP411 -> ASP413 — sibling asp-fd1.4 merged first claiming ASP411").
- The branch's CLAUDE.md prose ("ASP412", "stringly = ASP413") contradicts its own code and is wrong; the merged text below corrects it to match the code.

```
  same-module Enum exists to shadow. Ported into the enforced fixit rule
  pack as ASP411 `FsmStringlyDispatch`
  (`python/src/aspergillus/rules/catalog/fsm_stringly_dispatch.py`,
  pebble asp-fd1.4); this script remains as the original standalone probe.
- `verify_fsm_enum_dispatch_lint.py` / `verify_fsm_enum_dispatch_pytest.py`
  (pebble asp-fd1.1) — behavioral oracle probes for `FsmEnumDispatchExhaustive`
  (ASP413, `python/src/aspergillus/rules/catalog/fsm_enum_dispatch_exhaustive.py`;
  authored as ASP411 on its worker branch, renumbered at merge because
  sibling asp-fd1.4 had already merged claiming ASP411 for
  `FsmStringlyDispatch`), the fixit/LibCST port of
  `check_asp_fsm_enum_dispatch.py` above. Drive the real
  `uv run --directory python fixit lint` / `pytest tests` CLIs as
  subprocesses rather than calling the rule in-process.
- `verify_fsm_redundant_branches_lint.py` / `verify_fsm_redundant_branches_pytest.py`
  (asp-fd1.3): NOT dependency-free like the checkers above — these
  deliberately shell out to `uv run --directory python fixit lint` / `pytest`
  to verify the ASP411 `FsmRedundantBranches` rule (ported from
  `check_asp_fsm_redundant_branches.py` into
  `python/src/aspergillus/rules/catalog/fsm_redundant_branches.py`) fires
  through the real, installed fixit CLI and repo `[tool.fixit]` config, not
  just via in-repo pytest fixtures.
```

Notes on the resolution:

- **Stringly = ASP411**, per the code on main — the branch's "ASP413" claim was speculative and never happened in code.
- **Enum-dispatch = ASP413** with the renumber rationale corrected to match commit 95ff94d (ASP411 → ASP413), not the branch prose's fabricated "ASP412 / renumbered from ASP413" story.
- Both verify-probe bullets kept (one per side's intent); the stray ``` ``` `` fence from main's side dropped — it's an artifact of the earlier fd1.3 merge, and main's file has an unbalanced fence pair (lines 37/61) that the second conflict's resolution should also drop.
- The ASP411 collision between `FsmStringlyDispatch` and `FsmRedundantBranches` **still exists in code on main**; the collision note in the second conflict region should be kept (updated: the suggested ASP413 target is now taken by `FsmEnumDispatchExhaustive`, so the renumber must pick ASP414+).
- `verify_fsm_stringly_dispatch_lint.py` — asp-fd1.4: arg-dispatched
  (`invalid` / `boundary_marker`); writes a fixture INSIDE `python/` (fixit's
  config discovery walks up from the file's own path, so a fixture outside
  the `python/` tree never sees `[tool.fixit] enable`) and runs the real
  `uv run --directory python fixit lint` CLI against it, emitting
  `{"reports_violation": bool}`.
- `verify_fsm_stringly_dispatch_pytest.py` — asp-fd1.4: runs the real
  `uv run --directory python pytest tests -q -rA` suite, emitting
  `{"exit_code": int, "mentions_rule": bool}` — `mentions_rule` confirms
ASP413's fixture-based tests ran as part of the full suite, not in
  isolation.
