# Fixture provenance

Every `.rs` file under this directory is a verbatim, unedited copy of the
named path from the `lobaria` repository at commit `d0269c7` — the
commit the pebble's 2026-09-23 verification (cloud agents
`VerifyASP205_206`, `VerifyLobariaGate`) names. Each file sits at the
same relative path (`<crate>/src/...`) it holds in the real lobaria
workspace, so a reported line number matches the pebble's stated
acceptance exactly. Each `Cargo.toml` here is new: a minimal package
manifest naming the crate, not copied from lobaria. This is a fixture
for a gate that parses `.rs` files; it is not built with `cargo build`
and does not need to compile.

`aspergillus.toml` here is lobaria's own functional-core declaration for
this pebble's acceptance check: `statechart/**` is lobaria's pure core,
the rest is its imperative shell.

Source paths, real repository, real commit `d0269c7`:

- `shell/src/machine.rs` — `create` (real line 990) calls `rc::create`
  and `fire::create`: domain constructors in the `rc`/`fire` modules, not
  filesystem or process I/O. A bare-name I/O match reported this as
  ASP205 before this pebble's fix.
- `shell/src/capture.rs` — `decode_worker` (real line 506) calls
  `queue.recv()` and `results.send(..)` on an `std::sync::mpsc`
  `Receiver`/`SyncSender`: thread-internal message passing, not I/O. A
  bare-name I/O match reported this as ASP205 before this pebble's fix.
- `backtest/src/replay.rs` — `open_tokens` (real line 223) calls
  `book.open()` on an in-memory `Book`: a domain method, not a
  filesystem open. A bare-name I/O match reported this as ASP205 before
  this pebble's fix.
- `chart/src/lib.rs` — `load` (real line 52) calls `json5::read(text)`
  over a `&str`: a parse of already-in-memory text, not I/O. A bare-name
  I/O match reported this as ASP205 before this pebble's fix.
- `statechart/src/chart.rs`, `statechart/src/edge.rs`,
  `statechart/src/units.rs` — lobaria's pure functional core (no I/O
  anywhere in these files), the same three files
  `rust/fixtures/lobaria-a027fb9/statechart/` already carries verbatim
  for the duplicate-type check (pebble asp-ce6.4); byte-identical at
  `d0269c7` (`git diff a027fb9 d0269c7 -- statechart/src/{chart,edge,units}.rs`
  is empty), copied again here so this pebble's own fixture is
  self-contained.
