//! The generator: the contract as the Rust chart types.
//!
//! Concept: This module writes `statechart/src/chart.rs` from a [`Chart`],
//! and names every Rust item the file holds, so the conformance gate reads
//! the same names the generator wrote.
//!
//! One module per region, one unit struct per substate, one closed enum per
//! transition for its outcome (a tuple variant per target, a unit variant per
//! refusal), and one signature `fn name(from, on) -> Hole<Outcome>` per
//! transition. The body is a hole, unless `crate::bodies` derives it. A transition
//! with more than one source substate takes a closed enum of them. The events
//! are one module of unit structs, and the slot contract is two closed enums
//! over them. Everything here is pure: the same chart gives the same bytes,
//! formatted as rustfmt formats them, so `cargo fmt --check` has nothing to say
//! about the file.

use std::collections::BTreeMap;
use std::collections::BTreeSet;

use crate::bodies::derived_target;
use crate::contract::{Chart, Region, Transition};

/// The modules of the generated file that are not regions.
pub const RESERVED_MODULES: [&str; 2] = ["event", "slot"];

/// The widest line rustfmt keeps a signature on.
const MAX_WIDTH: usize = 100;

const DERIVE: &str = "#[derive(Clone, Copy, Debug, PartialEq, Eq)]";

/// Why a chart is not written as Rust.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Refused {
    /// A region's module name is one the file reserves for something else.
    ReservedModule(String),
    /// One outcome enum would hold two variants of one name.
    DuplicateVariant {
        /// The region.
        region: String,
        /// The transition.
        transition: String,
        /// The name written twice.
        name: String,
    },
    /// A concept is on more than one line, so it is not one doc line.
    ConceptNotOneLine(String),
    /// `carries` names an event the chart does not name.
    CarriesUnnamedEvent(String),
}

impl std::fmt::Display for Refused {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Refused::ReservedModule(name) => write!(f, "region {name} is a reserved module name"),
            Refused::DuplicateVariant {
                region,
                transition,
                name,
            } => write!(f, "{region}.{transition} names {name} twice"),
            Refused::ConceptNotOneLine(at) => write!(f, "{at}: a concept is not one line"),
            Refused::CarriesUnnamedEvent(name) => {
                write!(f, "carries names {name}, which is not an event")
            }
        }
    }
}

/// `collect_more` as `CollectMore`.
pub fn pascal(snake: &str) -> String {
    snake
        .split('_')
        .map(|part| {
            let mut chars = part.chars();
            chars.next().map_or_else(String::new, |first| {
                first.to_uppercase().chain(chars).collect::<String>()
            })
        })
        .collect()
}

/// The module a region is written as: its name in lower case.
pub fn module_name(region: &Region) -> String {
    region.name.to_ascii_lowercase()
}

/// The enum a transition returns: `CollectOutcome`.
pub fn outcome_name(transition: &Transition) -> String {
    format!("{}Outcome", pascal(&transition.name))
}

/// The enum of a transition's sources, when it has more than one: `EvictFrom`.
pub fn from_enum_name(transition: &Transition) -> String {
    format!("{}From", pascal(&transition.name))
}

/// The type of a transition's `from` parameter.
pub fn from_type(transition: &Transition) -> String {
    match transition.from.as_slice() {
        [only] => only.clone(),
        _ => from_enum_name(transition),
    }
}

/// The type of a transition's `on` parameter.
pub fn on_type(transition: &Transition) -> String {
    format!("event::{}", transition.on)
}

fn put(out: &mut String, text: &str) {
    out.push_str(text);
    out.push('\n');
}

fn doc(out: &mut String, indent: &str, text: &str) {
    put(out, &format!("{indent}/// {text}"));
}

/// The signature line or lines rustfmt writes for a transition.
fn signature(transition: &Transition) -> Vec<String> {
    let name = &transition.name;
    let from = from_type(transition);
    let on = on_type(transition);
    let returns = format!("Hole<{}>", outcome_name(transition));
    let one = format!("    pub const fn {name}(from: {from}, on: {on}) -> {returns} {{");
    if one.chars().count() <= MAX_WIDTH {
        return vec![one];
    }
    vec![
        format!("    pub const fn {name}("),
        format!("        from: {from},"),
        format!("        on: {on},"),
        format!("    ) -> {returns} {{"),
    ]
}

fn one_line<'a>(at: &str, text: &'a str) -> Result<&'a str, Refused> {
    if text.contains('\n') {
        Err(Refused::ConceptNotOneLine(at.to_owned()))
    } else {
        Ok(text)
    }
}

