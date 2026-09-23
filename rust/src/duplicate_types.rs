//! Whole-workspace Rust duplicate-TYPE detector (functional core).
//!
//! Finds a struct or enum CONCEPT — the same declared name carrying the
//! same shape — declared in more than one crate of a Cargo workspace. Two
//! declarations that share only a name, with a different shape, are two
//! separate concepts and are not reported; two declarations of the same
//! name and shape confined to one crate are not reported either, since
//! the request is about a concept crossing a crate boundary. Pebble:
//! asp-ce6.4.
//!
//! A declaration's shape ignores field/element types and visibility, and
//! keeps only its structural skeleton:
//! - a unit struct (`struct Foo;`) shapes as `struct:unit`;
//! - a tuple struct (`struct Foo(T1, T2)`) shapes as its field COUNT only
//!   (`struct:tuple:2`), so `Nanos(u64)`, `Nanos(i64)` and `Nanos(pub
//!   u64)` — three real lobaria declarations backing one `Nanos` amount —
//!   shape identically despite differing width, signedness and
//!   visibility;
//! - a named-field struct (`struct Foo { a: T1, b: T2 }`) shapes as its
//!   ordered field NAME list (`struct:fields:a,b`), ignoring each field's
//!   type;
//! - an enum shapes as its ordered variant NAME list
//!   (`enum:variants:A,B`), ignoring each variant's payload.
//!
//! No file, process, or exit code appears here — those live in the binary
//! at `src/bin/aspergillus_rust_dup_type_check.rs`.

use std::collections::HashMap;

use ast_grep_core::tree_sitter::StrDoc;
use ast_grep_core::Node;
use ast_grep_language::{LanguageExt, SupportLang};

use crate::Finding;

/// The ASP id every finding of this check reports.
pub const RULE_ID: &str = "ASP502";

type RNode<'r> = Node<'r, StrDoc<SupportLang>>;

/// One struct or enum declaration: its crate, file, 1-based start line,
/// declared name, and shape fingerprint.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TypeOccurrence {
    /// The crate the declaration belongs to: the workspace-relative path
    /// of the nearest ancestor directory holding a `Cargo.toml`.
    pub crate_id: String,
    /// The file, relative to the scanned workspace root.
    pub path: String,
    /// The 1-based line the declaration starts on.
    pub line: usize,
    /// The declared type name.
    pub name: String,
    /// The shape fingerprint two same-named declarations compare by.
    pub shape: String,
}

/// The workspace-relative crate a file belongs to: the LONGEST of
/// `crate_roots` that is an ancestor of `path`. A file under no known
/// crate root reports the empty string, so it never joins another file's
/// group.
pub fn crate_id_for_path(path: &std::path::Path, crate_roots: &[String]) -> String {
    crate_roots
        .iter()
        .filter(|root| root.is_empty() || path.starts_with(std::path::Path::new(root.as_str())))
        .max_by_key(|root| root.len())
        .cloned()
        .unwrap_or_default()
}

/// The child of `node` with tree-sitter kind `kind`, if one exists.
fn child_of_kind<'r>(node: &RNode<'r>, kind: &str) -> Option<RNode<'r>> {
    node.children().find(|child| child.kind().as_ref() == kind)
}

/// A tuple struct's or tuple enum-variant's field body
/// (`ordered_field_declaration_list`, e.g. `(pub u64)`): the count of its
/// declared fields, ignoring each field's own type and visibility. Every
/// child of this body is punctuation, a `visibility_modifier`, or exactly
/// one type node per field, so counting past those two exclusions counts
/// the fields.
fn tuple_arity(body: &RNode<'_>) -> usize {
    body.children()
        .filter(|child| {
            !matches!(
                child.kind().as_ref(),
                "(" | ")" | "," | "visibility_modifier"
            )
        })
        .count()
}

/// A named-field body's (`field_declaration_list`, e.g. `{ a: i32, b:
/// String }`) ordered field-name list, ignoring each field's type and
/// visibility.
fn named_field_names(body: &RNode<'_>) -> Vec<String> {
    body.children()
        .filter(|child| child.kind().as_ref() == "field_declaration")
        .filter_map(|decl| child_of_kind(&decl, "field_identifier"))
        .map(|ident| ident.text().into_owned())
        .collect()
}

