//! ASP408: anti-special-casing — a gaming DETECTOR in implementation code.
//!
//! `python/src/aspergillus/rules/catalog/anti_special_casing.py`
//! (`AntiSpecialCasing`) flags two shapes that game a test rather than
//! satisfy it: a *hardcoded-answer branch* (`if x == <literal>: return
//! <literal>` — a memorised oracle answer, not a computation) and a
//! *CI/test-env defeat device* (implementation code branching on a
//! CI/test environment variable, the Volkswagen shape where behaviour
//! changes under test). Both are the tell of a stub that special-cases the
//! one tested input to its expected output instead of computing it.
//!
//! Rust's refined intent keeps that scope exactly. Detector A: an
//! `if <a> == <literal>` whose consequence *yields a constant literal* —
//! either `return <literal>` or a literal tail expression. The compared
//! literal and the returned literal must both be *specific* (a non-empty
//! string, a number other than the guard boundaries `0`/`1`, or a
//! non-empty collection literal); an ordinary guard clause that returns a
//! trivial sentinel (`None`, `false`, `()`, `0`) or computes its result (a
//! call, an arithmetic expression) is legitimate and never flagged. A
//! `match` on a literal is a legitimate dispatch/lookup table in Rust and
//! is deliberately NOT flagged. Detector B: a `std::env::var`/`var_os`
//! read whose key is an unambiguous CI/test marker.
//!
//! Test code is exempt: the gate does not call this analyzer for a
//! `tests/` path, and any `#[cfg(test)]`/`#[test]` scope is skipped here —
//! hardcoded fixtures ARE the test, not gaming.

use ast_grep_core::{Doc, Node};
use ast_grep_language::{LanguageExt, SupportLang};

/// Unambiguous CI/test environment markers. An implementation has no
/// legitimate reason to branch on any of these; each exists only under a
/// CI runner or a test harness. Mirrors the Python `_TEST_ENV_VARS` set
/// (which deliberately excludes generic keys like `TEST`/`ENV`) and adds
/// the Rust-toolchain-specific markers cargo/nextest set only under test.
const TEST_ENV_MARKERS: &[&str] = &[
    "CI",
    "CONTINUOUS_INTEGRATION",
    "GITHUB_ACTIONS",
    "GITLAB_CI",
    "JENKINS_URL",
    "TRAVIS",
    "CIRCLECI",
    "BUILDKITE",
    "TF_BUILD",
    "APPVEYOR",
    "TEAMCITY_VERSION",
    "PYTEST_CURRENT_TEST",
    "TESTING",
    "TOX_ENV_NAME",
    "CARGO_TARGET_TMPDIR",
    "NEXTEST",
];

/// Every hardcoded-answer branch and CI/test-env defeat device in one
/// file's Rust source, outside any `#[cfg(test)]`/`#[test]` scope.
/// Blocking.
pub fn anti_special_casing_findings(source: &str) -> Vec<(usize, &'static str, bool)> {
    let root = SupportLang::Rust.ast_grep(source);
    let mut findings = Vec::new();
    for node in root.root().dfs() {
        let hit = match node.kind().as_ref() {
            "if_expression" => is_hardcoded_answer_branch(&node),
            "call_expression" => is_test_env_read(&node),
            _ => false,
        };
        if hit && !in_test_scope(&node) {
            findings.push((node.start_pos().line().saturating_add(1), "ASP408", true));
        }
    }
    findings.sort_by(|a, b| a.0.cmp(&b.0));
    findings
}

/// Detector A: `if <a> == <specific literal>` whose consequence yields a
/// specific literal constant.
fn is_hardcoded_answer_branch<D: Doc>(if_expr: &Node<'_, D>) -> bool {
    let Some(cond) = if_expr.field("condition") else {
        return false;
    };
    if cond.kind() != "binary_expression" {
        return false;
    }
    if cond.field("operator").is_none_or(|op| op.kind() != "==") {
        return false;
    }
    let left_literal = cond.field("left").is_some_and(|n| is_specific_literal(&n));
    let right_literal = cond.field("right").is_some_and(|n| is_specific_literal(&n));
    if !(left_literal || right_literal) {
        return false;
    }
    if_expr
        .field("consequence")
        .is_some_and(|block| block_yields_specific_literal(&block))
}

