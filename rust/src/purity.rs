//! Purity signals shared by ASP202, ASP205 and ASP206: the functional core
//! for these three rules.
//!
//! `python/src/aspergillus/rules/level2.py` (`LowAssertionDensity`,
//! `ImpureFunction`, `MixedIOAndLogic`) and
//! `python/src/aspergillus/io_blocklist.py` read one shared signal per
//! function: does its body call a known I/O name, how many assert-like
//! macros does it invoke, and how many top-level logic statements does its
//! body hold. This module computes the same three-part signal for Rust
//! source, over an already-parsed tree; no file, process, or exit code
//! appears here.

use ast_grep_core::{Doc, Node};
use ast_grep_language::{LanguageExt, SupportLang};

/// Bare call or macro names the gate treats as I/O effects: filesystem,
/// process, network and console. Matched on the callee's last path
/// segment (a bare method name, or a plain/scoped function name)
/// regardless of receiver type — the same no-type-resolution trade-off
/// `io_blocklist.py`'s `IO_METHOD_NAMES` documents.
const IO_CALL_NAMES: &[&str] = &[
    "read_to_string",
    "write_all",
    "write_fmt",
    "write",
    "read",
    "read_to_end",
    "read_line",
    "open",
    "create",
    "remove_file",
    "remove_dir",
    "remove_dir_all",
    "create_dir",
    "create_dir_all",
    "rename",
    "copy",
    "read_dir",
    "metadata",
    "connect",
    "bind",
    "send",
    "recv",
    "accept",
    "spawn",
    "output",
    "status",
];

/// Console-output macros the gate treats as I/O, matched on the macro's
/// bare name (the `println!` invocation's `macro` field is `println`, not
/// `println!`).
const IO_MACRO_NAMES: &[&str] = &["println", "eprintln", "print", "eprint"];

/// Assert-like macros, matched the same way. NASA `assert(cond)`'s Rust
/// equivalents.
const ASSERT_MACRO_NAMES: &[&str] = &[
    "assert",
    "assert_eq",
    "assert_ne",
    "debug_assert",
    "debug_assert_eq",
    "debug_assert_ne",
];

/// Direct-child kinds of a function body counted as a logic statement:
/// a binding, an assignment or other bare expression, a return, or a
/// control-flow construct. Mirrors the Python sibling's
/// `_count_logic_statements`, which only looks at a body's direct
/// children, not statements nested inside an `if`/`for`/`while`.
const LOGIC_STATEMENT_KINDS: &[&str] = &[
    "let_declaration",
    "expression_statement",
    "return_expression",
    "if_expression",
    "while_expression",
    "for_expression",
    "loop_expression",
    "match_expression",
];

/// One function's purity signal: its start line, its line count, the I/O
/// names its body calls (empty if pure), how many assert-like macros it
/// invokes, and how many top-level logic statements its body holds.
pub struct FunctionSignal {
    pub line: usize,
    pub line_count: usize,
    pub io_calls: Vec<String>,
    pub assert_count: usize,
    pub logic_count: usize,
}

/// Every function in `source`, each with its own purity signal. A nested
/// function or closure is its own separate signal — walking one
/// function's body does not descend into a nested one, matching how the
/// Python sibling's `_iter_skip_nested` treats a nested `FunctionDef` or
/// `Lambda`.
pub fn scan_functions(source: &str) -> Vec<FunctionSignal> {
    let root = SupportLang::Rust.ast_grep(source);
    root.root()
        .dfs()
        .filter(|n| n.kind() == "function_item")
        .map(|f| function_signal(&f))
        .collect()
}

fn function_signal<D: Doc>(func: &Node<'_, D>) -> FunctionSignal {
    let line = func.start_pos().line().saturating_add(1);
    let end_line = func.end_pos().line().saturating_add(1);
    let line_count = end_line.saturating_sub(line).saturating_add(1);

    let mut io_calls = Vec::new();
    let mut assert_count = 0usize;
    let mut logic_count = 0usize;

    if let Some(body) = func.field("body") {
        for child in body.children() {
            if LOGIC_STATEMENT_KINDS.contains(&child.kind().as_ref()) {
                logic_count += 1;
            }
        }
        walk_own_scope(&body, &mut |node| {
            let kind = node.kind();
            if kind == "call_expression" {
                if let Some(name) = call_callee_name(node) {
                    if IO_CALL_NAMES.contains(&name.as_str()) {
                        io_calls.push(name);
                    }
                }
            } else if kind == "macro_invocation" {
                if let Some(name) = macro_name(node) {
                    if IO_MACRO_NAMES.contains(&name.as_str()) {
                        io_calls.push(name.clone());
                    }
                    if ASSERT_MACRO_NAMES.contains(&name.as_str()) {
                        assert_count += 1;
                    }
                }
            }
        });
    }

    io_calls.sort();
    io_calls.dedup();
    FunctionSignal {
        line,
        line_count,
        io_calls,
        assert_count,
        logic_count,
    }
}

/// Visits every descendant of `node` with `visit`, skipping into a
/// descendant that is itself a nested function or closure — that
/// descendant is visited once but its own body is not walked, so a
/// nested function's calls and asserts count toward the nested function's
/// own signal, not its enclosing function's.
fn walk_own_scope<D: Doc>(node: &Node<'_, D>, visit: &mut impl FnMut(&Node<'_, D>)) {
    for child in node.children() {
        visit(&child);
        let kind = child.kind();
        if kind != "function_item" && kind != "closure_expression" {
            walk_own_scope(&child, visit);
        }
    }
}

