//! ASP411/414/416: the FSM-verification-integrity family's dispatch and
//! parse-boundary rules, ported to Rust.
//!
//! Three sibling analyzers over one file's Rust source, each a pure
//! `source -> findings` function mirroring the Python catalog rules in
//! `python/src/aspergillus/rules/catalog/`:
//!
//! - **ASP411 `fsm_redundant_branch_findings`** (`FsmRedundantBranches`):
//!   a `match` with two or more arms whose bodies are structurally
//!   identical — redundant states that should collapse into one `A | B =>`
//!   arm.
//! - **ASP414 `fsm_stringly_dispatch_findings`** (`FsmStringlyDispatch`):
//!   a `match` or `if`/`else if` chain that dispatches on string literals
//!   which shadow the variant names of an `enum` declared in the same file
//!   — stringly-typed dispatch that bypasses the compiler's exhaustiveness
//!   checking instead of matching on the enum itself.
//! - **ASP416 `fsm_validate_not_parse_findings`** (`FsmValidateNotParse`):
//!   a free function that validates rather than parses — its return type
//!   carries no parsed output (`bool` or `Result<(), E>` with a unit `Ok`)
//!   and its name opens with a validation verb, so a successful call proves
//!   a check ran but hands back nothing narrower than what it received
//!   (Alexis King, "Parse, don't validate", 2019).
//!
//! Each rule is deliberately conservative — every narrowing below exists to
//! keep correct, idiomatic Rust silent. No file, process, or exit code
//! appears here; the binary reads the source and prints findings.

use ast_grep_core::{Doc, Node};
use ast_grep_language::{LanguageExt, SupportLang};

// ===========================================================================
// ASP411: redundant match branches
// ===========================================================================

/// ASP411: every `match` arm whose body structurally duplicates an earlier
/// arm's body in the same `match`. The first arm carrying a given body is
/// the canonical one and stays silent; each later arm repeating it is
/// reported at its own line — those states should be merged into a single
/// `A | B => body` arm. Blocking.
///
/// Conservativeness narrowings, each guarding a legitimate Rust shape:
/// - **Trivial bodies are exempt.** A bare unit `()`, a single literal, or
///   a single identifier body repeating across arms is legitimate parallel
///   structure (`A => 0, B => 0`), not a redundant state; only a
///   non-trivial body counts as a duplicated transition.
/// - **The wildcard `_` arm never participates.** A `_ => body` sharing a
///   body with a named arm is a legitimate fallthrough default, not a
///   redundant state — it is neither reported nor used to seed a duplicate.
/// - **Guarded arms are skipped.** Two arms with the same body but
///   different `if`-guards are distinct transitions, so an arm carrying a
///   pattern guard is neither reported nor seeds a duplicate.
/// - **Divergent-typed bindings are skipped.** Two arms whose bodies are
///   token-identical are redundant only when they can actually collapse
///   into one `A | B => body` arm. With no type inference available, that
///   is proven syntactically: the arms must bind the same identifiers
///   through the same enum-variant path, or bind nothing at all. Arms that
///   capture a payload through *different* variant paths
///   (`Self::Data(shred) => shred.header()` vs
///   `Self::Coding(shred) => shred.header()`) bind values that may have
///   different types, so the merged or-pattern would fail to compile
///   (E0409); such a pair is neither reported nor seeds a duplicate. Arms
///   that bind nothing (`A => f(), B => f()`) or bind through the *same*
///   variant path still fire.
pub fn fsm_redundant_branch_findings(source: &str) -> Vec<(usize, &'static str, bool)> {
    let root = SupportLang::Rust.ast_grep(source);
    let mut findings = Vec::new();
    for node in root.root().dfs() {
        if node.kind() == "match_expression" {
            findings.extend(redundant_arms(&node));
        }
    }
    findings.sort_by(|a, b| a.0.cmp(&b.0));
    findings.dedup();
    findings
}

