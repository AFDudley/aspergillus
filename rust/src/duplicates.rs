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

/// The type-ERASED normalization additionally collapses every distinguishing
/// TYPE or constructor name - a kept-exact identifier or `type_identifier`
/// that is UpperCamelCase by Rust convention - to this placeholder. Two
/// functions whose only difference is the newtype they construct (e.g.
/// `InstructionCount::new` vs `LookupCount::new`) then normalize identically
/// under type erasure while staying distinct under the exact normalization -
/// the signature of a parallel typed variant, not a copied block.
const TYPE_PLACEHOLDER: &str = "_TYPE";

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

/// The idiomatic ROLE a top-level statement plays, insofar as the spine
/// pass cares. Only the three shapes of the guard/copy/sort preamble are
/// distinguished; every other statement is `Other`. A window that is
/// exactly `[EarlyReturnGuard, SliceCopy, Sort]` is the common
/// "bail-if-empty, take a sorted copy" idiom two analytics routines share
/// by coincidence, never a deliberately copied block worth one helper.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StatementRole {
    /// `if <cond> { return <expr>; }` with no `else` - an early-return guard.
    EarlyReturnGuard,
    /// `let <pat> = <expr>.to_vec();` - a defensive slice copy.
    SliceCopy,
    /// `<expr>.sort...(...);` - an in-place sort.
    Sort,
    /// Any statement the preamble idiom does not name.
    Other,
}

/// One top-level statement of a function body, rendered under the same
/// type-2 normalization the whole-body signature uses, with its source
/// span. The `text` sequence across a function is its statement SPINE - the
/// unit the sliding-window fragment detector compares.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NormalizedStatement {
    /// The statement's type-2 normalized text.
    pub text: String,
    /// The idiomatic role this statement plays in a shared preamble.
    pub role: StatementRole,
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
    /// The function's whole text under TYPE-ERASED normalization: as
    /// `normalized_body`, but with every UpperCamelCase type/constructor
    /// name collapsed too. Two occurrences sharing this string differ only
    /// in the types they name - parallel typed variants, whose shared spine
    /// windows a single helper could not hoist without erasing a newtype.
    pub type_erased_body: String,
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
    render_normalized(node, false)
}

/// Renders `node` under TYPE-ERASED normalization: as `normalize`, but
/// every kept-exact UpperCamelCase token - a type name, enum/struct
/// constructor, or `Self` - collapses to `_TYPE` as well. Two functions
/// that differ only in the newtype they construct share this rendering yet
/// stay distinct under `normalize`.
fn normalize_type_erased(node: &RNode<'_>) -> String {
    render_normalized(node, true)
}

fn render_normalized(node: &RNode<'_>, erase_types: bool) -> String {
    let mut protected = HashSet::new();
    mark_callee_identifiers(node, &mut protected);
    let mut tokens = Vec::new();
    render(node, &protected, erase_types, &mut tokens);
    tokens.join(" ")
}

/// Whether a kept-exact token names a type or constructor: a
/// `type_identifier` leaf, or any token whose first character is an ASCII
/// uppercase letter (Rust's UpperCamelCase convention for types, enum
/// variants, and struct constructors). Variable-position identifiers have
/// already collapsed to `_ID` before this is consulted, and `SCREAMING`
/// consts render as `_ID` too, so only genuine type/constructor names reach
/// the uppercase test.
fn is_type_token(node: &RNode<'_>, text: &str) -> bool {
    node.kind().as_ref() == "type_identifier"
        || text.chars().next().is_some_and(|c| c.is_ascii_uppercase())
}

fn render(
    node: &RNode<'_>,
    protected: &HashSet<usize>,
    erase_types: bool,
    tokens: &mut Vec<String>,
) {
    if is_leaf(node) {
        let piece = if node.kind().as_ref() == "identifier" && !protected.contains(&node.node_id())
        {
            IDENTIFIER_PLACEHOLDER.to_string()
        } else {
            let text = node.text();
            if erase_types && is_type_token(node, &text) {
                TYPE_PLACEHOLDER.to_string()
            } else {
                text.into_owned()
            }
        };
        tokens.push(piece);
        return;
    }
    for child in node.children() {
        render(&child, protected, erase_types, tokens);
    }
}

/// The inner expression of an `expression_statement`, or `node` itself when
/// it is not one. The trailing `;` and any comments are skipped.
fn statement_expression<'r>(node: &RNode<'r>) -> Option<RNode<'r>> {
    if node.kind().as_ref() == "expression_statement" {
        node.children().find(|child| {
            !matches!(
                child.kind().as_ref(),
                ";" | "line_comment" | "block_comment"
            )
        })
    } else {
        Some(node.clone())
    }
}

/// Whether `expr` is a method call `<receiver>.<name>(...)` whose method
/// name is one of `names`.
fn is_method_call(expr: &RNode<'_>, names: &[&str]) -> bool {
    if expr.kind().as_ref() != "call_expression" {
        return false;
    }
    let Some(function) = expr.field("function") else {
        return false;
    };
    if function.kind().as_ref() != "field_expression" {
        return false;
    }
    function.field("field").is_some_and(|field| {
        field.kind().as_ref() == "field_identifier" && names.contains(&field.text().as_ref())
    })
}

