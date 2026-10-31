//! Units this crate declares — production code, never excluded.

/// Basis points.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Bps(pub i64);

/// Lamports that may be negative (a signed delta).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SignedLamports(pub i64);

/// One row of a recorded trajectory.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TrajectoryRow {
    pub time: i64,
    pub price: i64,
}

/// Whether a signal is acted on.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Cut {
    Take,
    Skip,
}

/// Whether the machine is running.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Run {
    Active,
    Done,
}