fn outcome_enum(out: &mut String, region: &Region, t: &Transition) -> Result<(), Refused> {
    let mut seen = BTreeSet::new();
    for name in t.to.iter().chain(&t.refusals) {
        if !seen.insert(name.as_str()) {
            return Err(Refused::DuplicateVariant {
                region: region.name.clone(),
                transition: t.name.clone(),
                name: name.clone(),
            });
        }
    }
    doc(
        out,
        "    ",
        &format!(
            "Concept: This value is what `{}` returned: the substate it moved to, or the refusal that left the source unchanged.",
            t.name
        ),
    );
    put(out, &format!("    {DERIVE}"));
    put(out, &format!("    pub enum {} {{", outcome_name(t)));
    for target in &t.to {
        doc(
            out,
            "        ",
            &format!("The transition moved to `{target}`."),
        );
        put(out, &format!("        {target}({target}),"));
    }
    for refusal in &t.refusals {
        doc(
            out,
            "        ",
            &format!("The guard refused with `{refusal}`."),
        );
        put(out, &format!("        {refusal},"));
    }
    put(out, "    }");
    Ok(())
}

fn from_enum(out: &mut String, t: &Transition) {
    if t.from.len() < 2 {
        return;
    }
    doc(
        out,
        "    ",
        &format!(
            "Concept: This value is the substate `{}` fires from.",
            t.name
        ),
    );
    put(out, &format!("    {DERIVE}"));
    put(out, &format!("    pub enum {} {{", from_enum_name(t)));
    for source in &t.from {
        doc(out, "        ", &format!("The region is in `{source}`."));
        put(out, &format!("        {source}({source}),"));
    }
    put(out, "    }");
}

fn transition_fn(out: &mut String, region: &Region, t: &Transition) {
    let derived = derived_target(&region.name, &t.name);
    let emits = if t.emits.is_empty() {
        String::new()
    } else {
        format!(", and emits {}", t.emits.join(", "))
    };
    doc(
        out,
        "    ",
        &format!(
            "The transition `{}`: it fires on `{}` from {}{emits}. {}",
            t.name,
            t.on,
            t.from.join(", "),
            derived.map_or_else(
                || "Its body is owed.".to_owned(),
                |target| format!("Its body is derived: it returns `{target}`.")
            )
        ),
    );
    put(out, "    #[must_use]");
    for line in signature(t) {
        put(out, &line);
    }
    put(out, "        let _ = (from, on);");
    match derived {
        Some(target) => put(
            out,
            &format!(
                "        Hole::Derived({}::{target}({target}))",
                outcome_name(t)
            ),
        ),
        None => put(out, "        Hole::Owed(Owed)"),
    }
    put(out, "    }");
}

fn region_module(out: &mut String, region: &Region) -> Result<(), Refused> {
    let module = module_name(region);
    if RESERVED_MODULES.contains(&module.as_str()) {
        return Err(Refused::ReservedModule(region.name.clone()));
    }
    doc(out, "", one_line(&region.name, &region.concept)?);
    put(out, &format!("pub mod {module} {{"));
    let owes = region
        .transitions
        .iter()
        .any(|t| derived_target(&region.name, &t.name).is_none());
    put(
        out,
        if owes {
            "    use super::{event, Hole, Owed};"
        } else {
            "    use super::{event, Hole};"
        },
    );
    for s in &region.substates {
        put(out, "");
        doc(out, "    ", one_line(&s.name, &s.concept)?);
        put(out, &format!("    {DERIVE}"));
        put(out, &format!("    pub struct {};", s.name));
    }
    for t in &region.transitions {
        put(out, "");
        outcome_enum(out, region, t)?;
        if t.from.len() > 1 {
            put(out, "");
            from_enum(out, t);
        }
        put(out, "");
        transition_fn(out, region, t);
    }
    put(out, "}");
    Ok(())
}

/// Every event the chart names, with its concept: the shell's inputs and
/// outputs with the contract's words, and every event a transition emits or
/// fires on with a sentence that says where it comes from.
fn events(chart: &Chart) -> Result<BTreeMap<String, String>, Refused> {
    let mut found = BTreeMap::new();
    for e in chart.inputs.iter().chain(&chart.outputs) {
        found.insert(
            e.name.clone(),
            format!("Concept: {}.", one_line(&e.name, &e.concept)?),
        );
    }
    let named = chart
        .regions
        .iter()
        .flat_map(|r| &r.transitions)
        .flat_map(|t| t.emits.iter().chain(std::iter::once(&t.on)))
        .chain(&chart.slot.down)
        .chain(&chart.slot.up);
    for name in named {
        found
            .entry(name.clone())
            .or_insert_with(|| "Concept: an event a transition of the chart emits.".to_owned());
    }
    Ok(found)
}

