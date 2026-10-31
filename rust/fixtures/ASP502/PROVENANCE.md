# ASP502 fixture provenance

Every file here is SYNTHETIC, written for pebble asp-11d. No file is copied
from a real repository. The duplicate-type check parses `.rs` files and reads
`Cargo.toml` locations to assign a crate id; these crates are never built.

Each fixture is a two-crate workspace, because ASP502 reports a duplicate
CONCEPT only when it crosses a crate boundary.

- `violating/` — crate A and crate B declare three concepts that duplicate
  across the boundary along the name-independent structural axis:
  - `Run` (crate A) vs `Outcome` (crate B): identical field names and types,
    different struct name — a RENAMED structural duplicate.
  - `Metrics` (both crates): same field names and types, fields REORDERED.
  - `Phase` (both crates): same variants, variants REORDERED.
  The check reports every member of each group (6 findings).

- `satisfying/` — genuinely-distinct types that must NOT be reported:
  - `Lamports(u64)` (crate A) and `TokenUnits(u64)` (crate B): two distinct
    single-field u64 newtypes. The newtype idiom deliberately mints distinct
    wrappers over one primitive, so single-field tuple newtypes never join
    the structural axis.
  - `Sizing { entry_lamports, trim_pct }` vs `Stated { slot, micros }`: both
    two `u64` fields, but different field names — different concepts.
  - `Cut { Take, Skip }` vs `Run { Active, Done }`: different enum names and
    different variant names.
  The check reports nothing (0 findings).