/// Whether a `{ .. }` block's `return <expr>` statements or its tail
/// expression are a specific literal constant. Only the block's own
/// immediate statements/tail are inspected — a literal nested inside a
/// further `if`/`match`/loop is that inner construct's concern.
fn block_yields_specific_literal<D: Doc>(block: &Node<'_, D>) -> bool {
    for child in block.children() {
        match child.kind().as_ref() {
            "expression_statement" => {
                if let Some(inner) = child.children().next() {
                    if inner.kind() == "return_expression" && returns_specific_literal(&inner) {
                        return true;
                    }
                }
            }
            "return_expression" => {
                if returns_specific_literal(&child) {
                    return true;
                }
            }
            other => {
                // A tail expression that is itself a specific literal.
                if !is_punctuation(other) && is_specific_literal(&child) {
                    return true;
                }
            }
        }
    }
    false
}

/// Whether a `return_expression`'s value is a specific literal.
fn returns_specific_literal<D: Doc>(ret: &Node<'_, D>) -> bool {
    ret.children().any(|c| is_specific_literal(&c))
}

/// Whether `node` is a *specific* constant answer/input: a non-empty
/// string, a number other than the guard boundaries `0`/`1`, or a
/// non-empty collection literal. Booleans, `()`, chars, empty strings, and
/// `0`/`1` are trivial (guard sentinels) so ordinary guard clauses do not
/// trip the rule.
fn is_specific_literal<D: Doc>(node: &Node<'_, D>) -> bool {
    match node.kind().as_ref() {
        "string_literal" => node.children().any(|c| c.kind() == "string_content"),
        "raw_string_literal" => node.children().any(|c| c.kind() == "string_content"),
        "integer_literal" => is_specific_integer(node.text().as_ref()),
        "float_literal" => true,
        "array_expression" | "tuple_expression" => {
            node.children().any(|c| !is_punctuation(c.kind().as_ref()))
        }
        // A `vec![..]` / `[..; n]`-style constant answer: a non-empty
        // collection built by the `vec!` macro.
        "macro_invocation" => is_nonempty_vec_macro(node),
        _ => false,
    }
}

/// Whether `node` is a `vec![..]` macro with at least one element — a
/// non-empty collection literal answer. `vec![]` is the empty (trivial)
/// sentinel.
fn is_nonempty_vec_macro<D: Doc>(node: &Node<'_, D>) -> bool {
    if node
        .field("macro")
        .is_none_or(|m| m.text().as_ref() != "vec")
    {
        return false;
    }
    node.children().any(|child| {
        child.kind() == "token_tree" && child.children().any(|t| !is_punctuation(t.kind().as_ref()))
    })
}

/// Whether an integer literal names a value other than the guard
/// boundaries `0`/`1`. Type suffixes and digit separators are stripped
/// before the comparison; anything that is not exactly `0` or `1` is a
/// specific value.
fn is_specific_integer(text: &str) -> bool {
    let mut value: String = text.chars().filter(|c| *c != '_').collect();
    for suffix in [
        "isize", "usize", "i128", "u128", "i64", "u64", "i32", "u32", "i16", "u16", "i8", "u8",
    ] {
        if let Some(stripped) = value.strip_suffix(suffix) {
            value = stripped.to_string();
            break;
        }
    }
    value != "0" && value != "1"
}

fn is_punctuation(kind: &str) -> bool {
    matches!(kind, "(" | ")" | "[" | "]" | "," | "{" | "}")
}

/// Detector B: a `std::env::var`/`std::env::var_os` read whose first
/// string-literal argument is an unambiguous CI/test marker.
fn is_test_env_read<D: Doc>(call: &Node<'_, D>) -> bool {
    let Some(func) = call.field("function") else {
        return false;
    };
    let func_text = func.text();
    if !(func_text.ends_with("env::var") || func_text.ends_with("env::var_os")) {
        return false;
    }
    let Some(args) = call.field("arguments") else {
        return false;
    };
    for arg in args.children() {
        if arg.kind() == "string_literal" {
            let key = string_content(&arg);
            return TEST_ENV_MARKERS.contains(&key.as_str());
        }
    }
    false
}

/// The text between a string literal's quotes (its `string_content`), or
/// the empty string for an empty literal.
fn string_content<D: Doc>(literal: &Node<'_, D>) -> String {
    literal
        .children()
        .find(|c| c.kind() == "string_content")
        .map(|c| c.text().into_owned())
        .unwrap_or_default()
}

/// Whether `node` sits inside a `#[cfg(test)]` module or a `#[test]`
/// function — the test seam, where hardcoded fixtures are legitimate.
fn in_test_scope<D: Doc>(node: &Node<'_, D>) -> bool {
    let mut cursor = node.parent();
    while let Some(ancestor) = cursor {
        if matches!(ancestor.kind().as_ref(), "function_item" | "mod_item")
            && has_test_attribute(&ancestor)
        {
            return true;
        }
        cursor = ancestor.parent();
    }
    false
}

