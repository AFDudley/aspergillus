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

use std::collections::{BTreeMap, HashMap, HashSet};

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

/// The default minimum line span a whole function or a duplicated statement
/// window must cover to be reported - the shell's `--min-lines` floor, kept
/// here so both the whole-body and the spine paths share one meaning.
pub const DEFAULT_MIN_LINES: usize = 5;

/// The default minimum number of consecutive top-level statements a
/// duplicated spine window must contain to be reported. A copied run this
/// long, still exact after type-2 normalization, is deliberate reuse worth
/// hoisting; anything shorter is too incidental to distinguish from two
/// functions that merely open the same way.
pub const DEFAULT_MIN_STATEMENTS: usize = 3;

/// Joined between a window's per-statement normalized texts before it is
/// keyed. A NUL never appears in rendered Rust, so it cannot let two
/// distinct spines collide.
const STATEMENT_SEPARATOR: char = '\u{0}';

/// One top-level statement of a function body, rendered under the same
/// type-2 normalization the whole-body signature uses, with its source
/// span. The `text` sequence across a function is its statement SPINE - the
/// unit the sliding-window fragment detector compares.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NormalizedStatement {
    /// The statement's type-2 normalized text.
    pub text: String,
    /// The 1-based line the statement starts on.
    pub start_line: usize,
    /// The 1-based line the statement ends on.
    pub end_line: usize,
}

/// One `function_item` occurrence: a file, its 1-based start line, its
/// line span, its type-2 normalized whole body, and its statement spine.
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
    /// The function's top-level body statements, each type-2 normalized,
    /// in source order - the spine the fragment detector slides over.
    pub statements: Vec<NormalizedStatement>,
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

