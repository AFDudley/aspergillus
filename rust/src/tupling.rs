//! ASP406: Tupling — two aggregation passes over the same iterable.
//!
//! `python/src/aspergillus/rules/catalog/tupling.py` (`Tupling`) flags two
//! consecutive aggregation-builtin calls (`sum`, `max`, `min`, `len`,
//! `any`, `all`) over the same plain-name iterable in one function body:
//! Bird's Tupling move (Pearls of Functional Algorithm Design, 2010)
//! collapses the two traversals into one pass returning a tuple.
//!
//! Rust's refined intent: two iterator-aggregation chains rooted at the
//! SAME receiver identifier inside one function body. A chain is rooted
//! when its base is `IDENT.iter()`, `IDENT.into_iter()`, or
//! `IDENT.iter_mut()` and its aggregating method is one of `sum`,
//! `product`, `max`, `min`, `count`, `any`, `all`, `fold`, `last` — the
//! terminal one-pass consumers of an iterator. When two such chains share
//! the same base identifier, the second one is the second traversal: the
//! Tupling opportunity, reported at the second chain's line. Detection is
//! the value; the single-pass rewrite is a design decision.
//!
//! Requiring a plain-identifier base (`xs`, not `self.data` or `f()`) and
//! an iterator-family base method keeps this conservative: a chain over a
//! different receiver, or one whose base is not a plain `IDENT.iter()`, is
//! never a false Tupling trigger on correct Rust. No file, process, or exit
//! code appears here; the binary reads the source and prints findings.

use ast_grep_core::{Doc, Node};
use ast_grep_language::{LanguageExt, SupportLang};

/// Iterator methods that consume the whole iterator in a single pass.
/// Two of these rooted at the same receiver are two traversals.
const AGGREGATORS: &[&str] = &[
    "sum", "product", "max", "min", "count", "any", "all", "fold", "last",
];

/// Methods that turn an owner into an iterator. A Tupling base is exactly
/// `IDENT.iter()` / `IDENT.into_iter()` / `IDENT.iter_mut()`.
const ITER_METHODS: &[&str] = &["iter", "into_iter", "iter_mut"];

/// ASP406: within each free or nested function body, two aggregation
/// chains rooted at the same receiver identifier. The first chain is the
/// first traversal and stays silent; every later chain over that same
/// receiver is a second pass and is reported at its own line. Blocking.
pub fn tupling_findings(source: &str) -> Vec<(usize, &'static str, bool)> {
    let root = SupportLang::Rust.ast_grep(source);
    let mut findings = Vec::new();
    for node in root.root().dfs() {
        if node.kind() == "function_item" {
            findings.extend(function_tupling(&node));
        }
    }
    findings.sort_by(|a, b| a.0.cmp(&b.0));
    findings.dedup();
    findings
}

/// Every second-or-later aggregation chain in one function body, keyed by
/// the base receiver identifier. Nested `function_item`s are skipped: they
/// are their own bodies and are visited independently by the caller's dfs.
fn function_tupling<D: Doc>(func: &Node<'_, D>) -> Vec<(usize, &'static str, bool)> {
    let mut seen: Vec<String> = Vec::new();
    let mut out = Vec::new();
    let Some(body) = func.field("body") else {
        return out;
    };
    collect_chains(&body, &mut seen, &mut out);
    out
}

