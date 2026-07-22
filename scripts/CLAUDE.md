# scripts/

Standalone, dependency-free Python scripts invoked directly by `python3
scripts/<name>.py`, outside the `aspergillus` package under `python/`. Each
script reads source from stdin and prints one `stdout_json` object — the
shape a spec's `behavior` acceptance test observes.

- `check_stringly_dispatch.py` — ASP-FSM-STRINGLY: warns when an if/elif or
  `match` dispatches on `==` string-literal comparisons that shadow a
  same-module `Enum`'s values, so the dispatch bypasses exhaustiveness
  checking. Silenced by a `# asp-fsm: boundary-parse` marker comment
  anywhere in the flagged function's body (for serialization-boundary
  parsers), and silent when no same-module Enum exists to shadow.