/// The function's top-level body statements, each type-2 normalized. The
/// body `block`'s braces and any attached comments are dropped so the
/// sequence is exactly the executable spine; the trailing tail expression
/// (a block's final value) counts as a statement, since a copied run that
/// ends in one is still copied code.
fn statement_spine(function: &RNode<'_>) -> Vec<NormalizedStatement> {
    let Some(body) = function.field("body") else {
        return Vec::new();
    };
    body.children()
        .filter(|child| {
            !matches!(
                child.kind().as_ref(),
                "{" | "}" | "line_comment" | "block_comment"
            )
        })
        .map(|statement| NormalizedStatement {
            text: normalize(&statement),
            start_line: statement.start_pos().line().saturating_add(1),
            end_line: statement.end_pos().line().saturating_add(1),
        })
        .collect()
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
                statements: statement_spine(&node),
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

/// Whether the window `[start, end)` sits entirely inside a spine run this
/// function already reported - if so it is a piece of a longer clone, not a
/// separate one, so the longest-first scan skips it.
fn window_covered(covered: &[(usize, usize)], start: usize, end: usize) -> bool {
    covered.iter().any(|&(lo, hi)| lo <= start && end <= hi)
}

/// Every duplicated statement-spine FRAGMENT across the scanned functions,
/// as one blocking `Finding` per member at the window's first-statement
/// line.
///
/// This complements `duplicate_groups`, which requires a whole normalized
/// body to match: a copied run of statements embedded in two otherwise
/// different functions leaves their whole-body hashes distinct, so only a
/// sliding window over the statement spine can see it. Windows are scanned
/// longest-first; once a run is reported, any shorter window fully inside
/// it, for the same function, is skipped so a maximal spine is reported
/// once. `already_whole` names `(path, line)` pairs already reported as
/// whole-body clones; their full spine is pre-marked covered so a fragment
/// never restates a whole-body finding.
///
/// A window qualifies only when at least two DISTINCT functions share it,
/// it spans at least `min_lines` source lines, and it is at least
/// `min_statements` statements long. Matches stay exact under type-2
/// normalization (identifier renaming and literal values only), matching
/// the whole-body equivalence, which keeps the fragment path as FP-averse.
fn fragment_findings(
    occurrences: &[FunctionOccurrence],
    min_lines: usize,
    min_statements: usize,
    already_whole: &HashSet<(&str, usize)>,
) -> Vec<Finding> {
    let candidates: Vec<&FunctionOccurrence> = occurrences
        .iter()
        .filter(|occ| occ.statements.len() >= min_statements)
        .collect();
    let Some(max_len) = candidates.iter().map(|occ| occ.statements.len()).max() else {
        return Vec::new();
    };

    let mut covered: HashMap<usize, Vec<(usize, usize)>> = HashMap::new();
    for (index, occ) in candidates.iter().enumerate() {
        if already_whole.contains(&(occ.path.as_str(), occ.line)) {
            covered.insert(index, vec![(0, occ.statements.len())]);
        }
    }

    let mut findings: Vec<Finding> = Vec::new();
    for length in (min_statements..=max_len).rev() {
        // Bucket every not-yet-covered window of this length by its joined
        // normalized spine text.
        let mut buckets: BTreeMap<String, Vec<(usize, usize)>> = BTreeMap::new();
        for (index, occ) in candidates.iter().enumerate() {
            let n = occ.statements.len();
            if n < length {
                continue;
            }
            let owned = covered.get(&index);
            for start in 0..=(n - length) {
                let end = start + length;
                if owned.is_some_and(|runs| window_covered(runs, start, end)) {
                    continue;
                }
                let key = occ.statements[start..end]
                    .iter()
                    .map(|statement| statement.text.as_str())
                    .collect::<Vec<&str>>()
                    .join(&STATEMENT_SEPARATOR.to_string());
                buckets.entry(key).or_default().push((index, start));
            }
        }

        for occs in buckets.values() {
            // One window per function: a function whose own body repeats a
            // block is a different defect, out of scope here. First start wins.
            let mut by_function: BTreeMap<usize, usize> = BTreeMap::new();
            for &(index, start) in occs {
                by_function.entry(index).or_insert(start);
            }
            if by_function.len() < 2 {
                continue;
            }
            let n_lines = by_function
                .iter()
                .map(|(&index, &start)| {
                    let spine = &candidates[index].statements;
                    spine[start + length - 1].end_line - spine[start].start_line + 1
                })
                .max()
                .unwrap_or(0);
            if n_lines < min_lines {
                continue;
            }
            for (&index, &start) in &by_function {
                let occ = candidates[index];
                findings.push(Finding {
                    path: occ.path.clone(),
                    line: occ.statements[start].start_line,
                    rule_id: RULE_ID.to_string(),
                    blocking: true,
                });
                covered
                    .entry(index)
                    .or_default()
                    .push((start, start + length));
            }
        }
    }

    findings.sort_by(|a, b| a.path.cmp(&b.path).then(a.line.cmp(&b.line)));
    findings
}

/// Every ASP501 finding for the scanned functions: whole-body clones
/// (`duplicate_groups`) plus embedded statement-spine fragments
/// (`fragment_findings`), merged and de-duplicated by `(path, line)`.
///
/// The whole-body path is unchanged; the fragment path only ever adds
/// findings a whole-body hash cannot see. `min_lines` and `min_statements`
/// are the shared floors; pass `DEFAULT_MIN_LINES` / `DEFAULT_MIN_STATEMENTS`
/// for the shell's defaults.
pub fn duplicate_findings(
    occurrences: &[FunctionOccurrence],
    min_lines: usize,
    min_statements: usize,
) -> Vec<Finding> {
    let groups = duplicate_groups(occurrences);
    let already_whole: HashSet<(&str, usize)> = groups
        .iter()
        .flatten()
        .map(|occ| (occ.path.as_str(), occ.line))
        .collect();

    let mut findings = findings_for_groups(&groups);
    findings.extend(fragment_findings(
        occurrences,
        min_lines,
        min_statements,
        &already_whole,
    ));

    let mut seen: HashSet<(String, usize)> = HashSet::new();
    findings.retain(|finding| seen.insert((finding.path.clone(), finding.line)));
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
                statements: Vec::new(),
            },
            FunctionOccurrence {
                path: "b.rs".to_string(),
                line: 7,
                n_lines: 4,
                normalized_body: "same".to_string(),
                statements: Vec::new(),
            },
        ]];
        let findings = findings_for_groups(&groups);
        let rendered: Vec<String> = findings.iter().map(Finding::render).collect();
        assert_eq!(rendered, vec!["a.rs:3: ASP501", "b.rs:7: ASP501"]);
    }

    // Two functions whose whole bodies differ (distinct first and last
    // statements) but which share an identical 3-statement run in the
    // middle. A whole-body hash cannot see this; the spine window must.
    const FRAGMENT_LEFT: &str = r#"
