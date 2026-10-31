//! The chart contract.
//!
//! Concept: This crate reads `docs/chart.json5`, checks it, and draws it.
//!
//! The contract file is the one source of truth for the machine's chart
//! (`docs/glossary.md`, "The statechart"; `docs/thesis.md`). This crate is
//! the only reader of it: `json5` (tree-sitter, comments kept as extras),
//! `contract` (the typed chart, parsed once), `check` (the structural
//! findings the gate prints), `render` (Mermaid, on demand, never committed).
//! `rust_reader` (tree-sitter-rust, the reader the gate ports share) and
//! `vocabulary_io` (the retired-word gate over it) are the source-side half.
//! `ast_grep_gate` runs the core-types and parse-not-validate gates' rules,
//! read declaratively from YAML by ast-grep's own engine.
//! `strategy_contract`, `strategy_check`, `strategy_generate` and `strategy_io`
//! are the same for `docs/strategy.json5`: the strategy as data, its
//! structural gate, and the generator of `pump-strategy`'s decision core.
//! `generate` writes `statechart`'s chart types from the contract, and
//! `conformance` (with `conformance_io`) is the gate that reads them back and
//! refuses any difference from the contract. `tour` computes the Phase 7
//! work-ordering tour: for each region, an ordered walk of transition names
//! from its initial substate, and which declared transitions the walk
//! leaves uncovered.

pub mod ast_grep_gate;
pub mod bodies;
pub mod check;
pub mod conformance;
pub mod conformance_io;
pub mod contract;
pub mod contract_shape;
pub mod gate_shell;
pub mod gate_types;
pub mod generate;
pub mod json5;
pub mod manifest;
pub mod probe_support;
pub mod render;
pub mod rust_reader;
pub mod strategy_check;
pub mod strategy_contract;
pub mod strategy_generate;
pub mod strategy_io;
#[cfg(test)]
mod test_support;
pub mod totality;
pub mod totality_io;
pub mod tour;
pub mod vocabulary_io;
pub mod wire;

/// Read and parse a contract's text into a chart, or say why not.
pub fn load(text: &str) -> Result<contract::Chart, String> {
    let value = json5::read(text).map_err(|r| format!("line {}: {}", r.line, r.why))?;
    contract::parse(&value).map_err(|s| format!("{}: expected {}", s.at, s.why))
}
