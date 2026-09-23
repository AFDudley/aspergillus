# Fixture provenance

Every `.rs` file under this directory is a verbatim, unedited copy of the
named path from the `lobaria` repository at commit `a027fb9`, the real
reference corpus pebble asp-ce6.4 names. Each file sits at the same
relative path (`<crate>/src/...`) it holds in the real lobaria workspace,
so the duplicate-type check's reported paths match the pebble's stated
acceptance exactly.

Each `Cargo.toml` here is new: a minimal package manifest naming the
crate, not copied from lobaria. This is a fixture for a check that parses
`.rs` files and reads `Cargo.toml` locations to assign a crate id; it is
not built with `cargo build` and does not need to compile.

Source paths, real repository, real commit:

- `statechart/src/units.rs` — declares `Nanos` (real line 251).
- `statechart/src/edge.rs` — declares `Receipt` (real line 26).
- `statechart/src/chart.rs` — declares `Refused` as a unit struct (real
  line 86), inside `pub mod event`.
- `pump-strategy/src/units.rs` — declares `Nanos` (real line 167) and
  `Receipt` (real line 188).
- `hold-time-curve/src/input.rs` — declares `Receipt` (real line 22) and
  `Nanos` (real line 28).
- `chart/src/generate.rs` — declares `Refused` as an enum with a
  different variant set than `shell/src/drive.rs`'s `Refused`.
- `chart/src/vocabulary_io.rs` — declares `Finding` and `Hit`.
- `chart/src/contract.rs` — declares `Carried` with different field names
  than `backtest/src/simulate.rs`'s `Carried`.
- `shell/src/drive.rs` — declares `Refused` as an enum with a different
  variant set than `chart/src/generate.rs`'s `Refused`.
- `backtest/src/simulate.rs` — declares `Carried` with different field
  names than `chart/src/contract.rs`'s `Carried`.

`Nanos` and `Receipt` are the two concepts the check must report: each
name's three declarations share a name and, despite differing field type
and visibility, the same shape (a one-field tuple struct), across three
different crates. `Refused`, `Carried`, `Hit` and `Finding` are the four
concepts the check must NOT report: each shares a name across more than
one file, but `Refused` and `Carried` differ in shape (variant names,
field names) wherever they cross a crate boundary, and `Hit` and
`Finding` never leave the `chart` crate at all in this fixture slice.
