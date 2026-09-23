//! Crate A: three concepts that crate B re-declares as structural
//! duplicates — one renamed, two reordered. Synthetic; never built.

/// A captured subprocess result. Crate B declares the identical field
/// set under the NEW name `Outcome` (a renamed structural duplicate).
pub struct Run {
    pub exit_code: i32,
    pub stdout: String,
    pub stderr: String,
}

/// A two-field record. Crate B declares the same field names and types
/// with the fields REORDERED.
pub struct Metrics {
    pub wins: u64,
    pub losses: u64,
}

/// A small state machine. Crate B declares the same variants REORDERED.
pub enum Phase {
    Start,
    Running,
    Stop,
}
