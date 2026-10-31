//! ASP204: loops with no statically-determinable iteration bound.
//!
//! `python/src/aspergillus/rules/level2.py` (`UnboundedLoop`) flags a
//! `while` whose body carries no `break` and whose condition names no
//! counter modified in the body — NASA Power of 10 Rule #2, every loop must
//! have a provable upper bound. Rust's refined intent: the only loop
//! headers with no determinable bound are `loop { .. }` (no condition at
//! all) and `while true { .. }` (a constant-true condition). A `for` loop is
//! bounded by its iterator; every other `while <cond>` re-tests its
//! condition each iteration, so the condition itself is the bound and
//! flagging it would be a false positive on correct Rust. Either infinite
//! header is bounded only by a `break` that exits it: no reachable `break`
//! in its own body is the finding.
//!
//! No file, process, or exit code appears here; the binary at
//! `src/bin/aspergillus_rust_gate.rs` reads the source and prints findings.

use ast_grep_core::{Doc, Node};
use ast_grep_language::{LanguageExt, SupportLang};

/// ASP204: every `loop { .. }` or `while true { .. }` whose own body holds
/// no deliberate exit — neither a reachable `break` nor a `return`. Such a
/// header runs forever: its iteration count cannot be determined from the
/// source. Blocking.
///
/// A `for` loop is bounded by its iterator and a `while <cond>` other than
/// the constant `true` is bounded by its re-tested condition, so neither is
/// ever flagged. A `loop`/`while true` with a `break` (a counter- or
/// iterator-driven exit the author wrote) or a `return` (the function-level
/// exit an arg-parser or tree-walk loop uses) is bounded and stays silent —
/// flagging those would be a false positive on correct, terminating Rust.
pub fn unbounded_loop_findings(source: &str) -> Vec<(usize, &'static str, bool)> {
    let root = SupportLang::Rust.ast_grep(source);
    let mut findings = Vec::new();
    for node in root.root().dfs() {
        let unbounded = match node.kind().as_ref() {
            "loop_expression" => !body_has_exit(&node),
            "while_expression" => is_constant_true(&node) && !body_has_exit(&node),
            _ => false,
        };
        if unbounded {
            findings.push((node.start_pos().line().saturating_add(1), "ASP204", true));
        }
    }
    findings.sort_by(|a, b| a.0.cmp(&b.0));
    findings
}

/// Whether a `while_expression`'s condition is the constant `true` — the
/// `while true` infinite header, which tree-sitter models as a
/// `boolean_literal` condition. `while let`, `while <expr>`, and
/// `while count < n` all carry a non-constant condition and are bounded by
/// it.
fn is_constant_true<D: Doc>(while_expr: &Node<'_, D>) -> bool {
    while_expr
        .field("condition")
        .is_some_and(|c| c.kind() == "boolean_literal" && c.text().as_ref() == "true")
}

/// Whether the loop's own body holds a deliberate exit that targets it: a
/// `break` at this loop's level, or a `return` anywhere in the body.
fn body_has_exit<D: Doc>(loop_expr: &Node<'_, D>) -> bool {
    loop_expr
        .field("body")
        .is_some_and(|body| scope_has_exit(&body, false))
}

/// Whether `node`'s subtree holds an exit for the enclosing loop.
///
/// - A `return` exits the whole function, so it exits the loop from any
///   depth — except from inside a nested closure, whose `return` exits only
///   the closure. Closures are therefore not descended into.
/// - A `break` exits only the innermost enclosing loop, so it counts only
///   when not inside a nested loop (`in_nested_loop` tracks that). A `break`
///   in an `if`/`match`/`block` still bounds this loop, so those are
///   descended.
fn scope_has_exit<D: Doc>(node: &Node<'_, D>, in_nested_loop: bool) -> bool {
    node.children().any(|child| match child.kind().as_ref() {
        "return_expression" => true,
        "break_expression" => !in_nested_loop,
        "closure_expression" => false,
        "loop_expression" | "while_expression" | "for_expression" => scope_has_exit(&child, true),
        _ => scope_has_exit(&child, in_nested_loop),
    })
}
#[cfg(test)]
mod tests {
    use super::*;

    fn lines(source: &str) -> Vec<usize> {
        unbounded_loop_findings(source)
            .into_iter()
            .map(|(line, _, _)| line)
            .collect()
    }

    #[test]
    fn bare_loop_without_break_is_unbounded() {
        assert_eq!(
            lines("fn f() {\n    loop {\n        work();\n    }\n}\n"),
            vec![2]
        );
    }

    #[test]
    fn while_true_without_break_is_unbounded() {
        assert_eq!(
            lines("fn f() {\n    while true {\n        work();\n    }\n}\n"),
            vec![2]
        );
    }

    #[test]
    fn loop_with_break_is_bounded() {
        assert!(lines("fn f() {\n    let mut n = 0;\n    loop {\n        if n >= 10 { break; }\n        n += 1;\n    }\n}\n").is_empty());
    }

    #[test]
    fn while_true_with_break_is_bounded() {
        assert!(
            lines("fn f() {\n    while true {\n        if done() { break; }\n    }\n}\n")
                .is_empty()
        );
    }

    #[test]
    fn for_loop_is_never_flagged() {
        assert!(lines("fn f() {\n    for x in 0..10 {\n        use_it(x);\n    }\n}\n").is_empty());
    }

    #[test]
    fn while_condition_other_than_true_is_bounded_by_its_condition() {
        assert!(lines(
            "fn f() {\n    let mut c = 0;\n    while c < 100 {\n        c += 1;\n    }\n}\n"
        )
        .is_empty());
        assert!(
            lines("fn f() {\n    while let Some(x) = it.next() {\n        g(x);\n    }\n}\n")
                .is_empty()
        );
        assert!(
            lines("fn f() {\n    while chan.recv().is_ok() {\n        step();\n    }\n}\n")
                .is_empty()
        );
    }

    #[test]
    fn a_return_bounds_the_loop() {
        // A `return` is a deliberate function-level exit: an arg-parser or
        // tree-walk `loop { .. return .. }` terminates and is not flagged.
        assert!(lines("fn f(mut check: impl FnMut() -> bool) -> u32 {\n    let mut n = 0;\n    loop {\n        if check() { return n; }\n        n += 1;\n    }\n}\n").is_empty());
    }

    #[test]
    fn a_return_inside_a_closure_does_not_bound_the_loop() {
        // The `return` exits the closure, not the loop — the loop still has
        // no exit and is flagged.
        assert_eq!(
            lines("fn f() {\n    loop {\n        run(|| {\n            return;\n        });\n    }\n}\n"),
            vec![2]
        );
    }

    #[test]
    fn break_in_a_nested_loop_does_not_bound_the_outer() {
        // The inner `loop` has a break (bounded); the outer has none.
        assert_eq!(
            lines(
                "fn f() {\n    loop {\n        loop {\n            break;\n        }\n    }\n}\n"
            ),
            vec![2]
        );
    }

    #[test]
    fn break_in_an_if_bounds_the_loop() {
        assert!(lines(
            "fn f() {\n    loop {\n        if done() { break; }\n        step();\n    }\n}\n"
        )
        .is_empty());
    }
}