/// A `struct_item` node's shape fingerprint. See the module doc comment
/// for the three cases (unit, tuple, named-field).
fn struct_shape(node: &RNode<'_>) -> String {
    if let Some(body) = child_of_kind(node, "field_declaration_list") {
        format!("struct:fields:{}", named_field_names(&body).join(","))
    } else if let Some(body) = child_of_kind(node, "ordered_field_declaration_list") {
        format!("struct:tuple:{}", tuple_arity(&body))
    } else {
        "struct:unit".to_string()
    }
}

/// An `enum_item` node's shape fingerprint: its ordered variant-name
/// list, ignoring each variant's own payload.
fn enum_shape(node: &RNode<'_>) -> String {
    let variants: Vec<String> = child_of_kind(node, "enum_variant_list")
        .into_iter()
        .flat_map(|list| list.children().collect::<Vec<_>>())
        .filter(|child| child.kind().as_ref() == "enum_variant")
        .filter_map(|variant| child_of_kind(&variant, "identifier"))
        .map(|ident| ident.text().into_owned())
        .collect();
    format!("enum:variants:{}", variants.join(","))
}

/// The declared name of a `struct_item` or `enum_item`: its
/// `type_identifier` child.
fn declared_name(node: &RNode<'_>) -> Option<String> {
    child_of_kind(node, "type_identifier").map(|ident| ident.text().into_owned())
}

/// Every top-level or nested `struct_item`/`enum_item` in an already-read
/// Rust source, tagged with the crate it belongs to.
pub fn type_occurrences(path: &str, crate_id: &str, source: &str) -> Vec<TypeOccurrence> {
    let root = SupportLang::Rust.ast_grep(source);
    root.root()
        .dfs()
        .filter(|node| matches!(node.kind().as_ref(), "struct_item" | "enum_item"))
        .filter_map(|node| {
            let name = declared_name(&node)?;
            let line = node.start_pos().line().saturating_add(1);
            let shape = if node.kind().as_ref() == "struct_item" {
                struct_shape(&node)
            } else {
                enum_shape(&node)
            };
            Some(TypeOccurrence {
                crate_id: crate_id.to_string(),
                path: path.to_string(),
                line,
                name,
                shape,
            })
        })
        .collect()
}

/// Groups occurrences by identical `(name, shape)`. Only a group whose
/// members span TWO OR MORE distinct crates is a cross-crate duplicate —
/// a concept confined to one crate, however many times it repeats there,
/// is not reported. Groups are sorted by their first member's path then
/// line, for deterministic output; members within a group are sorted the
/// same way.
pub fn duplicate_groups(occurrences: &[TypeOccurrence]) -> Vec<Vec<TypeOccurrence>> {
    let mut buckets: HashMap<(&str, &str), Vec<&TypeOccurrence>> = HashMap::new();
    for occurrence in occurrences {
        buckets
            .entry((occurrence.name.as_str(), occurrence.shape.as_str()))
            .or_default()
            .push(occurrence);
    }

    let mut groups: Vec<Vec<TypeOccurrence>> = buckets
        .into_values()
        .filter(|members| {
            let distinct_crates: std::collections::HashSet<&str> =
                members.iter().map(|m| m.crate_id.as_str()).collect();
            distinct_crates.len() > 1
        })
        .map(|members| {
            let mut members: Vec<TypeOccurrence> = members.into_iter().cloned().collect();
            members.sort_by(|a, b| a.path.cmp(&b.path).then(a.line.cmp(&b.line)));
            members
        })
        .collect();

    groups.sort_by(|a, b| a[0].path.cmp(&b[0].path).then(a[0].line.cmp(&b[0].line)));
    groups
}

/// The allowlist key for one duplicate group: its declared name. An
/// allowlist entry drops every group of that name, matching the Python
/// `check-duplicates` reference's one-key-per-line, `#`-comment format.
pub fn allowlist_key(group: &[TypeOccurrence]) -> &str {
    group[0].name.as_str()
}

/// Drops every group whose `allowlist_key` is in `allowed`, keeping the
/// rest — and their relative order — unchanged.
pub fn apply_allowlist(
    groups: Vec<Vec<TypeOccurrence>>,
    allowed: &std::collections::HashSet<String>,
) -> Vec<Vec<TypeOccurrence>> {
    groups
        .into_iter()
        .filter(|group| !allowed.contains(allowlist_key(group)))
        .collect()
}