/// Walk `node`'s subtree collecting aggregation chains, but do not descend
/// into a nested `function_item` — that body owns its own traversals.
fn collect_chains<D: Doc>(
    node: &Node<'_, D>,
    seen: &mut Vec<String>,
    out: &mut Vec<(usize, &'static str, bool)>,
) {
    for child in node.children() {
        if child.kind() == "function_item" {
            continue;
        }
        if child.kind() == "call_expression" {
            if let Some(base) = aggregation_base(&child) {
                if seen.contains(&base) {
                    out.push((child.start_pos().line().saturating_add(1), "ASP406", true));
                } else {
                    seen.push(base);
                }
            }
        }
        collect_chains(&child, seen, out);
    }
}

/// If `call` is an aggregation chain (`sum`/`max`/… whose receiver walks
/// down to a plain `IDENT.iter()`-family base), return the base receiver
/// identifier text.
fn aggregation_base<D: Doc>(call: &Node<'_, D>) -> Option<String> {
    let func = call.field("function")?;
    if func.kind() != "field_expression" {
        return None;
    }
    let method = func.field("field")?;
    if !AGGREGATORS.contains(&method.text().as_ref()) {
        return None;
    }
    let receiver = func.field("value")?;
    if receiver.kind() != "call_expression" {
        return None;
    }
    iter_base(&receiver)
}

/// Descend a method-call receiver chain to its base. The base is reached
/// when a call's method is an iterator-family method (`iter` / `into_iter`
/// / `iter_mut`) whose own receiver is a plain identifier; that identifier
/// is returned. Intermediate combinators (`.filter(_)`, `.map(_)`, …) are
/// walked through. Any non-identifier base (`self.xs.iter()`, `f().iter()`)
/// yields `None`: too imprecise to call a Tupling trigger.
fn iter_base<D: Doc>(call: &Node<'_, D>) -> Option<String> {
    let func = call.field("function")?;
    if func.kind() != "field_expression" {
        return None;
    }
    let method = func.field("field")?;
    let receiver = func.field("value")?;
    if ITER_METHODS.contains(&method.text().as_ref()) {
        if receiver.kind() == "identifier" {
            return Some(receiver.text().to_string());
        }
        return None;
    }
    // An intermediate combinator: keep descending if its receiver is
    // itself a method call, else this chain has no plain iter base.
    if receiver.kind() == "call_expression" {
        return iter_base(&receiver);
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lines(source: &str) -> Vec<usize> {
        tupling_findings(source)
            .into_iter()
            .map(|(line, _, _)| line)
            .collect()
    }

    #[test]
    fn two_aggregations_over_the_same_receiver_flag_the_second() {
        assert_eq!(
            lines(
                "fn stats(xs: &[i32]) -> (i32, usize) {\n    let total: i32 = xs.iter().sum();\n    let n = xs.iter().count();\n    (total, n)\n}\n"
            ),
            vec![3]
        );
    }

    #[test]
    fn aggregation_behind_an_intermediate_combinator_still_roots_at_the_base() {
        assert_eq!(
            lines(
                "fn f(xs: Vec<i32>) {\n    let a: i32 = xs.iter().filter(|x| **x > 0).sum();\n    let b = xs.iter().map(|x| x + 1).max();\n}\n"
            ),
            vec![3]
        );
    }

    #[test]
    fn different_receivers_are_two_independent_first_passes() {
        assert!(lines(
            "fn f(xs: &[i32], ys: &[i32]) {\n    let a: i32 = xs.iter().sum();\n    let b: i32 = ys.iter().sum();\n}\n"
        )
        .is_empty());
    }

    #[test]
    fn a_single_aggregation_is_never_flagged() {
        assert!(lines("fn f(xs: &[i32]) {\n    let a: i32 = xs.iter().sum();\n}\n").is_empty());
    }

    #[test]
    fn a_non_identifier_base_is_not_a_trigger() {
        // `self.data.iter()` and `make().iter()` have no plain-identifier
        // base, so neither participates in a Tupling group.
        assert!(lines(
            "fn f(&self) {\n    let a: i32 = self.data.iter().sum();\n    let b: i32 = self.data.iter().count() as i32;\n}\n"
        )
        .is_empty());
    }

    #[test]
    fn same_receiver_in_separate_functions_does_not_couple() {
        assert!(lines(
            "fn f(xs: &[i32]) {\n    let a: i32 = xs.iter().sum();\n}\nfn g(xs: &[i32]) {\n    let b: i32 = xs.iter().sum();\n}\n"
        )
        .is_empty());
    }

    #[test]
    fn max_then_unwrap_still_counts_as_an_aggregation() {
        assert_eq!(
            lines(
                "fn f(xs: &[i32]) {\n    let a: i32 = xs.iter().sum();\n    let b = xs.iter().max().unwrap();\n}\n"
            ),
            vec![3]
        );
    }
}