fn compute_left(input: &[u32]) -> u32 {
    let label = 10;
    let mut total = 0;
    for item in input {
        total += item;
    }
    total = total * 2;
    total + label
}
"#;
    const FRAGMENT_RIGHT: &str = r#"
fn compute_right(values: &[u32]) -> u32 {
    let name = other_fn();
    let mut total = 0;
    for item in values {
        total += item;
    }
    total = total * 2;
    finalize(total)
}
"#;

    fn occurrences_from(sources: &[(&str, &str)]) -> Vec<FunctionOccurrence> {
        let mut occurrences = Vec::new();
        for (path, source) in sources {
            occurrences.extend(function_occurrences(path, source, DEFAULT_MIN_LINES));
        }
        occurrences
    }

    #[test]
    fn an_embedded_statement_spine_shared_by_two_functions_is_a_fragment_finding() {
        let occurrences = occurrences_from(&[("a.rs", FRAGMENT_LEFT), ("b.rs", FRAGMENT_RIGHT)]);
        // No whole-body clone: the bodies differ at their ends.
        assert!(duplicate_groups(&occurrences).is_empty());
        let findings = duplicate_findings(&occurrences, DEFAULT_MIN_LINES, DEFAULT_MIN_STATEMENTS);
        let rendered: Vec<String> = findings.iter().map(Finding::render).collect();
        // Reported at the window's first statement (`let mut total = 0;`),
        // not at either function's signature line.
        assert_eq!(rendered, vec!["a.rs:4: ASP501", "b.rs:4: ASP501"]);
    }

    #[test]
    fn a_shared_run_shorter_than_the_statement_floor_is_not_a_fragment() {
        // The shared run here is only the two `let`-and-loop statements; the
        // trailing statement differs, so the spine is length 2 < 3.
        let left = r#"
fn only_two_left(input: &[u32]) -> u32 {
    let seed = first_source();
    let mut total = 0;
    for item in input {
        total += item;
    }
    total + 1
}
"#;
        let right = r#"
fn only_two_right(values: &[u32]) -> u32 {
    let seed = second_source();
    let mut total = 0;
    for item in values {
        total += item;
    }
    finalize(total)
}
"#;
        let occurrences = occurrences_from(&[("a.rs", left), ("b.rs", right)]);
        let findings = duplicate_findings(&occurrences, DEFAULT_MIN_LINES, DEFAULT_MIN_STATEMENTS);
        assert_eq!(findings, Vec::new());
    }

    #[test]
    fn distinct_functions_share_no_spine_and_report_nothing() {
        let left = r#"
fn render_widths(items: &[Widget]) -> u32 {
    let mut total = 0;
    for item in items {
        total += item.width;
    }
    total
}
"#;
        let right = r#"
fn join_labels(rows: &[Row]) -> String {
    let mut out = String::new();
    for row in rows {
        out.push_str(&row.label);
    }
    out
}
"#;
        let occurrences = occurrences_from(&[("a.rs", left), ("b.rs", right)]);
        let findings = duplicate_findings(&occurrences, DEFAULT_MIN_LINES, DEFAULT_MIN_STATEMENTS);
        assert_eq!(findings, Vec::new());
    }

    #[test]
    fn a_whole_body_clone_reports_once_and_is_not_restated_as_a_fragment() {
        let source = r#"
fn add_totals(first: i32, second: i32) -> i32 {
    let sum = first + second;
    let doubled = sum * 2;
    let adjusted = doubled + 1;
    adjusted
}

fn sum_pair(left: i32, right: i32) -> i32 {
    let total = left + right;
    let scaled = total * 2;
    let tuned = scaled + 1;
    tuned
}
"#;
        let occurrences = occurrences_from(&[("lib.rs", source)]);
        let findings = duplicate_findings(&occurrences, DEFAULT_MIN_LINES, DEFAULT_MIN_STATEMENTS);
        let rendered: Vec<String> = findings.iter().map(Finding::render).collect();
        // One finding per function, at the signature line - the whole-body
        // path only. The fragment path does not restate the same pair.
        assert_eq!(rendered, vec!["lib.rs:2: ASP501", "lib.rs:9: ASP501"]);
    }
}