/// Every duplicate group rendered as one blocking `Finding` per member,
/// sorted by path then line.
pub fn findings_for_groups(groups: &[Vec<TypeOccurrence>]) -> Vec<Finding> {
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
    fn two_crates_declaring_the_same_tuple_struct_with_differing_field_types_is_one_group() {
        let one = type_occurrences(
            "crate-a/src/units.rs",
            "crate-a",
            "pub struct Nanos(i64);\n",
        );
        let two = type_occurrences(
            "crate-b/src/units.rs",
            "crate-b",
            "pub struct Nanos(pub u64);\n",
        );
        let mut occurrences = one;
        occurrences.extend(two);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0].len(), 2);
    }

    #[test]
    fn a_duplicate_confined_to_one_crate_is_not_reported() {
        let one = type_occurrences("crate-a/src/a.rs", "crate-a", "pub struct Nanos(i64);\n");
        let two = type_occurrences("crate-a/src/b.rs", "crate-a", "pub struct Nanos(u64);\n");
        let mut occurrences = one;
        occurrences.extend(two);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups, Vec::<Vec<TypeOccurrence>>::new());
    }

    #[test]
    fn same_name_different_shape_across_crates_is_not_reported() {
        let one = type_occurrences("crate-a/src/a.rs", "crate-a", "pub struct Refused;\n");
        let two = type_occurrences(
            "crate-b/src/b.rs",
            "crate-b",
            "pub enum Refused { NotReady, TooLate }\n",
        );
        let mut occurrences = one;
        occurrences.extend(two);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups, Vec::<Vec<TypeOccurrence>>::new());
    }

    #[test]
    fn named_field_structs_compare_by_field_name_list_not_type() {
        let one = type_occurrences(
            "crate-a/src/a.rs",
            "crate-a",
            "pub struct Hit { rule: String, path: String }\n",
        );
        let two = type_occurrences(
            "crate-b/src/b.rs",
            "crate-b",
            "pub struct Hit { rule: u32, path: u32 }\n",
        );
        let three = type_occurrences(
            "crate-c/src/c.rs",
            "crate-c",
            "pub struct Hit { reason: String }\n",
        );
        let mut occurrences = one;
        occurrences.extend(two);
        occurrences.extend(three);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0].len(), 2);
    }

    #[test]
    fn enums_compare_by_variant_name_list() {
        let one = type_occurrences(
            "crate-a/src/a.rs",
            "crate-a",
            "pub enum Refused { NotReady, TooLate }\n",
        );
        let two = type_occurrences(
            "crate-b/src/b.rs",
            "crate-b",
            "pub enum Refused { NotReady(i64), TooLate(String) }\n",
        );
        let mut occurrences = one;
        occurrences.extend(two);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups.len(), 1);
    }

    #[test]
    fn crate_id_for_path_picks_the_longest_matching_root() {
        let roots = vec!["".to_string(), "statechart".to_string()];
        let id = crate_id_for_path(std::path::Path::new("statechart/src/units.rs"), &roots);
        assert_eq!(id, "statechart");
    }

    #[test]
    fn apply_allowlist_drops_only_the_named_group() {
        let nanos = type_occurrences("a/src/units.rs", "a", "pub struct Nanos(i64);\n");
        let nanos_b = type_occurrences("b/src/units.rs", "b", "pub struct Nanos(u64);\n");
        let receipt = type_occurrences("a/src/edge.rs", "a", "pub struct Receipt(i64);\n");
        let receipt_b = type_occurrences("b/src/units.rs", "b", "pub struct Receipt(i64);\n");
        let mut occurrences = nanos;
        occurrences.extend(nanos_b);
        occurrences.extend(receipt);
        occurrences.extend(receipt_b);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups.len(), 2);

        let allowed: std::collections::HashSet<String> =
            ["Nanos".to_string()].into_iter().collect();
        let remaining = apply_allowlist(groups, &allowed);
        assert_eq!(remaining.len(), 1);
        assert_eq!(allowlist_key(&remaining[0]), "Receipt");
    }

    #[test]
    fn findings_render_as_path_line_asp_code() {
        let groups = vec![vec![
            TypeOccurrence {
                crate_id: "a".to_string(),
                path: "a/src/x.rs".to_string(),
                line: 3,
                name: "Nanos".to_string(),
                shape: "struct:tuple:1".to_string(),
            },
            TypeOccurrence {
                crate_id: "b".to_string(),
                path: "b/src/y.rs".to_string(),
                line: 9,
                name: "Nanos".to_string(),
                shape: "struct:tuple:1".to_string(),
            },
        ]];
        let findings = findings_for_groups(&groups);
        let rendered: Vec<String> = findings.iter().map(Finding::render).collect();
        assert_eq!(
            rendered,
            vec!["a/src/x.rs:3: ASP502", "b/src/y.rs:9: ASP502"]
        );
    }
}
