//! ASP407: Worker/Wrapper — trivial pass-through wrapper.
//!
//! `python/src/aspergillus/rules/catalog/worker_wrapper.py`
//! (`WorkerWrapper`) flags a function whose whole body is `return g(a, b,
//! …)` forwarding every positional parameter, verbatim and in order, to a
//! plain-named callee. Gill + Hutton's Worker/Wrapper transformation (JFP
//! 2009) governs such indirection: either the wrapper is about to grow the
//! `rep`/`unrep` logic that justifies it, or it exists only to rename `g`
//! and should be inlined (Fowler, Inline Function).
//!
//! Rust's refined intent: a FREE function — a `function_item` whose parent
//! is the source file or a `mod` block, never an `impl` — whose body is
//! exactly one call forwarding all of its parameters verbatim and in order
//! to a differently-named plain callee. Trait-impl and inherent methods are
//! never considered: `Deref::deref`, `From::from`, and trait forwarding are
//! legitimate one-line pass-throughs the transformation does not target.
//!
//! Conservativeness kept high to avoid false positives on correct Rust:
//! the callee must be a bare identifier (not `self.g`, `T::g`, or a macro),
//! every parameter must be a plain identifier binding, every argument must
//! be that same identifier in the same order, the callee name must differ
//! from the wrapper's own (self-recursion is not a wrapper), `async`
//! wrappers are exempt (sync-to-async adapters are legitimate), and a
//! zero-parameter function forwards nothing and is never flagged.
//!
//! No file, process, or exit code appears here; the binary reads the source
//! and prints findings.

use ast_grep_core::{Doc, Node};
use ast_grep_language::{LanguageExt, SupportLang};

/// ASP407: every free function that is a trivial verbatim pass-through
/// wrapper around a differently-named plain callee. Reported at the
/// function's line. Blocking.
pub fn worker_wrapper_findings(source: &str) -> Vec<(usize, &'static str, bool)> {
    let root = SupportLang::Rust.ast_grep(source);
    let mut funcs = Vec::new();
    collect_free_functions(&root.root(), &mut funcs);
    let mut findings: Vec<(usize, &'static str, bool)> = funcs
        .iter()
        .filter(|f| is_trivial_wrapper(f))
        .map(|f| (f.start_pos().line().saturating_add(1), "ASP407", true))
        .collect();
    findings.sort_by(|a, b| a.0.cmp(&b.0));
    findings
}

/// Collect free `function_item`s: those directly under the source file or
/// under a `mod` block's declaration list. Never descends into an
/// `impl_item` or `trait_item`, so their methods are excluded.
fn collect_free_functions<'a, D: Doc>(node: &Node<'a, D>, out: &mut Vec<Node<'a, D>>) {
    for child in node.children() {
        match child.kind().as_ref() {
            "function_item" => out.push(child),
            "mod_item" => {
                for gc in child.children() {
                    if gc.kind() == "declaration_list" {
                        collect_free_functions(&gc, out);
                    }
                }
            }
            _ => {}
        }
    }
}

/// Whether `func` is a trivial pass-through wrapper: not `async`, at least
/// one parameter, a body of exactly one call to a bare identifier callee
/// (differing from the wrapper's own name) whose arguments are exactly the
/// parameters, as plain identifiers, in declaration order.
fn is_trivial_wrapper<D: Doc>(func: &Node<'_, D>) -> bool {
    if func
        .children()
        .any(|c| c.kind() == "function_modifiers" && c.text().contains("async"))
    {
        return false;
    }
    let Some(name) = func.field("name") else {
        return false;
    };
    let Some(params) = param_names(func) else {
        return false;
    };
    if params.is_empty() {
        return false;
    }
    let Some(body) = func.field("body") else {
        return false;
    };
    let Some(call) = single_body_call(&body) else {
        return false;
    };
    let Some(callee) = call.field("function") else {
        return false;
    };
    if callee.kind() != "identifier" || callee.text() == name.text() {
        return false;
    }
    match arg_names(&call) {
        Some(args) => args == params,
        None => false,
    }
}

/// The wrapper's positional parameter names in declaration order, or `None`
/// if any parameter is not a plain identifier binding (a `self` receiver, a
/// destructuring pattern, `&self`, …) — those are not a verbatim forward.
fn param_names<D: Doc>(func: &Node<'_, D>) -> Option<Vec<String>> {
    let params = func.field("parameters")?;
    let mut names = Vec::new();
    for child in params.children() {
        match child.kind().as_ref() {
            "parameter" => {
                let pattern = child.field("pattern")?;
                if pattern.kind() != "identifier" {
                    return None;
                }
                names.push(pattern.text().to_string());
            }
            "self_parameter" => return None,
            // Punctuation (`(`, `)`, `,`) and attributes are skipped.
            _ => {}
        }
    }
    Some(names)
}

