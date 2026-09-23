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

/// Call names the gate treats as I/O regardless of call form or receiver:
/// rarely collide with a domain method of the same name, so the callee's
/// last path segment alone (a bare method name, or a plain/scoped
/// function name) is enough — the same no-type-resolution trade-off
/// `io_blocklist.py`'s `IO_METHOD_NAMES` documents.
const IO_UNAMBIGUOUS_NAMES: &[&str] = &[
    "read_to_string",
    "read_to_end",
    "read_line",
    "write_all",
    "write_fmt",
    "flush",
    "sync_all",
];

/// Call names the gate treats as I/O ONLY when the call is qualified by a
/// known I/O-providing path (`IO_QUALIFIED_PREFIXES`) — these names are
/// common enough on an ordinary domain type or module that an unqualified
/// match would flag legitimate non-I/O code. Verified false positives the
/// unqualified match produced: `book.open()` on an in-memory book,
/// `json5::read(text)` over a `&str`, `queue.recv()`/`results.send(..)`
/// on an `mpsc` channel, and `rc::create(..)`/`fire::create(..)` domain
/// constructors (lobaria `shell/src/machine.rs`, `shell/src/capture.rs`,
/// `backtest/src/replay.rs`, `chart/src/lib.rs`).
const IO_QUALIFIED_ONLY_NAMES: &[&str] = &[
    "open",
    "create",
    "read",
    "write",
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
    "exit",
];

/// A known I/O-providing path prefix: a scoped call whose full callee text
/// starts with one of these is I/O even when its bare name is one of the
/// collision-prone `IO_QUALIFIED_ONLY_NAMES`. A plain method call on an
/// unrelated receiver (`book.open()`) or a scoped call into an unrelated
/// module (`json5::read`, `rc::create`) starts with none of these and
/// stays unmatched.
const IO_QUALIFIED_PREFIXES: &[&str] = &[
    "std::fs::",
    "fs::",
    "File::",
    "std::io::",
    "io::",
    "std::net::",
    "net::",
    "TcpStream::",
    "TcpListener::",
    "UdpSocket::",
    "std::process::",
    "process::",
    "Command::",
];

/// Console-output and buffer-write macros the gate treats as I/O, matched
/// on the macro's bare name (the `println!` invocation's `macro` field is
/// `println`, not `println!`). `write!`/`writeln!` can also target an
/// in-memory `String` — a known over-approximation, kept because the gate
/// has no receiver-type information to narrow it further.
const IO_MACRO_NAMES: &[&str] = &[
    "println", "eprintln", "print", "eprint", "write", "writeln", "dbg",
];

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

/// Call names ASP202 counts as an assertion form, matched on the callee's
/// last path segment (parity with the Python rule's `ASSERTION_METHOD_NAMES`):
/// `ok_or`/`ok_or_else` turn an `Option` into a checked `Result`;
/// `try_from`/`try_new`/`from_str`/`parse` are validating constructors that
/// reject bad input by returning an `Err`. Each is a precondition the author
/// enforces at a boundary, the Rust analogue of NASA `assert(cond)`.
const ASSERT_CALL_NAMES: &[&str] = &[
    "ok_or",
    "ok_or_else",
    "try_from",
    "try_new",
    "from_str",
    "parse",
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
/// invokes, how many top-level logic statements its body holds, and
/// whether it is a test function (carries a `#[test]`-style attribute or
/// sits inside a `#[cfg(test)]` module) — the Python sibling exempts
/// `test_` functions, so the Rust rules exempt these.
pub struct FunctionSignal {
    pub line: usize,
    pub line_count: usize,
    pub io_calls: Vec<String>,
    pub assert_count: usize,
    pub logic_count: usize,
    pub is_test: bool,
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
                    let is_io = IO_UNAMBIGUOUS_NAMES.contains(&name.as_str())
                        || (IO_QUALIFIED_ONLY_NAMES.contains(&name.as_str())
                            && is_qualified_io_call(node));
                    if ASSERT_CALL_NAMES.contains(&name.as_str()) {
                        assert_count += 1;
                    }
                    if is_io {
                        io_calls.push(name);
                    }
                }
            } else if kind == "macro_invocation" {
                if let Some(name) = macro_name(node) {
                    let is_formatter_write =
                        (name == "write" || name == "writeln") && targets_a_formatter(node);
                    if IO_MACRO_NAMES.contains(&name.as_str()) && !is_formatter_write {
                        io_calls.push(name.clone());
                    }
                    if ASSERT_MACRO_NAMES.contains(&name.as_str()) {
                        assert_count += 1;
                    }
                }
            } else if kind == "try_expression" {
                // The `?` operator is a checked precondition on the wrapped
                // expression: propagate-the-error-or-continue.
                assert_count += 1;
            } else if kind == "return_expression" && returns_err(node) {
                // A `return Err(..)` guard clause is NASA `assert(cond)`:
                // `if bad { return Err(..) }` enforces a precondition.
                assert_count += 1;
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
        is_test: is_test_function(func),
    }
}

