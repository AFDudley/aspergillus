# scripts/

Standalone, dependency-free Python checkers invoked directly as
`python3 scripts/check_*.py` (stdin in, one JSON object on stdout). These are
not part of the `aspergillus` package or its `fixit`/`libcst` rule catalog
(`python/src/aspergillus/rules/`); they exist so a pebble's acceptance spec
can shell out to a fixed script path without depending on the package's
install state.

- `check_edge_duration.py` — ASP-FSM-EDGE-DURATION: rejects an FSM transition
  ("edge") body that embeds unbounded work (a direct LLM/subprocess call,
  a call into another state machine's run/drive entrypoint, or an unbounded
  retry loop) instead of emitting a durable marker and returning. See the
  module docstring for the edge-recognition heuristics and documented blind
  spots (indirection through a helper function defeats detection by design).
