//! Whole-workspace Rust duplicate-TYPE detector (functional core).
//!
//! Finds a struct or enum CONCEPT declared in more than one crate of a
//! Cargo workspace, along two axes. Pebbles: asp-ce6.4, asp-11d.
//!
//! 1. **Same name, same shape** — the original axis. Two declarations that
//!    share only a name, with a different shape, are two separate concepts
//!    and are not reported; two declarations of the same name and shape
//!    confined to one crate are not reported either, since the request is
//!    about a concept crossing a crate boundary. A declaration's *shape*
//!    ignores field/element types and visibility, keeping only its
//!    structural skeleton:
//!    - a unit struct (`struct Foo;`) shapes as `struct:unit`;
//!    - a tuple struct (`struct Foo(T1, T2)`) shapes as its field COUNT
//!      only (`struct:tuple:2`), so `Nanos(u64)`, `Nanos(i64)` and
//!      `Nanos(pub u64)` — three real lobaria declarations backing one
//!      `Nanos` amount — shape identically despite differing width,
//!      signedness and visibility;
//!    - a named-field struct (`struct Foo { a: T1, b: T2 }`) shapes as its
//!      ordered field NAME list (`struct:fields:a,b`), ignoring each
//!      field's type;
//!    - an enum shapes as its ordered variant NAME list
//!      (`enum:variants:A,B`), ignoring each variant's payload.
//!
//! 2. **Renamed / reordered structural duplicate** — the name-independent
//!    axis (asp-11d). A declaration's *structural signature* is keyed on
//!    field/variant names and types (not the declaration's own name) and
//!    is order-INSENSITIVE, so it catches a concept copied under a new
//!    name or with its fields/variants shuffled — without flagging the
//!    idiomatic distinct-newtype pattern:
//!    - a NAMED struct signs as the SORTED MULTISET of its `name:type`
//!      field pairs (`struct:named:a:i64,b:i64`), ignoring the struct's
//!      own name, visibility and field order — so `Written { pcap: Vec<u8>,
//!      note: String }` and `Fixture { pcap: Vec<u8>, note: String }` sign
//!      identically (a rename) and `Row { a: i64, b: i64 }` matches `Row {
//!      b: i64, a: i64 }` (a reorder), while `Sizing { entry: u64, trim:
//!      u64 }` and `Stated { slot: u64, micros: u64 }` — both `{u64, u64}`
//!      but differently named — stay apart;
//!    - a TUPLE struct signs as the SORTED MULTISET of its field types, but
//!      ONLY when it has two or more fields. A single-field tuple newtype
//!      (`struct Lamports(u64)`) carries NO signature: the newtype idiom
//!      deliberately mints many structurally identical wrappers over one
//!      primitive to give them distinct types (`Lamports` vs `TokenUnits`
//!      vs `UsdMicros`, all `u64`), so grouping them would be a false
//!      positive on correct, idiomatic Rust;
//!    - an enum signs as the SORTED SET of its variant descriptors, each a
//!      variant's own NAME plus its payload's sorted field types
//!      (`enum:Err(String);Ok(u64)`) — so a renamed enum whose variants
//!      are unchanged, or one whose variants were reordered, signs
//!      identically, while two unrelated binary enums (`Cut{Take,Skip}`
//!      vs `Run{Active,Done}`) do not, because their variant names differ.
//!
//! Unit and single-field-tuple structs and empty declarations carry no
//! structural signature and never join this axis. A structural group is
//! reported only when it spans more than one `(name, shape)` key — i.e. it
//! genuinely adds a rename or reorder that axis 1 did not already report.
//!
//! Both axes require a group to span TWO OR MORE distinct crates.
//!
//! No file, process, or exit code appears here — those live in the binary
//! at `src/bin/aspergillus_rust_dup_type_check.rs`.

use std::collections::{HashMap, HashSet};

use ast_grep_core::tree_sitter::StrDoc;
use ast_grep_core::Node;
use ast_grep_language::{LanguageExt, SupportLang};

use crate::Finding;

/// The ASP id every finding of this check reports.
pub const RULE_ID: &str = "ASP502";