/// True when `node` (a `return_expression`) directly returns a call to
/// `Err(..)` — the `return Err(..)` guard-clause assertion form.
fn returns_err<D: Doc>(node: &Node<'_, D>) -> bool {
    node.children().any(|child| {
        child.kind() == "call_expression" && call_callee_name(&child).as_deref() == Some("Err")
    })
}

/// Whether `func` is a test function: it carries a `#[test]`-style
/// attribute (`#[test]`, `#[tokio::test]`, `#[cfg(test)]`), or it sits
/// inside a module annotated `#[cfg(test)]`. tree-sitter-rust models an
/// item's attributes as `attribute_item` nodes that PRECEDE the item as
/// siblings, so both cases are read off preceding siblings — of the
/// function for a direct attribute, of an ancestor `mod_item` for the
/// enclosing test module. Mirrors the Python sibling exempting `test_`.
fn is_test_function<D: Doc>(func: &Node<'_, D>) -> bool {
    if has_test_attribute(func) {
        return true;
    }
    let mut ancestor = func.parent();
    while let Some(node) = ancestor {
        if node.kind() == "mod_item" && has_test_attribute(&node) {
            return true;
        }
        ancestor = node.parent();
    }
    false
}

/// Whether `item`'s immediately-preceding `attribute_item` siblings
/// include a `test`/`cfg(test)` attribute.
fn has_test_attribute<D: Doc>(item: &Node<'_, D>) -> bool {
    let mut prev = item.prev();
    while let Some(node) = prev {
        if node.kind() != "attribute_item" {
            break;
        }
        if node.text().contains("test") {
            return true;
        }
        prev = node.prev();
    }
    false
}

/// Visits every descendant of `node` with `visit`, skipping into a
/// descendant that is itself a nested function — that descendant is
/// visited once but its own body is not walked, so a nested function's
/// calls and asserts count toward the nested function's own signal, not
/// its enclosing function's. A closure is NOT skipped: `scan_functions`
/// only collects `function_item` nodes, so a closure's own I/O calls
/// (`iter().for_each(|p| std::fs::write(p, ..))`) would otherwise never
/// be seen by any function's signal at all.
fn walk_own_scope<D: Doc>(node: &Node<'_, D>, visit: &mut impl FnMut(&Node<'_, D>)) {
    for child in node.children() {
        visit(&child);
        if child.kind() != "function_item" {
            walk_own_scope(&child, visit);
        }
    }
}

/// Whether a `write!`/`writeln!` invocation targets an in-memory
/// `fmt::Formatter` — the near-universal shape of a `Display`/`Debug`
/// impl's `fmt` method or a `serde::de::Visitor::expecting` method — not a
/// file or socket. A `Display`/`Debug` impl's `fmt` method names its
/// `fmt::Formatter` parameter `f`; a `serde::de::Visitor::expecting` method
/// names it `formatter` (rustc's own docs and every generated impl use
/// exactly those two names). A `write!`/`writeln!` whose first argument is
/// any other identifier is presumed to target real I/O.
fn targets_a_formatter<D: Doc>(macro_invocation: &Node<'_, D>) -> bool {
    let text = macro_invocation.text();
    let Some(open) = text.find('(') else {
        return false;
    };
    let after_open = &text[open + 1..];
    let first_arg_end = after_open.find([',', ')']).unwrap_or(after_open.len());
    matches!(after_open[..first_arg_end].trim(), "f" | "formatter")
}

