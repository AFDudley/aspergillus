# scripts/

Standalone, dependency-free acceptance probes invoked directly by the
exophial reducer as `<interpreter> <script> <args>` — see each pebble's
linked `contracts/specs/derived-*.spec.json`. These are not part of the
`python/src/aspergillus` package; they run with the system interpreter, no
venv, so they use only the standard library (`ast`, `json`, `sys`).

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
