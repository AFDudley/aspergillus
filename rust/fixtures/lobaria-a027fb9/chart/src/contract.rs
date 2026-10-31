//! The contract: the chart as a typed value.
//!
//! Concept: This module parses a [`Value`] into a [`Chart`], once.
//!
//! Parse, don't validate: a required field that is absent or of the wrong
//! kind is a [`Shape`] refusal naming where; a [`Chart`] that exists has every
//! field. What the chart *means* — reachability, dead ends, events with no
//! source — is `check`'s question, asked of a `Chart`, never of a `Value`.
//! Field names here are the file's field names (`docs/chart.json5`).

use crate::json5::Value;

/// A named, described thing: an input, an output, or a substate.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Described {
    /// The name, as written.
    pub name: String,
    /// Its one-line meaning (a substate's `Concept:` line).
    pub concept: String,
}

/// A transition: the signature `fn name(from, on) -> to | refusals`, with
/// `emits` the events its action places on a ring.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Transition {
    /// The imperative verb.
    pub name: String,
    /// Source substates.
    pub from: Vec<String>,
    /// The event it fires on.
    pub on: String,
    /// Target substates.
    pub to: Vec<String>,
    /// The guard's named failures; the source is unchanged.
    pub refusals: Vec<String>,
    /// Events emitted for other regions.
    pub emits: Vec<String>,
}

/// A region of the top-level composite state.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Region {
    /// Present participle of the verb driving it.
    pub name: String,
    /// Its one-line meaning.
    pub concept: String,
    /// How many instances and what bounds them.
    pub instances: String,
    /// Events that create an instance.
    pub created_by: Vec<String>,
    /// The initial substate.
    pub initial: String,
    /// Substates, in written order.
    pub substates: Vec<Described>,
    /// Final substates.
    pub finals: Vec<String>,
    /// Transitions, in written order.
    pub transitions: Vec<Transition>,
}

/// An event that carries a value: the event, and the Rust type it holds.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Carried {
    /// The event's name.
    pub event: String,
    /// The Rust type path the generated event struct holds, as written in the
    /// generated file.
    pub rust_type: String,
}

/// The strategy slot's contract.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Slot {
    /// The region holding the slot.
    pub region: String,
    /// The substate that is the hole.
    pub substate: String,
    /// Events lobaria gives the occupant.
    pub down: Vec<String>,
    /// Events the occupant gives lobaria.
    pub up: Vec<String>,
    /// What the occupant must declare.
    pub declares: Vec<String>,
    /// Regions the occupant may not touch.
    pub forbidden: Vec<String>,
}

/// The chart: the whole declaration.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Chart {
    /// Contract version.
    pub version: i64,
    /// The top-level composite state.
    pub initial: String,
    /// Events entering from the shell.
    pub inputs: Vec<Described>,
    /// Events leaving to the shell.
    pub outputs: Vec<Described>,
    /// The events that carry a value: the event, and the Rust type it holds.
    /// An event not named here is a unit struct.
    pub carries: Vec<Carried>,
    /// Orthogonal regions, in written order.
    pub regions: Vec<Region>,
    /// The strategy slot.
    pub slot: Slot,
}

/// Where the value is not a chart.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Shape {
    /// Dotted path to the field.
    pub at: String,
    /// What was expected.
    pub why: String,
}

fn shape(at: &str, why: &str) -> Shape {
    Shape {
        at: at.to_owned(),
        why: why.to_owned(),
    }
}

fn field<'a>(value: &'a Value, at: &str, key: &str) -> Result<&'a Value, Shape> {
    value
        .get(key)
        .ok_or_else(|| shape(&format!("{at}.{key}"), "field missing"))
}

fn optional_names(value: &Value, at: &str, key: &str) -> Result<Vec<String>, Shape> {
    match value.get(key) {
        None => Ok(Vec::new()),
        Some(v) => names_of(v, &format!("{at}.{key}")),
    }
}

fn string_at(value: &Value, at: &str, key: &str) -> Result<String, Shape> {
    match field(value, at, key)? {
        Value::Str(s) => Ok(s.clone()),
        Value::Object(_) | Value::Array(_) | Value::Int(_) | Value::Bool(_) | Value::Null => {
            Err(shape(&format!("{at}.{key}"), "a string"))
        }
    }
}

