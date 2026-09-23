//! Whole-workspace Rust duplicate-function detector (functional core).
//!
//! Mirrors `python/src/aspergillus/duplicates.py`'s whole-body type-2 clone
//! normalization: every VARIABLE-position identifier collapses to one
//! placeholder, while every distinguishing token stays exact - literal
//! values, called-function names, macro names, and field/method names. Two
//! functions that differ only in their own name and their variable names
//! normalize identically; two functions that differ in a literal value do
//! not. Detection is deterministic and threshold-free, matching the Python
//! reference. Pebble: asp-ce6.3.
//!
//! No file, process, or exit code appears here - those live in the binary
//! at `src/bin/aspergillus_rust_dup_check.rs`.

use std::collections::{HashMap, HashSet};

use ast_grep_core::tree_sitter::StrDoc;
use ast_grep_core::Node;
use ast_grep_language::{LanguageExt, SupportLang};

use crate::Finding;

/// The ASP id every finding of this check reports.
pub const RULE_ID: &str = "ASP501";

/// A function's normalization collapses every variable-position
/// `identifier` leaf to this one placeholder, matching the Python
/// reference's `_NAME_PLACEHOLDER`.
const IDENTIFIER_PLACEHOLDER: &str = "_ID";

/// One `function_item` occurrence: a file, its 1-based start line, its
/// line span, and its type-2 normalized body.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FunctionOccurrence {
    /// The file, relative to the scanned workspace root.
    pub path: String,
    /// The 1-based line the function starts on.
    pub line: usize,
    /// The function's line span, start to end inclusive.
    pub n_lines: usize,
    /// The function's whole normalized text (signature and body).
    pub normalized_body: String,
}

type RNode<'r> = Node<'r, StrDoc<SupportLang>>;

fn is_leaf(node: &RNode<'_>) -> bool {
    node.children().next().is_none()
}

/// Marks every `identifier` node, anywhere under `node`, that names a
/// called function or invoked macro - these stay exact rather than
/// collapsing to the placeholder, matching the Python reference's
/// protection of called-function names.
fn mark_callee_identifiers(node: &RNode<'_>, protected: &mut HashSet<usize>) {
    match node.kind().as_ref() {
        "call_expression" | "generic_function" => {
            if let Some(callee) = node.field("function") {
                mark_name_path(&callee, protected);
            }
        }
        "macro_invocation" => {
            if let Some(name) = node.field("macro") {
                mark_name_path(&name, protected);
            }
        }
        _ => {}
    }
    for child in node.children() {
        mark_callee_identifiers(&child, protected);
    }
}

/// Marks every `identifier` leaf inside a callee or macro name path: a
/// bare `identifier`, or a `::`-joined `scoped_identifier` chain. Stops at
/// a `field_expression` (a method call target, e.g. `x.method()`): its
/// `field_identifier` is already a distinct node kind kept exact by
/// default, and its `value` (the receiver) is a normal expression whose
/// identifiers still collapse - matching the Python reference, where only
/// the attribute name of `x.method()` is protected, not `x` itself.
fn mark_name_path(node: &RNode<'_>, protected: &mut HashSet<usize>) {
    match node.kind().as_ref() {
        "identifier" => {
            protected.insert(node.node_id());
        }
        "scoped_identifier" => {
            for child in node.children() {
                mark_name_path(&child, protected);
            }
        }
        _ => {}
    }
}

/// Renders `node` as a type-2 normalized token string: every
/// variable-position `identifier` leaf collapses to one placeholder,
/// while every other token - literals, keywords, punctuation, type
/// names, field names, and callee/macro names - stays exact.
fn normalize(node: &RNode<'_>) -> String {
    let mut protected = HashSet::new();
    mark_callee_identifiers(node, &mut protected);
    let mut tokens = Vec::new();
    render(node, &protected, &mut tokens);
    tokens.join(" ")
}

fn render(node: &RNode<'_>, protected: &HashSet<usize>, tokens: &mut Vec<String>) {
    if is_leaf(node) {
        let piece = if node.kind().as_ref() == "identifier" && !protected.contains(&node.node_id())
        {
            IDENTIFIER_PLACEHOLDER.to_string()
        } else {
            node.text().into_owned()
        };
        tokens.push(piece);
        return;
    }
    for child in node.children() {
        render(&child, protected, tokens);
    }
}

/// Every `function_item` in an already-read Rust source, with its 1-based
/// start line and type-2 normalized body. A function whose line span is
/// under `min_lines` is excluded - matching the Python reference's
/// `--min-lines` floor (default 5), which keeps a trivial one-line getter
/// from seeding a spurious clone report.
pub fn function_occurrences(path: &str, source: &str, min_lines: usize) -> Vec<FunctionOccurrence> {
    let root = SupportLang::Rust.ast_grep(source);
    root.root()
        .dfs()
        .filter(|node| node.kind().as_ref() == "function_item")
        .filter_map(|node| {
            let start = node.start_pos().line().saturating_add(1);
            let end = node.end_pos().line().saturating_add(1);
            let n_lines = end.saturating_sub(start).saturating_add(1);
            if n_lines < min_lines {
                return None;
            }
            Some(FunctionOccurrence {
                path: path.to_string(),
                line: start,
                n_lines,
                normalized_body: normalize(&node),
            })
        })
        .collect()
}