/// Report each arm of one `match_expression` whose body duplicates an
/// earlier named, non-trivial, unguarded arm's body.
fn redundant_arms<D: Doc>(match_expr: &Node<'_, D>) -> Vec<(usize, &'static str, bool)> {
    let mut out = Vec::new();
    let Some(body) = match_expr.field("body") else {
        return out;
    };
    let mut seen: Vec<(String, String)> = Vec::new();
    for arm in body.children() {
        if arm.kind() != "match_arm" {
            continue;
        }
        let Some(pattern) = arm.field("pattern") else {
            continue;
        };
        // A guarded arm (`A if cond => …`) is a distinct transition even
        // when its body matches another arm's: skip it entirely.
        if pattern.field("condition").is_some() {
            continue;
        }
        // The wildcard default never participates in a redundancy group.
        if pattern.text().trim() == "_" {
            continue;
        }
        let Some(value) = arm.field("value") else {
            continue;
        };
        if is_trivial_body(&value) {
            continue;
        }
        // A body signature alone is not enough: two arms may share a body
        // yet capture their operands through different variant paths, so the
        // captured values can differ in type and the arms cannot merge into
        // one `A | B => body` (E0409). Pair the body signature with a
        // binding signature — the identifiers each pattern captures and the
        // variant path it captures them through — so only arms that would
        // actually collapse are treated as redundant.
        let signature = (token_signature(&value), binding_signature(&pattern));
        if seen.contains(&signature) {
            out.push((arm.start_pos().line().saturating_add(1), "ASP411", true));
        } else {
            seen.push(signature);
        }
    }
    out
}

/// A structural signature of an expression, blind to whitespace, comments,
/// and formatting: the text of every leaf token in source order. Two bodies
/// with the same signature are the same code up to layout.
fn token_signature<D: Doc>(node: &Node<'_, D>) -> String {
    let mut tokens = Vec::new();
    collect_leaf_tokens(node, &mut tokens);
    tokens.join("\u{1f}")
}

/// Append the text of every leaf descendant of `node` (including `node`
/// itself when it is a leaf) to `tokens`, in source order.
fn collect_leaf_tokens<D: Doc>(node: &Node<'_, D>, tokens: &mut Vec<String>) {
    let mut children = node.children().peekable();
    if children.peek().is_none() {
        tokens.push(node.text().trim().to_string());
        return;
    }
    for child in children {
        collect_leaf_tokens(&child, tokens);
    }
}

/// A signature of the identifiers an arm pattern captures and the variant
/// path each is captured through, canonical and blind to source order:
/// `Self::Data(shred)` -> `shred@Self::Data`, `(E::Data(x), true)` ->
/// `x@E::Data`, a bare `A` or a wildcard `_` -> the empty string. Two arms
/// with the same binding signature capture the same names through the same
/// variant paths, so an `A | B => body` merge binds each name to one type
/// and compiles; a differing signature means a merge could bind a name to
/// two types (E0409), so the arms are not redundant.
fn binding_signature<D: Doc>(pattern: &Node<'_, D>) -> String {
    let mut binds: Vec<String> = Vec::new();
    collect_pattern_bindings(pattern, None, &mut binds);
    binds.sort();
    binds.dedup();
    binds.join("\u{1f}")
}