fn names_of(value: &Value, at: &str) -> Result<Vec<String>, Shape> {
    let Value::Array(items) = value else {
        return Err(shape(at, "an array of names"));
    };
    items
        .iter()
        .map(|v| match v {
            Value::Str(s) => Ok(s.clone()),
            Value::Object(_) | Value::Array(_) | Value::Int(_) | Value::Bool(_) | Value::Null => {
                Err(shape(at, "an array of names"))
            }
        })
        .collect()
}

fn names_at(value: &Value, at: &str, key: &str) -> Result<Vec<String>, Shape> {
    names_of(field(value, at, key)?, &format!("{at}.{key}"))
}

fn carries_at(value: &Value, at: &str) -> Result<Vec<Carried>, Shape> {
    let Some(carries) = value.get("carries") else {
        return Ok(Vec::new());
    };
    let Value::Object(members) = carries else {
        return Err(shape(&format!("{at}.carries"), "an object of event: type"));
    };
    members
        .iter()
        .map(|(event, v)| match v {
            Value::Str(rust_type) => Ok(Carried {
                event: event.clone(),
                rust_type: rust_type.clone(),
            }),
            Value::Object(_) | Value::Array(_) | Value::Int(_) | Value::Bool(_) | Value::Null => {
                Err(shape(&format!("{at}.carries.{event}"), "a Rust type path"))
            }
        })
        .collect()
}

fn described_at(value: &Value, at: &str, key: &str) -> Result<Vec<Described>, Shape> {
    let Value::Object(members) = field(value, at, key)? else {
        return Err(shape(&format!("{at}.{key}"), "an object of name: concept"));
    };
    members
        .iter()
        .map(|(name, v)| match v {
            Value::Str(concept) => Ok(Described {
                name: name.clone(),
                concept: concept.clone(),
            }),
            Value::Object(_) | Value::Array(_) | Value::Int(_) | Value::Bool(_) | Value::Null => {
                Err(shape(&format!("{at}.{key}.{name}"), "a concept string"))
            }
        })
        .collect()
}

fn transition(name: &str, value: &Value, at: &str) -> Result<Transition, Shape> {
    Ok(Transition {
        name: name.to_owned(),
        from: names_at(value, at, "from")?,
        on: string_at(value, at, "on")?,
        to: names_at(value, at, "to")?,
        refusals: optional_names(value, at, "refusals")?,
        emits: optional_names(value, at, "emits")?,
    })
}

fn region(name: &str, value: &Value, at: &str) -> Result<Region, Shape> {
    let Value::Object(members) = field(value, at, "transitions")? else {
        return Err(shape(
            &format!("{at}.transitions"),
            "an object of transitions",
        ));
    };
    let transitions = members
        .iter()
        .map(|(tname, v)| transition(tname, v, &format!("{at}.transitions.{tname}")))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(Region {
        name: name.to_owned(),
        concept: string_at(value, at, "concept")?,
        instances: string_at(value, at, "instances")?,
        created_by: names_at(value, at, "created_by")?,
        initial: string_at(value, at, "initial")?,
        substates: described_at(value, at, "substates")?,
        finals: names_at(value, at, "finals")?,
        transitions,
    })
}

fn slot(value: &Value, at: &str) -> Result<Slot, Shape> {
    Ok(Slot {
        region: string_at(value, at, "region")?,
        substate: string_at(value, at, "substate")?,
        down: names_at(value, at, "down")?,
        up: names_at(value, at, "up")?,
        declares: names_at(value, at, "declares")?,
        forbidden: names_at(value, at, "forbidden")?,
    })
}

/// The value as a chart, or where it is not one.
pub fn parse(value: &Value) -> Result<Chart, Shape> {
    let at = "chart";
    let version = match field(value, at, "version")? {
        Value::Int(n) => *n,
        Value::Object(_) | Value::Array(_) | Value::Str(_) | Value::Bool(_) | Value::Null => {
            return Err(shape("chart.version", "an integer"));
        }
    };
    let Value::Object(members) = field(value, at, "regions")? else {
        return Err(shape("chart.regions", "an object of regions"));
    };
    let regions = members
        .iter()
        .map(|(rname, v)| region(rname, v, &format!("chart.regions.{rname}")))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(Chart {
        version,
        initial: string_at(value, at, "initial")?,
        inputs: described_at(value, at, "inputs")?,
        outputs: described_at(value, at, "outputs")?,
        carries: carries_at(value, at)?,
        regions,
        slot: slot(field(value, at, "slot")?, "chart.slot")?,
    })
}
