//! A deliberately rule-violating fixture input to a consumer's OWN gates —
//! not production code. Redeclares `Owed` and `Hole` with the same shape
//! as `statechart/src/chart.rs`, standing in for the real lobaria
//! `scripts/oracles/fixtures/` subtree this workspace reproduces (see
//! `../../../../PROVENANCE.md`).

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Owed;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Hole<T> {
    Derived(T),
    Owed(Owed),
}