/// Walk a pattern, recording each captured identifier as `name@variant_path`
/// where `variant_path` is the enclosing tuple-struct or struct pattern's
/// type (`Self::Data`, `E::S`). An identifier captured outside any such
/// pattern — a bare top-level binding, which binds the whole scrutinee to a
/// single type — carries no variant path and is not recorded, since it never
/// introduces a per-variant type divergence.
fn collect_pattern_bindings<D: Doc>(node: &Node<'_, D>, path: Option<&str>, out: &mut Vec<String>) {
    match node.kind().as_ref() {
        // A variant/struct pattern rebinds the path for the operands it
        // destructures: its own `type` child names the variant, and every
        // other child is a sub-pattern captured through that variant.
        "tuple_struct_pattern" | "struct_pattern" => {
            let type_node = node.field("type");
            let variant = type_node.as_ref().map(|t| t.text().trim().to_string());
            for child in node.children() {
                if let Some(t) = &type_node {
                    if child.range() == t.range() {
                        continue;
                    }
                }
                collect_pattern_bindings(&child, variant.as_deref(), out);
            }
        }
        // A captured identifier: `shred` in `Self::Data(shred)`, or the
        // shorthand field in `E::S { field }`.
        "identifier" | "shorthand_field_identifier" => {
            if let Some(p) = path {
                out.push(format!("{}@{}", node.text().trim(), p));
            }
        }
        // Any other node (tuple patterns, reference patterns, field names,
        // literals, `_`) carries the current path into its children.
        _ => {
            for child in node.children() {
                collect_pattern_bindings(&child, path, out);
            }
        }
    }
}

/// Whether an arm body is trivial: a bare unit `()`, a single literal, or a
/// single identifier — including the same wrapped in a one-expression
/// block. Trivial bodies repeating across arms are legitimate parallel
/// structure, not a redundant state.
fn is_trivial_body<D: Doc>(value: &Node<'_, D>) -> bool {
    if is_trivial_leaf(value) {
        return true;
    }
    if value.kind() == "block" {
        let mut meaningful = value.children().filter(|c| {
            !matches!(
                c.kind().as_ref(),
                "{" | "}" | "line_comment" | "block_comment"
            )
        });
        return match meaningful.next() {
            // An empty block `{}` is as trivial as a unit.
            None => true,
            Some(only) => meaningful.next().is_none() && is_trivial_leaf(&only),
        };
    }
    false
}

/// Whether a node is a bare trivial expression: unit, a literal, or an
/// identifier.
fn is_trivial_leaf<D: Doc>(node: &Node<'_, D>) -> bool {
    matches!(
        node.kind().as_ref(),
        "unit_expression"
            | "integer_literal"
            | "float_literal"
            | "string_literal"
            | "char_literal"
            | "boolean_literal"
            | "identifier"
    )
}

// ===========================================================================
// ASP414: stringly-typed dispatch shadowing a same-file enum
// ===========================================================================

/// ASP414: every `match` or `if`/`else if` chain that dispatches on string
/// literals shadowing the variant names of an `enum` declared in the same
/// file. Reported at the dispatch's own line. Blocking.
///
/// Conservativeness narrowings:
/// - **A same-file enum must exist and be shadowed.** With no enum whose
///   variant names the dispatch's string literals reproduce, there is
///   nothing stringly-typed to flag.
/// - **At least two literals must shadow variant names.** A single string
///   comparison (`if kind == "json"`) against genuine external data is not
///   a dispatch masquerading as an enum match; requiring two shadowing
///   literals keeps a lone string branch silent.
/// - **Variant names match case-sensitively** on the Rust identifier: a
///   dispatch on `"Foo"`/`"Bar"` shadows `enum E { Foo, Bar }`, but on
///   `"foo"`/`"bar"` it does not.
pub fn fsm_stringly_dispatch_findings(source: &str) -> Vec<(usize, &'static str, bool)> {
    let root = SupportLang::Rust.ast_grep(source);
    let variants = enum_variant_names(&root.root());
    if variants.is_empty() {
        return Vec::new();
    }
    let mut findings = Vec::new();
    for node in root.root().dfs() {
        match node.kind().as_ref() {
            "match_expression" => {
                if count_shadowing(match_arm_string_literals(&node), &variants) >= 2 {
                    findings.push((node.start_pos().line().saturating_add(1), "ASP414", true));
                }
            }
            // Only a chain root (an `if` that is not itself an `else if`
            // continuation) is measured, so a chain is counted once.
            "if_expression" if !is_else_if(&node) => {
                if count_shadowing(if_chain_string_literals(&node), &variants) >= 2 {
                    findings.push((node.start_pos().line().saturating_add(1), "ASP414", true));
                }
            }
            _ => {}
        }
    }
    findings.sort_by(|a, b| a.0.cmp(&b.0));
    findings.dedup();
    findings
}