/// Whether `node` is `if <cond> { return <expr>; }` with no `else` - an
/// early-return guard whose sole effect is to bail out.
fn is_early_return_guard(node: &RNode<'_>) -> bool {
    let Some(expr) = statement_expression(node) else {
        return false;
    };
    if expr.kind().as_ref() != "if_expression" || expr.field("alternative").is_some() {
        return false;
    }
    let Some(block) = expr.field("consequence") else {
        return false;
    };
    let mut inner = block.children().filter(|child| {
        !matches!(
            child.kind().as_ref(),
            "{" | "}" | "line_comment" | "block_comment"
        )
    });
    let Some(only) = inner.next() else {
        return false;
    };
    if inner.next().is_some() {
        return false;
    }
    statement_expression(&only).is_some_and(|e| e.kind().as_ref() == "return_expression")
}

/// Whether `node` is `let <pat> = <expr>.to_vec();` - a defensive copy of a
/// slice into an owned, sortable `Vec`.
fn is_slice_copy(node: &RNode<'_>) -> bool {
    node.kind().as_ref() == "let_declaration"
        && node
            .field("value")
            .is_some_and(|value| is_method_call(&value, &["to_vec"]))
}

/// Whether `node` is an in-place sort call `<expr>.sort...(...);`.
fn is_sort(node: &RNode<'_>) -> bool {
    statement_expression(node).is_some_and(|expr| {
        is_method_call(
            &expr,
            &[
                "sort",
                "sort_by",
                "sort_unstable",
                "sort_by_key",
                "sort_unstable_by",
                "sort_unstable_by_key",
            ],
        )
    })
}