/// The single forwarded call in `body`, or `None` if the body is not
/// exactly one call. Accepts a tail call, a tail `return <call>`, and a
/// single statement of either shape. Comments do not count as statements.
fn single_body_call<'a, D: Doc>(body: &Node<'a, D>) -> Option<Node<'a, D>> {
    let mut meaningful = body.children().filter(|c| {
        !matches!(
            c.kind().as_ref(),
            "{" | "}" | "line_comment" | "block_comment"
        )
    });
    let only = meaningful.next()?;
    if meaningful.next().is_some() {
        return None;
    }
    unwrap_call(&only)
}

/// Unwrap a body element to the call it forwards: a bare call, a
/// `return <call>`, or an `expression_statement` wrapping either.
fn unwrap_call<'a, D: Doc>(node: &Node<'a, D>) -> Option<Node<'a, D>> {
    match node.kind().as_ref() {
        "call_expression" => Some(node.clone()),
        "return_expression" => node.children().find_map(|c| unwrap_call(&c)),
        "expression_statement" => node.children().find_map(|c| unwrap_call(&c)),
        _ => None,
    }
}

/// The call's argument names in order if every argument is a plain
/// identifier, else `None`. A literal, `&x`, `x.clone()`, or reordering
/// makes the call more than a verbatim forward.
fn arg_names<D: Doc>(call: &Node<'_, D>) -> Option<Vec<String>> {
    let args = call.field("arguments")?;
    let mut names = Vec::new();
    for child in args.children() {
        match child.kind().as_ref() {
            "(" | ")" | "," => {}
            "identifier" => names.push(child.text().to_string()),
            // Any non-identifier argument (literal, reference, field access,
            // nested call, attribute) is not a verbatim parameter forward.
            _ => return None,
        }
    }
    Some(names)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lines(source: &str) -> Vec<usize> {
        worker_wrapper_findings(source)
            .into_iter()
            .map(|(line, _, _)| line)
            .collect()
    }

    #[test]
    fn tail_call_forwarding_all_params_is_a_wrapper() {
        assert_eq!(
            lines("fn f(x: i32, y: i32) -> i32 {\n    g(x, y)\n}\n"),
            vec![1]
        );
    }

    #[test]
    fn return_call_forwarding_all_params_is_a_wrapper() {
        assert_eq!(
            lines("fn f(x: i32) -> i32 {\n    return g(x);\n}\n"),
            vec![1]
        );
    }

    #[test]
    fn reordered_args_are_not_a_verbatim_forward() {
        assert!(lines("fn f(x: i32, y: i32) -> i32 {\n    g(y, x)\n}\n").is_empty());
    }

    #[test]
    fn extra_or_literal_args_are_not_a_forward() {
        assert!(lines("fn f(x: i32) -> i32 {\n    g(x, 42)\n}\n").is_empty());
        assert!(lines("fn f(x: i32) -> i32 {\n    g(&x)\n}\n").is_empty());
    }

    #[test]
    fn extra_body_statements_disqualify() {
        assert!(lines("fn f(x: i32) -> i32 {\n    let y = x + 1;\n    g(y)\n}\n").is_empty());
    }

    #[test]
    fn method_and_path_callees_are_exempt() {
        // `self.g(x)` and `T::g(x)` are not bare-identifier callees.
        assert!(lines("fn f(x: i32) -> i32 {\n    T::g(x)\n}\n").is_empty());
    }

    #[test]
    fn impl_methods_are_never_flagged() {
        // A trait/inherent-impl forward (`Deref`, `From`, …) is legitimate.
        assert!(lines(
            "struct S;\nimpl S {\n    fn f(&self, x: i32) -> i32 {\n        g(x)\n    }\n}\n"
        )
        .is_empty());
    }

    #[test]
    fn async_wrapper_is_exempt() {
        assert!(lines("async fn f(x: i32) -> i32 {\n    g(x)\n}\n").is_empty());
    }

    #[test]
    fn self_recursion_is_not_a_wrapper() {
        assert!(lines("fn f(x: i32) -> i32 {\n    f(x)\n}\n").is_empty());
    }

    #[test]
    fn zero_param_function_forwards_nothing() {
        assert!(lines("fn f() {\n    g()\n}\n").is_empty());
    }

    #[test]
    fn wrapper_inside_a_mod_is_flagged() {
        assert_eq!(
            lines("mod m {\n    fn f(x: i32) -> i32 {\n        g(x)\n    }\n}\n"),
            vec![2]
        );
    }
}