/// The set of every `enum` variant name declared anywhere in the file.
fn enum_variant_names<D: Doc>(root: &Node<'_, D>) -> Vec<String> {
    let mut names = Vec::new();
    for node in root.dfs() {
        if node.kind() != "enum_item" {
            continue;
        }
        let Some(body) = node.field("body") else {
            continue;
        };
        for variant in body.children() {
            if variant.kind() == "enum_variant" {
                if let Some(name) = variant.field("name") {
                    names.push(name.text().to_string());
                }
            }
        }
    }
    names
}

/// How many of `literals` name a same-file enum variant (case-sensitive).
fn count_shadowing(literals: Vec<String>, variants: &[String]) -> usize {
    literals
        .into_iter()
        .filter(|lit| variants.iter().any(|v| v == lit))
        .count()
}

/// The string-literal pattern contents across a `match_expression`'s arms:
/// each arm pattern that is a bare string literal contributes its content.
fn match_arm_string_literals<D: Doc>(match_expr: &Node<'_, D>) -> Vec<String> {
    let mut out = Vec::new();
    let Some(body) = match_expr.field("body") else {
        return out;
    };
    for arm in body.children() {
        if arm.kind() != "match_arm" {
            continue;
        }
        let Some(pattern) = arm.field("pattern") else {
            continue;
        };
        for child in pattern.children() {
            if let Some(content) = string_literal_content(&child) {
                out.push(content);
            }
        }
    }
    out
}

/// The string literals compared with `==` along an `if`/`else if` chain's
/// conditions. Only the condition expressions are inspected — literals in
/// the branch bodies are not dispatch keys.
fn if_chain_string_literals<D: Doc>(if_expr: &Node<'_, D>) -> Vec<String> {
    let mut out = Vec::new();
    let mut current = Some(if_expr.clone());
    while let Some(node) = current {
        if node.kind() != "if_expression" {
            break;
        }
        if let Some(condition) = node.field("condition") {
            collect_eq_string_literals(&condition, &mut out);
        }
        current = node
            .field("alternative")
            .and_then(|else_clause| else_clause.children().find(|c| c.kind() == "if_expression"));
    }
    out
}

/// Collect the content of every string literal that is an operand of an
/// `==` comparison anywhere within `node` (a condition expression), so
/// `a == "x" || b == "y"` yields both.
fn collect_eq_string_literals<D: Doc>(node: &Node<'_, D>, out: &mut Vec<String>) {
    if node.kind() == "binary_expression" && binary_is_eq(node) {
        for child in node.children() {
            if let Some(content) = string_literal_content(&child) {
                out.push(content);
            }
        }
    }
    for child in node.children() {
        collect_eq_string_literals(&child, out);
    }
}

/// Whether a `binary_expression`'s operator is `==`.
fn binary_is_eq<D: Doc>(node: &Node<'_, D>) -> bool {
    node.children().any(|c| c.kind() == "==")
}

/// The inner content of a `string_literal` node (`"Foo"` -> `Foo`), or
/// `None` for any other node.
fn string_literal_content<D: Doc>(node: &Node<'_, D>) -> Option<String> {
    if node.kind() != "string_literal" {
        return None;
    }
    let content = node
        .children()
        .find(|c| c.kind() == "string_content")
        .map(|c| c.text().to_string())
        .unwrap_or_default();
    Some(content)
}

/// Whether an `if_expression` is the `else if` continuation of an outer
/// `if` — its parent is an `else_clause`. Such a node is measured as part
/// of its chain root, never on its own.
fn is_else_if<D: Doc>(node: &Node<'_, D>) -> bool {
    node.parent()
        .map(|p| p.kind() == "else_clause")
        .unwrap_or(false)
}

// ===========================================================================
// ASP416: validate, don't parse
// ===========================================================================