type RNode<'r> = Node<'r, StrDoc<SupportLang>>;

/// One struct or enum declaration: its crate, file, 1-based start line,
/// declared name, shape fingerprint, and name-independent structural
/// signature.
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
    /// The shape fingerprint two same-named declarations compare by
    /// (axis 1; ignores field/variant types).
    pub shape: String,
    /// The name-independent structural signature two declarations of any
    /// name compare by (axis 2; keyed on sorted field/variant types). The
    /// empty string means the declaration carries no signature (a unit or
    /// empty declaration) and never joins the structural axis.
    pub signature: String,
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

/// A type node's comparison key: its source text with internal whitespace
/// runs collapsed to single spaces, so `Vec<u8>` and `Vec< u8 >` compare
/// equal.
fn type_key(node: &RNode<'_>) -> String {
    node.text().split_whitespace().collect::<Vec<_>>().join(" ")
}

/// A tuple struct's or tuple enum-variant's field body
/// (`ordered_field_declaration_list`, e.g. `(pub u64)`): the count of its
/// declared fields, ignoring each field's own type and visibility. Every
/// child of this body is punctuation, a `visibility_modifier`, or exactly
/// one type node per field, so counting past those two exclusions counts
/// the fields.
fn tuple_arity(body: &RNode<'_>) -> usize {
    tuple_field_type_nodes(body).len()
}

/// The type nodes of a tuple body (`ordered_field_declaration_list`), one
/// per field, skipping punctuation, `visibility_modifier`s and attributes.
fn tuple_field_type_nodes<'r>(body: &RNode<'r>) -> Vec<RNode<'r>> {
    body.children()
        .filter(|child| {
            !matches!(
                child.kind().as_ref(),
                "(" | ")" | "," | "visibility_modifier" | "attribute_item"
            )
        })
        .collect()
}

/// A tuple body's field types (`(pub u64, String)` -> `["u64", "String"]`),
/// ignoring visibility and declaration position.
fn tuple_field_types(body: &RNode<'_>) -> Vec<String> {
    tuple_field_type_nodes(body).iter().map(type_key).collect()
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

/// A named-field body's field types (`{ a: i32, b: String }` -> `["i32",
/// "String"]`), ignoring each field's name and visibility.
fn named_field_types(body: &RNode<'_>) -> Vec<String> {
    body.children()
        .filter(|child| child.kind().as_ref() == "field_declaration")
        .filter_map(|decl| decl.field("type"))
        .map(|t| type_key(&t))
        .collect()
}

/// A named-field body's `name:type` pairs (`{ a: i32, b: String }` ->
/// `["a:i32", "b:String"]`), ignoring visibility. The field NAME is kept:
/// two named structs are a structural duplicate only when they share the
/// same set of field names AND types, so `Sizing { entry: u64, trim: u64 }`
/// and `Stated { slot: u64, micros: u64 }` — both `{u64, u64}` but named
/// differently — are correctly kept apart.
fn named_field_pairs(body: &RNode<'_>) -> Vec<String> {
    body.children()
        .filter(|child| child.kind().as_ref() == "field_declaration")
        .filter_map(|decl| {
            let name = child_of_kind(&decl, "field_identifier")?
                .text()
                .into_owned();
            let ty = decl.field("type").map(|t| type_key(&t)).unwrap_or_default();
            Some(format!("{name}:{ty}"))
        })
        .collect()
}

/// A `struct_item` node's shape fingerprint (axis 1). See the module doc
/// comment for the three cases (unit, tuple, named-field).
fn struct_shape(node: &RNode<'_>) -> String {
    if let Some(body) = child_of_kind(node, "field_declaration_list") {
        format!("struct:fields:{}", named_field_names(&body).join(","))
    } else if let Some(body) = child_of_kind(node, "ordered_field_declaration_list") {
        format!("struct:tuple:{}", tuple_arity(&body))
    } else {
        "struct:unit".to_string()
    }
}

/// An `enum_item` node's shape fingerprint (axis 1): its ordered
/// variant-name list, ignoring each variant's own payload.
fn enum_shape(node: &RNode<'_>) -> String {
    let variants: Vec<String> = enum_variants(node)
        .filter_map(|variant| child_of_kind(&variant, "identifier"))
        .map(|ident| ident.text().into_owned())
        .collect();
    format!("enum:variants:{}", variants.join(","))
}

/// Every `enum_variant` child of an `enum_item`, in declaration order.
fn enum_variants<'r>(node: &RNode<'r>) -> impl Iterator<Item = RNode<'r>> {
    child_of_kind(node, "enum_variant_list")
        .into_iter()
        .flat_map(|list| list.children().collect::<Vec<_>>())
        .filter(|child| child.kind().as_ref() == "enum_variant")
}

