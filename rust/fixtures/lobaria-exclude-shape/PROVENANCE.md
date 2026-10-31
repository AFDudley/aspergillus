# Fixture provenance

Every file under this directory is SYNTHETIC, written for pebble asp-f4c.
Unlike `rust/fixtures/lobaria-a027fb9/` (a verbatim copy of real lobaria
source), no file here is copied from the real lobaria repository. The
directory reproduces the SHAPE of the scenario asp-f4c's request names —
a `statechart/src/chart.rs` declaring `Owed` and `Hole`, and a
`scripts/oracles/fixtures/` subtree redeclaring the same two concepts as
lobaria's own gate fixtures do — without depending on network or
filesystem access to the real lobaria repository.

Layout:

- `statechart/src/units.rs`, `pump-strategy/src/units.rs` — each declares
  `Bps`, `SignedLamports`, `TrajectoryRow`, `Cut` and `Run` with the same
  shape (a struct's field-name list or an enum's variant-name list, per
  `rust/src/duplicate_types.rs`). These five names cross the
  `statechart`/`pump-strategy` crate boundary, so the duplicate-type check
  reports all five whether or not `--exclude` is given: this is the
  request's "five production duplicate concepts."
- `statechart/src/chart.rs` — declares `Owed` (a unit struct) and `Hole`
  (an enum with `Derived`/`Owed` variants), production code, never
  excluded.
- `scripts/oracles/fixtures/dup/owed_hole.rs` — redeclares `Owed` and
  `Hole` with the identical shape. This is the concepts' ONLY OTHER
  declaration: with no `--exclude`, the duplicate-type check reports both
  the `statechart/src/chart.rs` and the `scripts/oracles/fixtures/...`
  copies; with `--exclude 'scripts/oracles/fixtures/**'`, this file is
  never scanned, so `Owed` and `Hole` each keep only their
  `statechart/src/chart.rs` declaration — no longer a cross-crate
  duplicate — and neither is reported at all.

Each `Cargo.toml` here is a minimal package manifest naming the crate; the
duplicate-type check parses `.rs` files and reads `Cargo.toml` locations
to assign a crate id, and is never built with `cargo build`.