/// Groups occurrences, across every scanned file, by identical normalized
/// body. Only buckets with more than one member are a duplicate pair -
/// a function with a unique body reports nothing. Groups are returned
/// sorted by their first member's path then line, for deterministic
/// output; members within a group are sorted the same way.
pub fn duplicate_groups(occurrences: &[FunctionOccurrence]) -> Vec<Vec<FunctionOccurrence>> {
    let mut buckets: HashMap<&str, Vec<&FunctionOccurrence>> = HashMap::new();
    for occurrence in occurrences {
        buckets
            .entry(occurrence.normalized_body.as_str())
            .or_default()
            .push(occurrence);
    }

    let mut groups: Vec<Vec<FunctionOccurrence>> = buckets
        .into_values()
        .filter(|members| members.len() > 1)
        .map(|members| {
            let mut members: Vec<FunctionOccurrence> = members.into_iter().cloned().collect();
            members.sort_by(|a, b| a.path.cmp(&b.path).then(a.line.cmp(&b.line)));
            members
        })
        .collect();

    groups.sort_by(|a, b| a[0].path.cmp(&b[0].path).then(a[0].line.cmp(&b[0].line)));
    groups
}

/// Every duplicate group rendered as one blocking `Finding` per member,
/// sorted by path then line.
pub fn findings_for_groups(groups: &[Vec<FunctionOccurrence>]) -> Vec<Finding> {
    let mut findings: Vec<Finding> = groups
        .iter()
        .flatten()
        .map(|occurrence| Finding {
            path: occurrence.path.clone(),
            line: occurrence.line,
            rule_id: RULE_ID.to_string(),
            blocking: true,
        })
        .collect();
    findings.sort_by(|a, b| a.path.cmp(&b.path).then(a.line.cmp(&b.line)));
    findings
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn two_functions_differing_only_in_names_are_one_duplicate_group() {
        let source = r#"
fn add_totals(first: i32, second: i32) -> i32 {
    let sum = first + second;
    let doubled = sum * 2;
    doubled
}

fn sum_pair(left: i32, right: i32) -> i32 {
    let total = left + right;
    let scaled = total * 2;
    scaled
}
"#;
        let occurrences = function_occurrences("lib.rs", source, 3);
        assert_eq!(occurrences.len(), 2);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0].len(), 2);
    }

    #[test]
    fn functions_differing_by_one_literal_are_not_a_duplicate_group() {
        let source = r#"
fn add_totals(first: i32, second: i32) -> i32 {
    let sum = first + second;
    let doubled = sum * 2;
    doubled
}

fn add_totals_tripled(first: i32, second: i32) -> i32 {
    let sum = first + second;
    let tripled = sum * 3;
    tripled
}
"#;
        let occurrences = function_occurrences("lib.rs", source, 3);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups, Vec::<Vec<FunctionOccurrence>>::new());
    }

    #[test]
    fn a_called_function_name_stays_exact_so_different_callees_do_not_match() {
        let one = function_occurrences(
            "a.rs",
            "fn f(x: i32) -> i32 {\n    let y = helper_one(x);\n    y\n}\n",
            3,
        );
        let two = function_occurrences(
            "b.rs",
            "fn g(x: i32) -> i32 {\n    let y = helper_two(x);\n    y\n}\n",
            3,
        );
        let mut occurrences = one;
        occurrences.extend(two);
        assert_eq!(
            duplicate_groups(&occurrences),
            Vec::<Vec<FunctionOccurrence>>::new()
        );
    }

    #[test]
    fn a_field_access_name_stays_exact_so_different_field_names_do_not_match() {
        let one = function_occurrences(
            "a.rs",
            "fn f(item: Widget) -> i32 {\n    let y = item.width;\n    y\n}\n",
            3,
        );
        let two = function_occurrences(
            "b.rs",
            "fn g(item: Widget) -> i32 {\n    let y = item.height;\n    y\n}\n",
            3,
        );
        let mut occurrences = one;
        occurrences.extend(two);
        assert_eq!(
            duplicate_groups(&occurrences),
            Vec::<Vec<FunctionOccurrence>>::new()
        );
    }

    #[test]
    fn a_duplicate_pair_split_across_two_files_is_one_group() {
        let one = function_occurrences(
            "crate-a/src/lib.rs",
            "fn a_calc(x: i32) -> i32 {\n    let y = x + 1;\n    y * 2\n}\n",
            3,
        );
        let two = function_occurrences(
            "crate-b/src/lib.rs",
            "fn b_calc(n: i32) -> i32 {\n    let m = n + 1;\n    m * 2\n}\n",
            3,
        );
        let mut occurrences = one;
        occurrences.extend(two);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups.len(), 1);
        let paths: HashSet<&str> = groups[0].iter().map(|o| o.path.as_str()).collect();
        assert_eq!(paths.len(), 2);
    }

    #[test]
    fn a_function_under_min_lines_is_excluded() {
        let occurrences = function_occurrences("lib.rs", "fn f() -> i32 {\n    1\n}\n", 5);
        assert_eq!(occurrences, Vec::new());
    }

    #[test]
    fn findings_render_as_path_line_asp_code() {
        let groups = vec![vec![
            FunctionOccurrence {
                path: "a.rs".to_string(),
                line: 3,
                n_lines: 4,
                normalized_body: "same".to_string(),
            },
            FunctionOccurrence {
                path: "b.rs".to_string(),
                line: 7,
                n_lines: 4,
                normalized_body: "same".to_string(),
            },
        ]];
        let findings = findings_for_groups(&groups);
        let rendered: Vec<String> = findings.iter().map(Finding::render).collect();
        assert_eq!(rendered, vec!["a.rs:3: ASP501", "b.rs:7: ASP501"]);
    }
}