/// A `struct_item` node's name-independent structural signature (axis 2),
/// or the empty string when the declaration carries none (and so never
/// joins the structural axis):
/// - a NAMED struct signs as the sorted multiset of its `name:type` field
///   pairs, ignoring the struct's own name, visibility and field order —
///   so a copy under a new struct name or with its fields reordered signs
///   identically, while two structs with the same field TYPES but
///   different field names stay apart;
/// - a TUPLE struct signs, only when it has TWO OR MORE fields, as the
///   sorted multiset of its field types. A single-field tuple newtype
///   (`struct Lamports(u64)`) carries NO signature: the newtype idiom
///   deliberately mints many structurally identical wrappers over one
///   primitive to give them distinct types (`Lamports` vs `TokenUnits`),
///   so grouping them would be a false positive on correct Rust;
/// - a unit or empty struct carries no signature.
fn struct_signature(node: &RNode<'_>) -> String {
    if let Some(body) = child_of_kind(node, "field_declaration_list") {
        let mut pairs = named_field_pairs(&body);
        if pairs.is_empty() {
            return String::new();
        }
        pairs.sort();
        format!("struct:named:{}", pairs.join(","))
    } else if let Some(body) = child_of_kind(node, "ordered_field_declaration_list") {
        let mut types = tuple_field_types(&body);
        if types.len() < 2 {
            return String::new();
        }
        types.sort();
        format!("struct:tuple:{}", types.join(","))
    } else {
        String::new()
    }
}

/// One enum variant's descriptor for the structural signature: its own
/// NAME plus its payload's sorted field types, so a renamed enum whose
/// variant names are unchanged still matches, but two enums with
/// different variant names never do.
fn variant_descriptor(variant: &RNode<'_>) -> String {
    let name = child_of_kind(variant, "identifier")
        .map(|ident| ident.text().into_owned())
        .unwrap_or_default();
    let payload = if let Some(body) = child_of_kind(variant, "ordered_field_declaration_list") {
        let mut types = tuple_field_types(&body);
        types.sort();
        format!("({})", types.join(","))
    } else if let Some(body) = child_of_kind(variant, "field_declaration_list") {
        let mut types = named_field_types(&body);
        types.sort();
        format!("{{{}}}", types.join(","))
    } else {
        String::new()
    };
    format!("{name}{payload}")
}

/// An `enum_item` node's name-independent structural signature (axis 2):
/// the sorted set of its variant descriptors, ignoring the enum's own
/// name and its variant order. An empty enum carries no signature.
fn enum_signature(node: &RNode<'_>) -> String {
    let mut descriptors: Vec<String> = enum_variants(node)
        .map(|variant| variant_descriptor(&variant))
        .collect();
    if descriptors.is_empty() {
        return String::new();
    }
    descriptors.sort();
    descriptors.dedup();
    format!("enum:{}", descriptors.join(";"))
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
            let is_struct = node.kind().as_ref() == "struct_item";
            let shape = if is_struct {
                struct_shape(&node)
            } else {
                enum_shape(&node)
            };
            let signature = if is_struct {
                struct_signature(&node)
            } else {
                enum_signature(&node)
            };
            Some(TypeOccurrence {
                crate_id: crate_id.to_string(),
                path: path.to_string(),
                line,
                name,
                shape,
                signature,
            })
        })
        .collect()
}

