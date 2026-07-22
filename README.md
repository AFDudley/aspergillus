# aspergillus

NASA-grade code quality rules, applied across multiple languages.

Named after _Aspergillus nidulans_, the first fungus NASA intentionally
grew on the International Space Station.

## What it is

A rule set derived from NASA's Power of 10, ported to:

- **Python** — Fixit/LibCST rule-pack. Implements ASP201–206 (Level 2)
  and ASP301–304 (Level 3) as custom lint rules.
- **TypeScript** — reference ESLint/tsconfig/Prettier configs plus a
  stub `aspergillus-ts` CLI. Composes stock plugins; no custom rules.
- **Rust** — reference clippy/Cargo-lints configs. Placeholder tier.

See [`docs/design.md`](docs/design.md) for the full per-language
rule-mapping table.

## The rules at a glance

### Level 2 — structural (blocking)

- **ASP201 — Functions stay under 60 lines.** Long functions hide bugs
  and resist change; the 60-line ceiling forces decomposition into
  units a reader can hold in their head at once.
- **ASP202 — At least 2 assertions per function.** Assertions catch
  contract violations at the point of failure, before bad state
  propagates into downstream data corruption or silent wrong answers.
- **ASP203 — No global mutable state.** Modules stay testable in
  isolation — no more "this test passed until I changed an unrelated
  module." Eliminates whole classes of non-deterministic bugs.
- **ASP204 — No unbounded loops.** Every loop must have a provable
  termination bound. You cannot accidentally ship an infinite loop
  into production or a runaway retry loop into an outage.
- **ASP205 — No impure functions in core code.** Business logic is
  testable without mocks, stubs, or fixtures; I/O is concentrated at
  the edges of the system where it belongs.
- **ASP206 — Functional core, imperative shell.** Side effects live at
  the boundary. The core is pure and deterministic — same input always
  produces the same output, so it behaves identically in tests and
  production.

### Level 3 — error handling (blocking for strict adopters)

- **ASP301 — Results, not exceptions.** Error paths appear in function
  signatures via `Result<T, E>` / `neverthrow` / similar. No hidden
  control-flow jumps; callers cannot forget to handle a failure.
  _Retired for Python_ (pebble asp-80c): Python has no ergonomic
  `Result`, so an idiomatic guard-raise-then-return clause is correct
  standard code, not an antipattern — the rule only manufactured
  function-splitting ceremony. Still enforced in Rust (`clippy::panic`)
  and TypeScript (`no-throw` + neverthrow), which have ergonomic
  `Result` types. See `docs/design.md` § "Python Level 3 — ASP301
  retired".
- **ASP302 — No `Optional` / `None` / `null` returns.** Force callers
  to handle "not there" explicitly — no silent `NoneType has no
attribute …` crashes three layers down the call stack.
- **ASP303 — No error swallowed into a success sentinel.** A `return []`
  / `{}` / `""` from an `except` handler in a success-typed function
  conflates "the operation failed" with "it succeeded and produced
  nothing." Make the failure explicit (a `Result`), don't hide it in an
  empty value.
- **ASP304 — A surfaced failure must carry its captured evidence.** A
  failure message built from a process/gate `returncode` while the
  captured `.stdout` / `.stderr` / `.output` / `.report` is in scope and
  discarded gives the operator a one-bit summary of a cause that was
  captured and thrown away. Surface the evidence, not just the code.

### Level 4/5 — planned, not implemented

Contracts and property-based tests (L4), formal verification via SMT
solvers (L5). Applied selectively to safety-critical or financial
logic.

## Repository layout

| Path          | Contents                                          |
| ------------- | ------------------------------------------------- |
| `docs/`       | Design, implementation notes, spec/plan history   |
| `python/`     | Python package, tests, pre-commit config          |
| `typescript/` | Reference configs + stub CLI                      |
| `rust/`       | Reference clippy/Cargo lint configs (placeholder) |

## Adoption

Consumers pull aspergillus as a git subtree and use the language
subtree(s) they need:

- **Python** — see `python/` (install via `uv tool install ./python`).
- **TypeScript** — see [`typescript/README.md`](typescript/README.md).
- **Rust** — see [`rust/README.md`](rust/README.md).

## Levels

- **Level 1** — external tooling baseline (ruff, ESLint, clippy, …).
  Not aspergillus code; aspergillus ships reference configs only.
- **Level 2** — structural rules (ASP201–206). Blocking.
- **Level 3** — error-handling rules (ASP302–304; ASP301 retired for
  Python, still active in Rust/TypeScript). Blocking in strict adopters.
- **Level 4/5** — planned (contracts; formal verification). Not implemented.

See [`docs/design.md`](docs/design.md) for the authoritative
per-language rule-mapping table.
