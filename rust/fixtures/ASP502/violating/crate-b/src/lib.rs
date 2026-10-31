//! Crate B: the same concepts as crate A, re-declared under new names or
//! with fields/variants reordered. Synthetic; never built.

/// A RENAMED copy of crate A's `Run`: same field names and types, new
/// struct name. Reported on the name-independent structural axis.
pub struct Outcome {
    pub exit_code: i32,
    pub stdout: String,
    pub stderr: String,
}

/// Crate A's `Metrics` with its fields REORDERED. Axis 1 keys on the
/// ordered field-name list and stays silent; the structural axis reports
/// it on the order-insensitive `name:type` multiset.
pub struct Metrics {
    pub losses: u64,
    pub wins: u64,
}

/// Crate A's `Phase` with its variants REORDERED. Reported on the
/// order-insensitive variant-descriptor set.
pub enum Phase {
    Stop,
    Start,
    Running,
}