/// Sorts a group's members by path then line, then the groups themselves
/// by their first member, for deterministic output.
fn sort_groups(groups: &mut [Vec<TypeOccurrence>]) {
    for members in groups.iter_mut() {
        members.sort_by(|a, b| a.path.cmp(&b.path).then(a.line.cmp(&b.line)));
    }
    groups.sort_by(|a, b| a[0].path.cmp(&b[0].path).then(a[0].line.cmp(&b[0].line)));
}

/// Whether a bucket of occurrences spans two or more distinct crates.
fn spans_multiple_crates(members: &[&TypeOccurrence]) -> bool {
    members
        .iter()
        .map(|m| m.crate_id.as_str())
        .collect::<HashSet<_>>()
        .len()
        > 1
}

/// Axis 1 groups: occurrences sharing an identical `(name, shape)` key,
/// where the group spans two or more distinct crates.
fn name_shape_groups(occurrences: &[TypeOccurrence]) -> Vec<Vec<TypeOccurrence>> {
    let mut buckets: HashMap<(&str, &str), Vec<&TypeOccurrence>> = HashMap::new();
    for occurrence in occurrences {
        buckets
            .entry((occurrence.name.as_str(), occurrence.shape.as_str()))
            .or_default()
            .push(occurrence);
    }
    buckets
        .into_values()
        .filter(|members| spans_multiple_crates(members))
        .map(|members| members.into_iter().cloned().collect())
        .collect()
}

/// Axis 2 groups: occurrences sharing an identical structural signature,
/// where the group spans two or more distinct crates AND more than one
/// `(name, shape)` key — i.e. a rename (distinct names) or a reorder
/// (distinct ordered shapes) that axis 1 did not already report. An empty
/// signature (a unit or empty declaration) never participates.
fn structural_groups(occurrences: &[TypeOccurrence]) -> Vec<Vec<TypeOccurrence>> {
    let mut buckets: HashMap<&str, Vec<&TypeOccurrence>> = HashMap::new();
    for occurrence in occurrences {
        if occurrence.signature.is_empty() {
            continue;
        }
        buckets
            .entry(occurrence.signature.as_str())
            .or_default()
            .push(occurrence);
    }
    buckets
        .into_values()
        .filter(|members| {
            spans_multiple_crates(members)
                && members
                    .iter()
                    .map(|m| (m.name.as_str(), m.shape.as_str()))
                    .collect::<HashSet<_>>()
                    .len()
                    > 1
        })
        .map(|members| members.into_iter().cloned().collect())
        .collect()
}

