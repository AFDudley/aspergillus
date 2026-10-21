//! Crate A: genuinely-distinct domain types. Nothing here structurally
//! duplicates crate B. Synthetic; never built.

/// A u64 newtype. Crate B declares `TokenUnits`, ALSO a u64 newtype, but
/// the newtype idiom keeps them deliberately distinct: single-field tuple
/// newtypes never join the structural axis, so this pair is not reported.
pub struct Lamports(pub u64);

/// A sizing record: two u64 fields. Crate B's `Stated` has the same field
/// types but different field NAMES, so it is a different concept.
pub struct Sizing {
    pub entry_lamports: u64,
    pub trim_pct: u64,
}

/// A binary decision. Crate B's `Run` has different variant names.
pub enum Cut {
    Take,
    Skip,
}