fn event_module(out: &mut String, chart: &Chart) -> Result<(), Refused> {
    doc(
        out,
        "",
        "Concept: This module is the events of the chart: one type for each.",
    );
    put(out, "pub mod event {");
    let events = events(chart)?;
    if let Some(unnamed) = chart
        .carries
        .iter()
        .find(|c| !events.contains_key(&c.event))
    {
        return Err(Refused::CarriesUnnamedEvent(unnamed.event.clone()));
    }
    for (i, (name, concept)) in events.iter().enumerate() {
        if i > 0 {
            put(out, "");
        }
        doc(out, "    ", concept);
        put(out, &format!("    {DERIVE}"));
        match chart.carries.iter().find(|c| &c.event == name) {
            Some(carried) => put(
                out,
                &format!("    pub struct {name}(pub {});", carried.rust_type),
            ),
            None => put(out, &format!("    pub struct {name};")),
        }
    }
    put(out, "}");
    Ok(())
}

fn slot_enum(out: &mut String, name: &str, gives: &str, events: &[String]) {
    doc(
        out,
        "    ",
        &format!("Concept: This value is one thing {gives}."),
    );
    put(out, &format!("    {DERIVE}"));
    if events.is_empty() {
        put(out, &format!("    pub enum {name} {{}}"));
        return;
    }
    put(out, &format!("    pub enum {name} {{"));
    for e in events {
        doc(out, "        ", &format!("The event `{e}`."));
        put(out, &format!("        {e}(event::{e}),"));
    }
    put(out, "    }");
}

fn slot_module(out: &mut String, chart: &Chart) {
    doc(
        out,
        "",
        &format!(
            "Concept: This module is the slot contract of `{}.{}`: what the occupant is given and what it gives back.",
            chart.slot.region, chart.slot.substate
        ),
    );
    put(out, "pub mod slot {");
    put(out, "    use super::event;");
    put(out, "");
    slot_enum(
        out,
        "Down",
        "the machine gives the occupant",
        &chart.slot.down,
    );
    put(out, "");
    slot_enum(out, "Up", "the occupant gives the machine", &chart.slot.up);
    put(out, "}");
}

const HEADER: &str = "//! The chart, as types. GENERATED from `docs/chart.json5`; do not edit.
//!
//! Concept: This module is the machine's chart: one module per region, one
//! type per substate, one signature per transition.
//!
//! `docs/chart.json5` is the only declaration (`docs/process.md`, \"Draw the
//! machine as a contract before any body\"). The `chart` crate writes this
//! file: `cargo run -q -p chart --bin chart-generate > statechart/src/chart.rs`.
//! `scripts/gates/chart-conformance` refuses any difference between this file
//! and the contract, in either direction. Each transition returns the closed
//! union of its targets and its refusals. Its body is a hole ([`Owed`]) until
//! `chart/src/bodies.rs` derives it.

/// Concept: This value marks a transition body that is owed: its signature is
/// declared and its derivation against the postcondition is the next step's
/// work.
///
/// A hole is a type, not a default: a caller that receives `Owed` has
/// received nothing it can act on, and the compiler makes every consumer say
/// so. [Brady 2017: treat an open hole as work you owe]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Owed;

/// Concept: This value is what a transition returns until its body is
/// derived: the outcome, or the hole.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Hole<T> {
    /// The derived outcome.
    Derived(T),
    /// The body is owed.
    Owed(Owed),
}
";

/// The Rust source of the chart: the same bytes for the same chart.
pub fn generate(chart: &Chart) -> Result<String, Refused> {
    let mut out = String::from(HEADER);
    put(&mut out, "");
    event_module(&mut out, chart)?;
    for region in &chart.regions {
        put(&mut out, "");
        region_module(&mut out, region)?;
    }
    put(&mut out, "");
    slot_module(&mut out, chart);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pascal_joins_the_parts() {
        assert_eq!(pascal("fill_parity"), "FillParity");
        assert_eq!(pascal("collect"), "Collect");
    }

    #[test]
    fn a_long_signature_wraps_as_rustfmt_wraps_it() {
        let t = Transition {
            name: "a_transition_with_a_long_name".to_owned(),
            from: vec!["A".to_owned(), "B".to_owned()],
            on: "AnEventWithALongName".to_owned(),
            to: vec!["A".to_owned()],
            refusals: Vec::new(),
            emits: Vec::new(),
        };
        assert_eq!(signature(&t).len(), 4);
    }
}
