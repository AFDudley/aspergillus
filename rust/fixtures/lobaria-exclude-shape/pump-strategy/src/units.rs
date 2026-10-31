//! Units this crate also declares — production code, never excluded.
//! Duplicates of `statechart/src/units.rs`, differing only in a field's
//! own visibility, which the duplicate-type check's shape ignores.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Bps(i64);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SignedLamports(i64);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TrajectoryRow {
    pub time: i64,
    pub price: i64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Cut {
    Take,
    Skip,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Run {
    Active,
    Done,
}
