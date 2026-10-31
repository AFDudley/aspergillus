//! The chart's hole type — production code, never excluded. Reproduces
//! the shape of the real lobaria `statechart/src/chart.rs` declarations
//! this fixture stands in for (see `../../PROVENANCE.md`).

/// A transition body not yet derived.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Owed;

/// The outcome, or the hole.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Hole<T> {
    /// The derived outcome.
    Derived(T),
    /// The body is owed.
    Owed(Owed),
}