/// The validation verbs a function name may open with. A function so named
/// answers a yes/no question about its input rather than returning a parsed,
/// narrowed value.
const VALIDATION_VERB_PREFIXES: &[&str] = &["is_", "has_", "validate", "check", "verify", "ensure"];

/// ASP416: every free function that validates rather than parses — its name
/// opens with a validation verb and its return type carries no parsed
/// output. Reported at the function's line. Blocking.
///
/// Refined Rust trigger (decidable from the signature alone), mirroring the
/// Python `FsmValidateNotParse`'s intent — a function that can reject its
/// input should return a type proving, on success, that the input satisfied
/// a stronger invariant:
/// - a **free** `function_item` (directly under the file or a `mod`, never
///   an `impl`/`trait` method), AND
/// - whose name opens with a validation verb (`is_`, `has_`, `validate`,
///   `check`, `verify`, `ensure`), AND
/// - whose return type is exactly `bool` or `Result<(), E>` — a `Result`
///   whose success arm is the unit `()`, carrying no parsed output, AND
/// - which takes at least one **raw-input** parameter — an unparsed
///   `str`/`String`/`[u8]`/`Vec<u8>`/`OsStr`/`OsString` (through a leading
///   `&`/lifetime/`mut`) — the text or bytes it should parse into a
///   narrower type.
///
/// Conservativeness narrowings:
/// - **Both the validate-shaped return type and the verb name are
///   required.** A `check_*` returning a parsed `Config`, or an
///   `analyze`-named function returning `bool`, is not flagged — only the
///   conjunction is the parse-don't-validate shape.
/// - **The inspected parameter must be raw input.** A predicate over an
///   already-parsed domain value (`fn is_enter(a: Act) -> bool`, `fn
///   is_valid(c: &Config) -> bool`) is a legitimate classification, not a
///   parse boundary — the smell is reducing raw text/bytes to a verdict
///   instead of parsing them, so only a raw-input parameter counts.
/// - **Impl and trait methods are exempt.** `is_empty`, `PartialEq::eq`,
///   and inherent predicates are legitimate Rust idioms, not parse
///   boundaries; only free functions are considered.
/// - **A zero-parameter predicate is exempt.** A `fn is_ready() -> bool`
///   reading ambient state takes no value to parse, so it cannot be
///   validating-instead-of-parsing an input.
pub fn fsm_validate_not_parse_findings(source: &str) -> Vec<(usize, &'static str, bool)> {
    let root = SupportLang::Rust.ast_grep(source);
    let mut funcs = Vec::new();
    collect_free_functions(&root.root(), &mut funcs);
    let mut findings: Vec<(usize, &'static str, bool)> = funcs
        .iter()
        .filter(|f| validates_not_parses(f))
        .map(|f| (f.start_pos().line().saturating_add(1), "ASP416", true))
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

/// Whether `func` has a validation-verb name, a validate-shaped return type
/// (`bool` or `Result<(), _>`), and at least one **raw-input** parameter
/// (an unparsed `str`/`String`/`[u8]`/`Vec<u8>`/`OsStr`/`OsString`).
fn validates_not_parses<D: Doc>(func: &Node<'_, D>) -> bool {
    let Some(name) = func.field("name") else {
        return false;
    };
    let name = name.text();
    if !VALIDATION_VERB_PREFIXES
        .iter()
        .any(|p| name.as_ref().starts_with(p))
    {
        return false;
    }
    if !takes_raw_input(func) {
        return false;
    }
    match func.field("return_type") {
        Some(ret) => is_validate_shaped_return(&ret),
        None => false,
    }
}

/// The raw, still-unparsed input types a parse-don't-validate function
/// should be turning into a narrower type instead of reducing to a verdict:
/// text and byte buffers. A parameter of an already-parsed domain type (an
/// `enum`, a struct like `&Config`) is the input of a legitimate predicate,
/// not a parse boundary, so it is deliberately excluded — that exclusion is
/// what keeps idiomatic variant tests (`fn is_enter(a: Act) -> bool`) silent.
const RAW_INPUT_TYPES: &[&str] = &["str", "String", "[u8]", "Vec<u8>", "OsStr", "OsString"];

/// Whether the function declares at least one parameter whose type is a raw
/// input type (see `RAW_INPUT_TYPES`), looking through a leading reference,
/// lifetime, and `mut`.
fn takes_raw_input<D: Doc>(func: &Node<'_, D>) -> bool {
    let Some(params) = func.field("parameters") else {
        return false;
    };
    for param in params.children() {
        if param.kind() != "parameter" {
            continue;
        }
        if let Some(ty) = param.field("type") {
            let normalized = normalize_param_type(ty.text().as_ref());
            if RAW_INPUT_TYPES.contains(&normalized.as_str()) || normalized.starts_with("[u8;") {
                return true;
            }
        }
    }
    false
}

/// A parameter type reduced to its base for the raw-input comparison: a
/// leading `&`, a lifetime (`'a`), and `mut` are stripped, then interior
/// whitespace is removed. `&str` -> `str`, `&[u8]` -> `[u8]`,
/// `&'a mut String` -> `String`, `Vec<u8>` -> `Vec<u8>`.
fn normalize_param_type(text: &str) -> String {
    let mut s = text.trim();
    if let Some(rest) = s.strip_prefix('&') {
        s = rest.trim_start();
    }
    if s.starts_with('\'') {
        let end = s[1..]
            .find(|c: char| !(c.is_alphanumeric() || c == '_'))
            .map_or(s.len(), |i| i + 1);
        s = s[end..].trim_start();
    }
    if let Some(rest) = s.strip_prefix("mut ") {
        s = rest.trim_start();
    }
    s.split_whitespace().collect()
}

/// Whether a return type is exactly `bool` or `Result<(), _>` (a `Result`
/// whose first type argument is the unit type). Both carry no parsed output
/// on success.
fn is_validate_shaped_return<D: Doc>(ret: &Node<'_, D>) -> bool {
    if ret.kind() == "primitive_type" && ret.text() == "bool" {
        return true;
    }
    if ret.kind() == "generic_type" {
        let Some(base) = ret.field("type") else {
            return false;
        };
        if base.text() != "Result" {
            return false;
        }
        let Some(args) = ret.field("type_arguments") else {
            return false;
        };
        // The success arm is the first type argument; a unit `()` there is
        // a `Result<(), E>` (or `Result<()>`) — no parsed output returned.
        return args
            .children()
            .find(|c| !matches!(c.kind().as_ref(), "<" | ">" | ","))
            .map(|first| first.kind() == "unit_type")
            .unwrap_or(false);
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    fn asp411(source: &str) -> Vec<usize> {
        fsm_redundant_branch_findings(source)
            .into_iter()
            .map(|(line, _, _)| line)
            .collect()
    }

    fn asp414(source: &str) -> Vec<usize> {
        fsm_stringly_dispatch_findings(source)
            .into_iter()
            .map(|(line, _, _)| line)
            .collect()
    }

    fn asp416(source: &str) -> Vec<usize> {
        fsm_validate_not_parse_findings(source)
            .into_iter()
            .map(|(line, _, _)| line)
            .collect()
    }

    // ---- ASP411 -----------------------------------------------------------

    #[test]
    fn identical_arm_bodies_flag_the_later_arm() {
        assert_eq!(
            asp411(
                "fn f(s: State) -> i32 {\n    match s {\n        State::A => compute(s),\n        State::B => compute(s),\n        State::C => other(s),\n    }\n}\n"
            ),
            vec![4]
        );
    }

    #[test]
    fn three_identical_bodies_flag_both_later_arms() {
        assert_eq!(
            asp411(
                "fn f(s: State) -> i32 {\n    match s {\n        State::A => compute(s),\n        State::B => compute(s),\n        State::C => compute(s),\n    }\n}\n"
            ),
            vec![4, 5]
        );
    }

    #[test]
    fn distinct_bodies_are_silent() {
        assert!(asp411(
            "fn f(s: State) -> i32 {\n    match s {\n        State::A => compute(s),\n        State::B => other(s),\n    }\n}\n"
        )
        .is_empty());
    }

    #[test]
    fn trivial_literal_bodies_are_exempt() {
        // Parallel trivial arms returning the same literal are legitimate.
        assert!(asp411(
            "fn f(s: State) -> i32 {\n    match s {\n        State::A => 0,\n        State::B => 0,\n        State::C => 1,\n    }\n}\n"
        )
        .is_empty());
    }

    #[test]
    fn wildcard_sharing_a_body_is_a_legitimate_fallthrough() {
        assert!(asp411(
            "fn f(s: State) -> i32 {\n    match s {\n        State::A => compute(s),\n        _ => compute(s),\n    }\n}\n"
        )
        .is_empty());
    }

    #[test]
    fn guarded_arms_with_the_same_body_are_distinct_transitions() {
        assert!(asp411(
            "fn f(s: State, n: i32) -> i32 {\n    match s {\n        State::A if n > 0 => compute(s),\n        State::A => compute(s),\n    }\n}\n"
        )
        .is_empty());
    }

    #[test]
    fn identical_block_bodies_are_flagged() {
        assert_eq!(
            asp411(
                "fn f(s: State) -> i32 {\n    match s {\n        State::A => { let x = step(s); x + 1 }\n        State::B => { let x = step(s); x + 1 }\n    }\n}\n"
            ),
            vec![4]
        );
    }

    #[test]
    fn identical_bodies_binding_different_variant_paths_are_silent() {
        // `shred` binds a DataShred in one arm and a CodingShred in the
        // other; the merged `Self::Data(shred) | Self::Coding(shred)` fails
        // to compile (E0409), so the arms are not redundant.
        assert!(asp411(
            "fn f(e: E) -> u32 {\n    match e {\n        Self::Data(shred) => shred.header(),\n        Self::Coding(shred) => shred.header(),\n    }\n}\n"
        )
        .is_empty());
    }

    #[test]
    fn identical_bodies_binding_the_same_variant_path_are_flagged() {
        // Both arms capture `x` through `E::Data`, so the merge binds `x` to
        // one type and compiles — a genuine redundancy.
        assert_eq!(
            asp411(
                "fn f(e: E, b: bool) -> u32 {\n    match (e, b) {\n        (E::Data(x), true) => x.count_ones(),\n        (E::Data(x), false) => x.count_ones(),\n    }\n}\n"
            ),
            vec![4]
        );
    }

    #[test]
    fn identical_bodies_with_no_bindings_are_flagged() {
        // Neither arm captures anything, so `A | B => step()` compiles: the
        // second arm is redundant.
        assert_eq!(
            asp411(
                "fn f(s: State) -> i32 {\n    match s {\n        State::A => step(s),\n        State::B => step(s),\n    }\n}\n"
            ),
            vec![4]
        );
    }

    #[test]
    fn identical_bodies_binding_wildcards_under_different_variants_are_flagged() {
        // `_` captures nothing, so `Self::Data(_) | Self::Coding(_) => log()`
        // compiles regardless of the payload types.
        assert_eq!(
            asp411(
                "fn f(e: E) -> u32 {\n    match e {\n        Self::Data(_) => log(),\n        Self::Coding(_) => log(),\n    }\n}\n"
            ),
            vec![4]
        );
    }

    // ---- ASP414 -----------------------------------------------------------

    #[test]
    fn match_on_strings_shadowing_enum_variants_is_flagged() {
        assert_eq!(
            asp414(
                "enum State { Active, Idle }\nfn route(s: &str) -> i32 {\n    match s {\n        \"Active\" => 1,\n        \"Idle\" => 2,\n        _ => 0,\n    }\n}\n"
            ),
            vec![3]
        );
    }

    #[test]
    fn if_chain_on_strings_shadowing_enum_variants_is_flagged() {
        assert_eq!(
            asp414(
                "enum State { Active, Idle }\nfn route(s: &str) -> i32 {\n    if s == \"Active\" {\n        1\n    } else if s == \"Idle\" {\n        2\n    } else {\n        0\n    }\n}\n"
            ),
            vec![3]
        );
    }

    #[test]
    fn strings_with_no_shadowing_enum_are_silent() {
        assert!(asp414(
            "fn route(s: &str) -> i32 {\n    match s {\n        \"active\" => 1,\n        \"idle\" => 2,\n        _ => 0,\n    }\n}\n"
        )
        .is_empty());
    }

    #[test]
    fn a_single_shadowing_literal_is_below_threshold() {
        assert!(asp414(
            "enum State { Active, Idle }\nfn route(s: &str) -> i32 {\n    if s == \"Active\" {\n        1\n    } else {\n        0\n    }\n}\n"
        )
        .is_empty());
    }

    #[test]
    fn case_differing_literals_do_not_shadow() {
        assert!(asp414(
            "enum State { Active, Idle }\nfn route(s: &str) -> i32 {\n    match s {\n        \"active\" => 1,\n        \"idle\" => 2,\n        _ => 0,\n    }\n}\n"
        )
        .is_empty());
    }

    #[test]
    fn dispatch_on_the_enum_itself_is_silent() {
        assert!(asp414(
            "enum State { Active, Idle }\nfn route(s: State) -> i32 {\n    match s {\n        State::Active => 1,\n        State::Idle => 2,\n    }\n}\n"
        )
        .is_empty());
    }

    // ---- ASP416 -----------------------------------------------------------

    #[test]
    fn validation_verb_over_raw_str_returning_bool_is_flagged() {
        assert_eq!(
            asp416("fn is_valid_email(x: &str) -> bool {\n    x.contains('@')\n}\n"),
            vec![1]
        );
    }

    #[test]
    fn validation_verb_over_raw_bytes_returning_result_unit_is_flagged() {
        assert_eq!(
            asp416("fn validate(x: &[u8]) -> Result<(), Error> {\n    Ok(())\n}\n"),
            vec![1]
        );
    }

    #[test]
    fn a_predicate_over_a_parsed_domain_type_is_silent() {
        // `is_enter(a: Act) -> bool` and `is_valid(c: &Config) -> bool` test
        // an already-parsed value — a legitimate classification, not a parse
        // boundary. Only raw text/bytes input is the parse-don't-validate smell.
        assert!(asp416("enum Act { Enter, Exit }\nfn is_enter(a: Act) -> bool {\n    matches!(a, Act::Enter)\n}\n").is_empty());
        assert!(asp416("fn is_valid(c: &Config) -> bool {\n    c.ok\n}\n").is_empty());
    }

    #[test]
    fn a_parser_returning_a_narrowed_type_is_silent() {
        // Returns a parsed value, not a yes/no — the correct shape.
        assert!(
            asp416("fn parse(x: &str) -> Result<Config, Error> {\n    Config::from(x)\n}\n")
                .is_empty()
        );
    }

    #[test]
    fn a_bool_predicate_with_a_non_verb_name_is_silent() {
        assert!(asp416("fn ready(x: &Config) -> bool {\n    x.ok\n}\n").is_empty());
    }

    #[test]
    fn a_zero_parameter_predicate_is_exempt() {
        assert!(asp416("fn is_ready() -> bool {\n    true\n}\n").is_empty());
    }

    #[test]
    fn an_impl_method_predicate_is_exempt() {
        assert!(asp416(
            "struct S;\nimpl S {\n    fn is_valid(&self, x: &Config) -> bool {\n        x.ok\n    }\n}\n"
        )
        .is_empty());
    }

    #[test]
    fn a_verb_name_returning_a_narrowed_type_is_silent() {
        // `check_*` that returns a parsed value is a parser, not a validator.
        assert!(asp416(
            "fn check_config(x: &str) -> Result<Config, Error> {\n    Config::from(x)\n}\n"
        )
        .is_empty());
    }
}