/// Every cross-crate duplicate group, along both axes (same name + shape,
/// and renamed/reordered structural duplicate). A concept confined to one
/// crate, however many times it repeats there, is not reported. Groups are
/// sorted by their first member's path then line, for deterministic
/// output; members within a group are sorted the same way. A single
/// occurrence may appear in more than one group (e.g. one member of a
/// same-name pair that also has a renamed twin elsewhere); `findings_for_groups`
/// collapses those to one finding per source location.
pub fn duplicate_groups(occurrences: &[TypeOccurrence]) -> Vec<Vec<TypeOccurrence>> {
    let mut groups = name_shape_groups(occurrences);
    groups.extend(structural_groups(occurrences));
    sort_groups(&mut groups);
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
/// sorted by path then line and deduplicated by source location — so a
/// declaration reported by both axes yields a single finding.
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
    findings.dedup_by(|a, b| a.path == b.path && a.line == b.line);
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
    fn a_renamed_named_struct_is_a_structural_duplicate() {
        // asp-11d probe (refined): a struct copied under a NEW name but
        // with identical field names and types. Axis 1 keys on the
        // declared name, so it is silent; the structural axis reports both.
        let one = type_occurrences(
            "slot-extractor-oracle/src/extractor.rs",
            "slot-extractor-oracle",
            "pub struct Written { pcap: Vec<u8>, note: String }\n",
        );
        let two = type_occurrences(
            "slot-extractor/src/extract.rs",
            "slot-extractor",
            "pub struct Fixture { pcap: Vec<u8>, note: String }\n",
        );
        let mut occurrences = one;
        occurrences.extend(two);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0].len(), 2);
        let names: HashSet<&str> = groups[0].iter().map(|m| m.name.as_str()).collect();
        assert_eq!(
            names,
            ["Written", "Fixture"].into_iter().collect::<HashSet<_>>()
        );
    }

    #[test]
    fn distinct_single_field_u64_newtypes_are_not_flagged() {
        // The newtype idiom deliberately mints distinct wrappers over one
        // primitive; two unrelated `u64` newtypes are correct Rust and must
        // never be reported as a structural duplicate.
        let one = type_occurrences(
            "pump-strategy/src/units.rs",
            "pump-strategy",
            "pub struct Lamports(u64);\n",
        );
        let two = type_occurrences(
            "backtest/src/land.rs",
            "backtest",
            "pub struct LandSeed(u64);\n",
        );
        let mut occurrences = one;
        occurrences.extend(two);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups, Vec::<Vec<TypeOccurrence>>::new());
    }

    #[test]
    fn named_structs_sharing_only_field_types_are_not_collapsed() {
        // Both `{u64, u64}`, but their field NAMES differ, so they are two
        // distinct concepts, not a rename.
        let one = type_occurrences(
            "chart/src/strategy_contract.rs",
            "chart",
            "pub struct Sizing { entry_lamports: u64, trim_pct: u64 }\n",
        );
        let two = type_occurrences(
            "price-feed-oracle/src/message.rs",
            "price-feed-oracle",
            "pub struct Stated { slot: u64, micros: u64 }\n",
        );
        let mut occurrences = one;
        occurrences.extend(two);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups, Vec::<Vec<TypeOccurrence>>::new());
    }

    #[test]
    fn a_reordered_multi_field_tuple_struct_is_a_structural_duplicate() {
        // Multi-field tuple structs are rarely the distinct-unit idiom, so
        // they join the structural axis on their sorted field-type
        // multiset — catching a copy whose fields were reordered.
        let one = type_occurrences(
            "crate-a/src/a.rs",
            "crate-a",
            "pub struct Pair(u64, String);\n",
        );
        let two = type_occurrences(
            "crate-b/src/b.rs",
            "crate-b",
            "pub struct Duo(String, u64);\n",
        );
        let mut occurrences = one;
        occurrences.extend(two);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0].len(), 2);
    }

    #[test]
    fn a_reordered_named_struct_is_a_structural_duplicate() {
        // Same name, same field-type multiset, fields shuffled: axis 1's
        // ordered field-name list differs, so only the structural axis
        // reports it.
        let one = type_occurrences(
            "crate-a/src/a.rs",
            "crate-a",
            "pub struct Row { a: i64, b: i64 }\n",
        );
        let two = type_occurrences(
            "crate-b/src/b.rs",
            "crate-b",
            "pub struct Row { b: i64, a: i64 }\n",
        );
        let mut occurrences = one;
        occurrences.extend(two);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0].len(), 2);
    }

    #[test]
    fn a_reordered_enum_is_a_structural_duplicate() {
        let one = type_occurrences(
            "crate-a/src/a.rs",
            "crate-a",
            "pub enum Phase { Start, Stop }\n",
        );
        let two = type_occurrences(
            "crate-b/src/b.rs",
            "crate-b",
            "pub enum Phase { Stop, Start }\n",
        );
        let mut occurrences = one;
        occurrences.extend(two);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0].len(), 2);
    }

    #[test]
    fn a_renamed_enum_with_unchanged_variants_is_a_structural_duplicate() {
        let one = type_occurrences(
            "crate-a/src/a.rs",
            "crate-a",
            "pub enum Status { Ok, Err(String) }\n",
        );
        let two = type_occurrences(
            "crate-b/src/b.rs",
            "crate-b",
            "pub enum Outcome { Ok, Err(String) }\n",
        );
        let mut occurrences = one;
        occurrences.extend(two);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0].len(), 2);
    }

    #[test]
    fn distinct_binary_enums_with_different_variant_names_are_not_collapsed() {
        // Two two-unit-variant enums are structurally similar but their
        // variant names differ, so they are distinct concepts, not a
        // rename — the variant-name-bearing signature keeps them apart.
        let cut_a = type_occurrences(
            "crate-a/src/a.rs",
            "crate-a",
            "pub enum Cut { Take, Skip }\n",
        );
        let cut_b = type_occurrences(
            "crate-b/src/b.rs",
            "crate-b",
            "pub enum Cut { Take, Skip }\n",
        );
        let run_a = type_occurrences(
            "crate-a/src/c.rs",
            "crate-a",
            "pub enum Run { Active, Done }\n",
        );
        let run_b = type_occurrences(
            "crate-b/src/d.rs",
            "crate-b",
            "pub enum Run { Active, Done }\n",
        );
        let mut occurrences = cut_a;
        occurrences.extend(cut_b);
        occurrences.extend(run_a);
        occurrences.extend(run_b);
        let groups = duplicate_groups(&occurrences);
        // Two axis-1 groups (Cut, Run), and NO structural group merging
        // Cut with Run.
        assert_eq!(groups.len(), 2);
        for group in &groups {
            let names: HashSet<&str> = group.iter().map(|m| m.name.as_str()).collect();
            assert_eq!(names.len(), 1, "Cut and Run must not be collapsed");
        }
    }

    #[test]
    fn unit_structs_with_different_names_are_not_collapsed() {
        let one = type_occurrences("crate-a/src/a.rs", "crate-a", "pub struct Owed;\n");
        let two = type_occurrences("crate-b/src/b.rs", "crate-b", "pub struct Hole;\n");
        let mut occurrences = one;
        occurrences.extend(two);
        let groups = duplicate_groups(&occurrences);
        assert_eq!(groups, Vec::<Vec<TypeOccurrence>>::new());
    }

    #[test]
    fn a_same_name_pair_with_a_renamed_twin_yields_one_finding_per_location() {
        // `Balance { amount: u64 }` appears in two crates (axis 1) and
        // `Lamports { amount: u64 }` is its renamed twin (axis 2). The two
        // Balance locations sit in both a name-shape group and the
        // structural group, but each source location must render once.
        let bal_a = type_occurrences(
            "crate-a/src/a.rs",
            "crate-a",
            "pub struct Balance { amount: u64 }\n",
        );
        let bal_b = type_occurrences(
            "crate-b/src/b.rs",
            "crate-b",
            "pub struct Balance { amount: u64 }\n",
        );
        let lam = type_occurrences(
            "crate-c/src/c.rs",
            "crate-c",
            "pub struct Lamports { amount: u64 }\n",
        );
        let mut occurrences = bal_a;
        occurrences.extend(bal_b);
        occurrences.extend(lam);
        let groups = duplicate_groups(&occurrences);
        let findings = findings_for_groups(&groups);
        let rendered: Vec<String> = findings.iter().map(Finding::render).collect();
        assert_eq!(
            rendered,
            vec![
                "crate-a/src/a.rs:1: ASP502",
                "crate-b/src/b.rs:1: ASP502",
                "crate-c/src/c.rs:1: ASP502",
            ]
        );
    }

    #[test]
    fn crate_id_for_path_picks_the_longest_matching_root() {
        let roots = vec!["".to_string(), "statechart".to_string()];
        let id = crate_id_for_path(std::path::Path::new("statechart/src/units.rs"), &roots);
        assert_eq!(id, "statechart");
    }

    #[test]
    fn apply_allowlist_drops_only_the_named_group() {
        // Distinct field types keep each concept on axis 1 only, so this
        // exercises allowlist mechanics without the structural axis.
        let nanos = type_occurrences("a/src/units.rs", "a", "pub struct Nanos(i64);\n");
        let nanos_b = type_occurrences("b/src/units.rs", "b", "pub struct Nanos(u64);\n");
        let receipt = type_occurrences("a/src/edge.rs", "a", "pub struct Receipt(String);\n");
        let receipt_b = type_occurrences("b/src/units.rs", "b", "pub struct Receipt(String);\n");
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
                signature: "struct:tuple:u64".to_string(),
            },
            TypeOccurrence {
                crate_id: "b".to_string(),
                path: "b/src/y.rs".to_string(),
                line: 9,
                name: "Nanos".to_string(),
                shape: "struct:tuple:1".to_string(),
                signature: "struct:tuple:u64".to_string(),
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