/// Whether `call`'s callee text is qualified by a known I/O-providing
/// path prefix (`IO_QUALIFIED_PREFIXES`) — a scoped call into a real I/O
/// module or type (`std::fs::File::open`, `TcpListener::bind`), not a
/// plain method call on an arbitrary receiver or a scoped call into an
/// unrelated module.
fn is_qualified_io_call<D: Doc>(call: &Node<'_, D>) -> bool {
    let Some(callee) = call.field("function") else {
        return false;
    };
    let text = callee.text();
    IO_QUALIFIED_PREFIXES
        .iter()
        .any(|prefix| text.starts_with(prefix))
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

/// ASP202: a non-test function longer than `MIN_LINES` with fewer than
/// `MIN_ASSERTS` recognized assertion forms. Mirrors `LowAssertionDensity`.
/// An assertion form is an assert-family macro, the `?` operator, a
/// `return Err(..)` guard clause, `ok_or`/`ok_or_else`, or a validating
/// constructor (`try_from`/`try_new`/`from_str`/`parse`) — the Rust
/// analogues of NASA `assert(cond)` and the Python rule's raise-guards and
/// `ASSERTION_METHOD_NAMES`. The gate runs this only over the imperative
/// shell (files outside the declared functional core): a pure, fully-typed
/// core function earns its correctness statically, so demanding two runtime
/// asserts there mis-prescribes the shell mechanism onto the core.
pub fn assertion_density_findings(source: &str) -> Vec<(usize, &'static str, bool)> {
    const MIN_LINES: usize = 5;
    const MIN_ASSERTS: usize = 2;
    scan_functions(source)
        .into_iter()
        .filter(|f| !f.is_test && f.line_count > MIN_LINES && f.assert_count < MIN_ASSERTS)
        .map(|f| (f.line, "ASP202", true))
        .collect()
}

/// ASP205: a non-test function whose body calls a known Rust I/O name.
/// Mirrors `ImpureFunction`: blocking. The gate runs it only over files
/// inside the declared functional core — I/O in the core is the finding.
pub fn impure_function_findings(source: &str) -> Vec<(usize, &'static str, bool)> {
    scan_functions(source)
        .into_iter()
        .filter(|f| !f.is_test && !f.io_calls.is_empty())
        .map(|f| (f.line, "ASP205", true))
        .collect()
}

/// ASP206: a non-test function that both calls I/O and holds more than
/// `LOGIC_THRESHOLD` top-level logic statements. Mirrors `MixedIOAndLogic`.
/// The gate runs it only over files OUTSIDE the declared functional core
/// (the imperative shell): a thin shell is adapters between the world and
/// the core's types, so a shell function that mixes I/O with real logic is
/// the finding — the fix is lifting that logic into the core. Inside the
/// core, ASP205 already flags any I/O, so ASP206 would add nothing there.
pub fn mixed_io_logic_findings(source: &str) -> Vec<(usize, &'static str, bool)> {
    const LOGIC_THRESHOLD: usize = 3;
    scan_functions(source)
        .into_iter()
        .filter(|f| !f.is_test && !f.io_calls.is_empty() && f.logic_count > LOGIC_THRESHOLD)
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
    fn two_question_marks_satisfy_asp202() {
        let source = "fn parse_two(a: &str, b: &str) -> Result<i32, std::num::ParseIntError> {\n    let x = a.parse::<i32>()?;\n    let y = b.parse::<i32>()?;\n    let z = x + y;\n    let w = z * 2;\n    let v = w - 1;\n    Ok(v)\n}\n";
        assert_eq!(assertion_density_findings(source), Vec::new());
    }

    #[test]
    fn two_return_err_guards_satisfy_asp202() {
        let source = "fn checked(a: i32, b: i32) -> Result<i32, String> {\n    if a < 0 {\n        return Err(\"a\".to_string());\n    }\n    if b < 0 {\n        return Err(\"b\".to_string());\n    }\n    Ok(a + b)\n}\n";
        assert_eq!(assertion_density_findings(source), Vec::new());
    }

    #[test]
    fn ok_or_and_a_validating_constructor_satisfy_asp202() {
        let source = "fn build(raw: Option<&str>) -> Result<i32, String> {\n    let text = raw.ok_or(\"missing\")?;\n    let value = i32::from_str(text).map_err(|_| \"bad\")?;\n    let doubled = value * 2;\n    let shifted = doubled - 1;\n    Ok(shifted)\n}\n";
        assert_eq!(assertion_density_findings(source), Vec::new());
    }

    #[test]
    fn a_test_function_with_no_asserts_is_exempt_from_asp202() {
        let source = "#[test]\nfn checks() {\n    let a = 1;\n    let b = a + 1;\n    let c = b + 1;\n    let d = c + 1;\n    let e = d + 1;\n}\n";
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
    fn a_test_function_doing_io_is_exempt_from_asp205_and_asp206() {
        let source = "#[test]\nfn writes_a_file() {\n    std::fs::write(\"x\", b\"\").unwrap();\n    let a = 1;\n    let b = 2;\n    let c = 3;\n    let d = 4;\n}\n";
        assert_eq!(impure_function_findings(source), Vec::new());
        assert_eq!(mixed_io_logic_findings(source), Vec::new());
    }

    #[test]
    fn a_helper_inside_a_cfg_test_module_is_exempt() {
        let source = "#[cfg(test)]\nmod tests {\n    fn helper() {\n        std::fs::write(\"x\", b\"\").unwrap();\n        let a = 1;\n        let b = 2;\n        let c = 3;\n        let d = 4;\n    }\n}\n";
        assert_eq!(impure_function_findings(source), Vec::new());
        assert_eq!(mixed_io_logic_findings(source), Vec::new());
    }

    #[test]
    fn a_nested_function_is_scanned_separately() {
        let source =
            "fn outer() {\n    fn inner() {\n        println!(\"hi\");\n    }\n    inner();\n}\n";
        let found = impure_function_findings(source);
        assert_eq!(found, vec![(2, "ASP205", true)]);
    }

    #[test]
    fn a_bare_method_call_named_open_on_a_domain_receiver_is_not_asp205() {
        let source = "fn open_tokens(book: &Book) -> Option<Unit> {\n    book.open().find_map(|x| Some(x))\n}\n";
        assert_eq!(impure_function_findings(source), Vec::new());
    }

    #[test]
    fn a_scoped_read_call_into_an_unrelated_module_is_not_asp205() {
        let source = "fn load(text: &str) -> Chart {\n    json5::read(text).unwrap()\n}\n";
        assert_eq!(impure_function_findings(source), Vec::new());
    }

    #[test]
    fn mpsc_send_and_recv_are_not_asp205() {
        let source =
            "fn decode_worker(queue: &Receiver<Job>, results: &SyncSender<Out>) {\n    let job = queue.recv();\n    results.send(job).ok();\n}\n";
        assert_eq!(impure_function_findings(source), Vec::new());
    }

    #[test]
    fn a_domain_create_constructor_is_not_asp205() {
        let source =
            "fn build(from: Unseen) -> Running {\n    let outcome = rc::create(from);\n    outcome\n}\n";
        assert_eq!(impure_function_findings(source), Vec::new());
    }

    #[test]
    fn a_qualified_filesystem_write_is_asp205() {
        let source =
            "fn save(path: &str, data: &[u8]) {\n    std::fs::write(path, data).unwrap();\n}\n";
        assert_eq!(impure_function_findings(source), vec![(1, "ASP205", true)]);
    }

    #[test]
    fn a_file_write_hidden_inside_a_for_each_closure_is_asp205() {
        let source = "fn persist(ps: &[&str]) {\n    ps.iter().for_each(|p| std::fs::write(p, b\"\").unwrap());\n}\n";
        assert_eq!(impure_function_findings(source), vec![(1, "ASP205", true)]);
    }

    #[test]
    fn writeln_to_a_file_is_asp205() {
        let source = "fn f(w: &mut std::fs::File) {\n    writeln!(w, \"x\").unwrap();\n}\n";
        assert_eq!(impure_function_findings(source), vec![(1, "ASP205", true)]);
    }

    #[test]
    fn write_macro_is_asp205() {
        let source = "fn f(w: &mut std::fs::File) {\n    write!(w, \"x\").unwrap();\n}\n";
        assert_eq!(impure_function_findings(source), vec![(1, "ASP205", true)]);
    }

    #[test]
    fn write_to_a_display_formatter_named_f_is_not_asp205() {
        let source = "fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {\n    write!(f, \"{}\", self.0)\n}\n";
        assert_eq!(impure_function_findings(source), vec![]);
    }

    #[test]
    fn write_to_a_visitor_expecting_formatter_is_not_asp205() {
        let source = "fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {\n    write!(formatter, \"a sequence of {N} elements\")\n}\n";
        assert_eq!(impure_function_findings(source), vec![]);
    }

    #[test]
    fn dbg_macro_is_asp205() {
        let source = "fn f(x: i32) -> i32 {\n    dbg!(x)\n}\n";
        assert_eq!(impure_function_findings(source), vec![(1, "ASP205", true)]);
    }

    #[test]
    fn flush_is_asp205() {
        let source = "fn f(w: &mut std::fs::File) {\n    w.flush().unwrap();\n}\n";
        assert_eq!(impure_function_findings(source), vec![(1, "ASP205", true)]);
    }

    #[test]
    fn sync_all_is_asp205() {
        let source = "fn f(w: &std::fs::File) {\n    w.sync_all().unwrap();\n}\n";
        assert_eq!(impure_function_findings(source), vec![(1, "ASP205", true)]);
    }

    #[test]
    fn process_exit_is_asp205() {
        let source = "fn f() {\n    std::process::exit(1);\n}\n";
        assert_eq!(impure_function_findings(source), vec![(1, "ASP205", true)]);
    }

    #[test]
    fn write_to_a_formatter_in_a_display_impl_is_not_asp205() {
        let source = "impl fmt::Display for Chart {\n    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {\n        write!(f, \"{}\", self.0)\n    }\n}\n";
        assert_eq!(impure_function_findings(source), Vec::new());
    }

    #[test]
    fn writeln_to_a_formatter_in_a_visitor_expecting_method_is_not_asp205() {
        let source = "impl<'de> Visitor<'de> for SignatureVisitor {\n    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {\n        writeln!(f, \"a sequence of {N} bytes\")\n    }\n}\n";
        assert_eq!(impure_function_findings(source), Vec::new());
    }
}
