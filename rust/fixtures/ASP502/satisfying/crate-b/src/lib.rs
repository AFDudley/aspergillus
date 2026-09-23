//! Crate B: genuinely-distinct domain types. Nothing here structurally
//! duplicates crate A. Synthetic; never built.

/// Also a u64 newtype, but a DIFFERENT concept from crate A's `Lamports`.
/// Single-field tuple newtypes carry no structural signature.
pub struct TokenUnits(pub u64);

/// A price message: two u64 fields, but named differently from crate A's
/// `Sizing`, so the structural axis keeps them apart.
pub struct Stated {
    pub slot: u64,
    pub micros: u64,
}

/// A different binary decision: different enum name AND different variant
/// names from crate A's `Cut`.
pub enum Run {
    Active,
    Done,
}