/// Whether the item is preceded by a `#[test]`/`#[cfg(test)]`-family
/// attribute. Walks the preceding-sibling attribute (and comment) run.
fn has_test_attribute<D: Doc>(item: &Node<'_, D>) -> bool {
    let mut prev = item.prev();
    while let Some(sibling) = prev {
        match sibling.kind().as_ref() {
            "attribute_item" => {
                if attribute_is_test(sibling.text().as_ref()) {
                    return true;
                }
            }
            "line_comment" | "block_comment" => {}
            _ => break,
        }
        prev = sibling.prev();
    }
    false
}

/// Whether an attribute's source denotes a test scope. Whitespace is
/// removed, then any `test` token (`#[test]`, `#[tokio::test]`,
/// `#[cfg(test)]`, `#[cfg(all(test, ..))]`) marks the scope. Over-matching
/// only suppresses findings (a conservative false negative), never adds
/// one.
fn attribute_is_test(text: &str) -> bool {
    text.chars()
        .filter(|c| !c.is_whitespace())
        .collect::<String>()
        .contains("test")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lines(source: &str) -> Vec<usize> {
        anti_special_casing_findings(source)
            .into_iter()
            .map(|(line, _, _)| line)
            .collect()
    }

    #[test]
    fn flags_hardcoded_answer_branch_string_in_collection_out() {
        // The load-bearing snake-gaming stub: a specific input mapped to a
        // specific canned board.
        let src = "fn next_state(board: Board, mv: &str) -> Board {\n    if mv == \"UP\" {\n        return vec![[0, 0, 0], [0, 1, 0]];\n    }\n    board\n}\n";
        assert_eq!(lines(src), vec![2]);
    }

    #[test]
    fn flags_hardcoded_answer_branch_number_in_string_out() {
        let src = "fn lookup(code: u32) -> &'static str {\n    if code == 404 {\n        return \"canned\";\n    }\n    real(code)\n}\n";
        assert_eq!(lines(src), vec![2]);
    }

    #[test]
    fn flags_tail_expression_literal_answer() {
        let src = "fn step(mv: &str) -> Vec<u8> {\n    if mv == \"UP\" { vec![1, 2, 3] } else { compute(mv) }\n}\n";
        assert_eq!(lines(src), vec![2]);
    }

    #[test]
    fn flags_ci_env_defeat_device() {
        let src = "fn compute(x: i64) -> i64 {\n    if std::env::var(\"CI\").is_ok() {\n        return 42;\n    }\n    x * x\n}\n";
        // Both the env read (line 2) and the hardcoded 42 return would be
        // eligible, but `42` sits behind a non-`==` condition, so only the
        // env-var defeat device fires.
        assert_eq!(lines(src), vec![2]);
    }

    #[test]
    fn ignores_guard_returning_trivial_sentinel() {
        let src = "fn f(n: u32) -> Option<u32> {\n    if n == 42 {\n        return None;\n    }\n    Some(g(n))\n}\n";
        assert!(lines(src).is_empty());
    }

    #[test]
    fn ignores_branch_that_computes() {
        let src = "fn route(status: &str) -> Profile {\n    if status == \"active\" {\n        return build_profile(status);\n    }\n    default()\n}\n";
        assert!(lines(src).is_empty());
    }

    #[test]
    fn ignores_boundary_literal_zero() {
        let src = "fn f(x: i64) -> i64 {\n    if x == 0 {\n        return 0;\n    }\n    h(x)\n}\n";
        assert!(lines(src).is_empty());
    }

    #[test]
    fn ignores_match_dispatch_table() {
        // A literal-keyed match is a legitimate lookup table, not a
        // special-case: never flagged.
        let src = "fn name(code: u32) -> &'static str {\n    match code {\n        404 => \"Not Found\",\n        500 => \"Server Error\",\n        _ => \"Unknown\",\n    }\n}\n";
        assert!(lines(src).is_empty());
    }

    #[test]
    fn ignores_non_test_env_var() {
        let src =
            "fn cfg() -> Result<String, VarError> {\n    std::env::var(\"DATABASE_URL\")\n}\n";
        assert!(lines(src).is_empty());
    }

    #[test]
    fn exempts_cfg_test_module() {
        let src = "#[cfg(test)]\nmod tests {\n    fn stub(mv: &str) -> u32 {\n        if mv == \"UP\" { return 99; }\n        0\n    }\n}\n";
        assert!(lines(src).is_empty());
    }
}