/// Classifies a top-level statement into the one preamble role it plays, or
/// `Other`. Only the guard/copy/sort shapes are named; the sliding-window
/// pass uses them to recognize the "bail-if-empty, take a sorted copy"
/// idiom two routines share by coincidence.
fn classify_statement(node: &RNode<'_>) -> StatementRole {
    if is_early_return_guard(node) {
        StatementRole::EarlyReturnGuard
    } else if is_slice_copy(node) {
        StatementRole::SliceCopy
    } else if is_sort(node) {
        StatementRole::Sort
    } else {
        StatementRole::Other
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
            role: classify_statement(&statement),
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
                type_erased_body: normalize_type_erased(&node),
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

/// Whether `window` is exactly the guard/copy/sort preamble idiom:
/// `if <empty> { return … }; let <v> = <slice>.to_vec(); <v>.sort…();`.
/// This three-statement opener is shared by unrelated slice-statistics
/// routines as convention, not as a deliberately copied block.
fn is_sort_preamble_idiom(window: &[NormalizedStatement]) -> bool {
    matches!(
        window,
        [guard, copy, sort]
            if guard.role == StatementRole::EarlyReturnGuard
                && copy.role == StatementRole::SliceCopy
                && sort.role == StatementRole::Sort
    )
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
///
/// Two further precision gates keep short coincidental spines from being
/// reported as clones. A window shared only by PARALLEL TYPED VARIANTS -
/// functions with one identical type-ERASED whole body, so their sole
/// difference is the newtype they construct - is skipped: a single helper
/// could not replace them without erasing that type. And a window that is
/// exactly the guard/copy/sort PREAMBLE IDIOM (`if empty return; let v =
/// s.to_vec(); v.sort…()`) is skipped: unrelated slice-statistics routines
/// share it by convention, not by copying.
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
            // Parallel typed variants: if every function sharing this window
            // has the same TYPE-ERASED whole body, they differ only in the
            // types they name (e.g. two `push` methods whose sole difference
            // is the count newtype they construct). One helper could not
            // replace them without erasing that newtype, so their shared
            // spine is not a clone worth hoisting.
            let (&rep_index, &rep_start) = by_function.iter().next().expect("len >= 2 checked");
            let variant_signature = candidates[rep_index].type_erased_body.as_str();
            if by_function
                .keys()
                .all(|&index| candidates[index].type_erased_body == variant_signature)
            {
                continue;
            }
            // Common preamble idiom: `if empty return; sorted = copy; sort`.
            // Two analytics routines that compute unrelated statistics share
            // this three-statement opener by coincidence; hoisting it needs a
            // cross-module `sorted_copy` helper for three trivial lines.
            if is_sort_preamble_idiom(
                &candidates[rep_index].statements[rep_start..rep_start + length],
            ) {
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
                type_erased_body: "same".to_string(),
                statements: Vec::new(),
            },
            FunctionOccurrence {
                path: "b.rs".to_string(),
                line: 7,
                n_lines: 4,
                normalized_body: "same".to_string(),
                type_erased_body: "same".to_string(),
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

    #[test]
    fn parallel_typed_variants_differing_only_in_a_constructor_are_not_a_fragment() {
        // Two `push` methods identical but for the count newtype each
        // constructs; their shared four-statement spine is not a clone one
        // helper could hoist without erasing that newtype.
        let source = r#"
fn push_a(&mut self, span: SpanA) -> Result<(), Refusal> {
    let at = usize::from(self.count.get());
    let slot = self.spans.get_mut(at).ok_or(Refusal::Full)?;
    *slot = span;
    let next = self
        .count
        .get()
        .checked_add(1)
        .ok_or(Refusal::Full)?;
    self.count = CountA::new(next);
    Ok(())
}

fn push_b(&mut self, span: SpanB) -> Result<(), Refusal> {
    let at = usize::from(self.count.get());
    let slot = self.spans.get_mut(at).ok_or(Refusal::Full)?;
    *slot = span;
    let next = self
        .count
        .get()
        .checked_add(1)
        .ok_or(Refusal::Full)?;
    self.count = CountB::new(next);
    Ok(())
}
"#;
        let occurrences = occurrences_from(&[("wire.rs", source)]);
        // The count newtypes differ, so there is no whole-body clone.
        assert!(duplicate_groups(&occurrences).is_empty());
        let findings = duplicate_findings(&occurrences, DEFAULT_MIN_LINES, DEFAULT_MIN_STATEMENTS);
        assert_eq!(findings, Vec::new());
    }

    #[test]
    fn a_genuine_four_statement_setup_shared_by_different_functions_still_fires() {
        // The same window size and line span as the parallel-variant case,
        // but the two functions genuinely diverge (distinct callees, not a
        // type path), so their shared setup block is a real clone.
        let left = r#"
fn offline(path: &Path) -> Result<String, String> {
    let observations = replay(path)?;
    let mint = graduated_mint(path)?;
    let mut simulator = simulator();
    for observation in &observations {
        simulator.observe(observation);
    }
    let valued = simulator.open_value().is_some();
    Ok(format!("{valued}"))
}
"#;
        let right = r#"
fn entered(path: &Path) -> Result<u64, String> {
    let observations = replay(path)?;
    let mint = graduated_mint(path)?;
    let mut simulator = simulator();
    for observation in &observations {
        simulator.observe(observation);
    }
    let leg = simulator.fill(mint)?;
    Ok(leg.tokens())
}
"#;
        let occurrences = occurrences_from(&[("a.rs", left), ("b.rs", right)]);
        assert!(duplicate_groups(&occurrences).is_empty());
        let findings = duplicate_findings(&occurrences, DEFAULT_MIN_LINES, DEFAULT_MIN_STATEMENTS);
        let rendered: Vec<String> = findings.iter().map(Finding::render).collect();
        assert_eq!(rendered, vec!["a.rs:3: ASP501", "b.rs:3: ASP501"]);
    }

    #[test]
    fn the_guard_copy_sort_preamble_idiom_is_not_a_fragment() {
        // Two analytics routines computing unrelated statistics share the
        // `if empty return; sorted copy; sort` opener by convention.
        let left = r#"
fn stats(latencies: &[f64]) -> Option<Summary> {
    if latencies.is_empty() {
        return None;
    }
    let mut sorted = latencies.to_vec();
    sorted.sort_by(f64::total_cmp);
    Some(Summary { count: sorted.len() })
}
"#;
        let right = r#"
fn median(returns: &[f64]) -> Option<f64> {
    if returns.is_empty() {
        return None;
    }
    let mut sorted = returns.to_vec();
    sorted.sort_by(f64::total_cmp);
    let n = sorted.len();
    sorted.get(n / 2).copied()
}
"#;
        let occurrences = occurrences_from(&[("summary.rs", left), ("stat.rs", right)]);
        assert!(duplicate_groups(&occurrences).is_empty());
        let findings = duplicate_findings(&occurrences, DEFAULT_MIN_LINES, DEFAULT_MIN_STATEMENTS);
        assert_eq!(findings, Vec::new());
    }

    #[test]
    fn a_six_statement_copied_block_in_otherwise_different_functions_still_fires() {
        // A copied run this long inside two otherwise-different functions is
        // deliberate reuse: neither precision gate applies, so it fires.
        let left = r#"
fn ingest(rows: &[Row]) -> Report {
    let head = first_marker();
    let mut acc = 0u64;
    let scale = load_scale();
    let width = rows.len() as u64;
    let total = acc + width;
    let scaled = total * scale;
    let adjusted = scaled + head;
    Report::new(adjusted)
}
"#;
        let right = r#"
fn summarize(cells: &[Cell]) -> Summary {
    let extra = other_source();
    let mut acc = 0u64;
    let scale = load_scale();
    let width = cells.len() as u64;
    let total = acc + width;
    let scaled = total * scale;
    let adjusted = scaled + extra;
    finalize(adjusted)
}
"#;
        let occurrences = occurrences_from(&[("left.rs", left), ("right.rs", right)]);
        assert!(duplicate_groups(&occurrences).is_empty());
        let findings = duplicate_findings(&occurrences, DEFAULT_MIN_LINES, DEFAULT_MIN_STATEMENTS);
        let rendered: Vec<String> = findings.iter().map(Finding::render).collect();
        assert_eq!(rendered, vec!["left.rs:4: ASP501", "right.rs:4: ASP501"]);
    }
}
