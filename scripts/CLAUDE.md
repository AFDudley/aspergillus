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