/// The macro's bare name (the `println!` invocation's `macro` field text
/// is `println`).
fn macro_name<D: Doc>(macro_invocation: &Node<'_, D>) -> Option<String> {
    Some(macro_invocation.field("macro")?.text().into_owned())
}

/// A call expression's callee, resolved to its last path segment:
/// `f(...)` -> `f`; `a.b(...)` -> `b`; `std::fs::write(...)` -> `write`.
fn call_callee_name<D: Doc>(call: &Node<'_, D>) -> Option<String> {
    let callee = call.field("function")?;
    Some(last_segment(&callee))
}

fn last_segment<D: Doc>(node: &Node<'_, D>) -> String {
    match node.kind().as_ref() {
        "field_expression" => node
            .field("field")
            .map(|f| f.text().into_owned())
            .unwrap_or_default(),
        "scoped_identifier" => node
            .field("name")
            .map(|f| f.text().into_owned())
            .unwrap_or_default(),
        _ => node.text().into_owned(),
    }
}

/// ASP202: a function longer than `MIN_LINES` with fewer than
/// `MIN_ASSERTS` assert-like macro invocations. Mirrors
/// `LowAssertionDensity`. Rust has no dynamic-parameter escape hatch —
/// every parameter is statically typed — so unlike the Python sibling
/// this check applies the assertion-density floor to any function past
/// the line threshold, not only an imperative-shell subset.
pub fn assertion_density_findings(source: &str) -> Vec<(usize, &'static str, bool)> {
    const MIN_LINES: usize = 5;
    const MIN_ASSERTS: usize = 2;
    scan_functions(source)
        .into_iter()
        .filter(|f| f.line_count > MIN_LINES && f.assert_count < MIN_ASSERTS)
        .map(|f| (f.line, "ASP202", true))
        .collect()
}

/// ASP205: a function whose body calls a known Rust I/O name. Mirrors
/// `ImpureFunction`: blocking — the finding fails the gate run, since every
/// Aspergillus Rust rule now blocks.
pub fn impure_function_findings(source: &str) -> Vec<(usize, &'static str, bool)> {
    scan_functions(source)
        .into_iter()
        .filter(|f| !f.io_calls.is_empty())
        .map(|f| (f.line, "ASP205", true))
        .collect()
}

/// ASP206: a function that both calls I/O and holds more than
/// `LOGIC_THRESHOLD` top-level logic statements — I/O mixed with enough
/// business logic that functional-core / imperative-shell separation
/// would help. Mirrors `MixedIOAndLogic`.
pub fn mixed_io_logic_findings(source: &str) -> Vec<(usize, &'static str, bool)> {
    const LOGIC_THRESHOLD: usize = 3;
    scan_functions(source)
        .into_iter()
        .filter(|f| !f.io_calls.is_empty() && f.logic_count > LOGIC_THRESHOLD)
        .map(|f| (f.line, "ASP206", true))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_short_pure_function_is_exempt_from_asp202() {
        let source = "fn add(a: i32, b: i32) -> i32 {\n    a + b\n}\n";
        assert_eq!(assertion_density_findings(source), Vec::new());
    }

    #[test]
    fn a_long_function_with_no_asserts_is_asp202() {
        let source = "fn transfer(a: i32, b: i32, c: i32) -> i32 {\n    let x = a + b;\n    let y = x + c;\n    let z = y - a;\n    let w = z * 2;\n    let v = w - b;\n    v\n}\n";
        let found = assertion_density_findings(source);
        assert_eq!(found, vec![(1, "ASP202", true)]);
    }

    #[test]
    fn two_asserts_satisfy_asp202() {
        let source = "fn transfer(a: i32, b: i32, c: i32) -> i32 {\n    assert!(a >= 0);\n    assert!(b >= 0);\n    let x = a + b;\n    let y = x + c;\n    let z = y - a;\n    let w = z * 2;\n    w\n}\n";
        assert_eq!(assertion_density_findings(source), Vec::new());
    }

    #[test]
    fn a_function_calling_println_is_asp205() {
        let source = "fn save(data: &str) {\n    println!(\"{data}\");\n}\n";
        assert_eq!(impure_function_findings(source), vec![(1, "ASP205", true)]);
    }

    #[test]
    fn a_pure_function_is_not_asp205() {
        let source = "fn add(a: i32, b: i32) -> i32 {\n    a + b\n}\n";
        assert_eq!(impure_function_findings(source), Vec::new());
    }

    #[test]
    fn io_mixed_with_logic_past_threshold_is_asp206() {
        let source = "fn mixed(raw: &str) -> i32 {\n    println!(\"{raw}\");\n    let a = raw.len();\n    let b = a + 1;\n    let c = b * 2;\n    let d = c - a;\n    d as i32\n}\n";
        assert_eq!(mixed_io_logic_findings(source), vec![(1, "ASP206", true)]);
    }

    #[test]
    fn an_orchestrator_under_the_threshold_is_not_asp206() {
        let source = "fn orchestrator(raw: &str) {\n    println!(\"{raw}\");\n}\n";
        assert_eq!(mixed_io_logic_findings(source), Vec::new());
    }

    #[test]
    fn a_nested_function_is_scanned_separately() {
        let source =
            "fn outer() {\n    fn inner() {\n        println!(\"hi\");\n    }\n    inner();\n}\n";
        let found = impure_function_findings(source);
        assert_eq!(found, vec![(2, "ASP205", true)]);
    }
}
