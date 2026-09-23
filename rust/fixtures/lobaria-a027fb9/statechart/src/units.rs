//! Units: every quantity is its own type.
//!
//! Concept: This module is the set of unit newtypes every quantity in the
//! machine is expressed in.
//!
//! A bare integer in the core is untyped (`docs/process.md`, "Units are
//! types"). The compiler refuses to add lamports to token units because they
//! are different types; arithmetic within a unit is checked and refuses on
//! overflow rather than wrapping. Scales are stated on the type, never in a
//! comment at a use site.

use core::fmt;

use serde::de::{Error, SeqAccess, Visitor};
use serde::ser::SerializeTuple;
use serde::{Deserialize, Deserializer, Serialize, Serializer};

use crate::Refusal;
/// Define a `Copy` newtype over one integer with `new`/`get`. The single
/// place an integer field is permitted in the core is inside a newtype made
/// here or by `unit_u64!`; the core-types gate checks exactly that.
macro_rules! newtype {
    ($(#[$meta:meta])* $name:ident($int:ty)) => {
        $(#[$meta])*
        #[derive(
            Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash,
            ::serde::Serialize, ::serde::Deserialize,
        )]
        pub struct $name($int);

        impl $name {
            /// Wrap a raw value.
            #[must_use]
            pub const fn new(raw: $int) -> Self {
                Self(raw)
            }

            /// The raw value.
            #[must_use]
            pub const fn get(self) -> $int {
                self.0
            }
        }
    };
}
pub(crate) use newtype;

macro_rules! unit_u64 {
    ($(#[$meta:meta])* $name:ident) => {
        $(#[$meta])*
        #[derive(
            Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash,
            ::serde::Serialize, ::serde::Deserialize,
        )]
        pub struct $name(u64);

        impl $name {
            /// Wrap a raw count of this unit.
            #[must_use]
            pub const fn new(raw: u64) -> Self {
                Self(raw)
            }

            /// The raw count.
            #[must_use]
            pub const fn get(self) -> u64 {
                self.0
            }

            /// The sum, refused on overflow.
            pub const fn checked_add(self, rhs: Self) -> Result<Self, Refusal> {
                match self.0.checked_add(rhs.0) {
                    Some(sum) => Ok(Self(sum)),
                    None => Err(Refusal::Overflow),
                }
            }

            /// The difference, refused on underflow.
            pub const fn checked_sub(self, rhs: Self) -> Result<Self, Refusal> {
                match self.0.checked_sub(rhs.0) {
                    Some(difference) => Ok(Self(difference)),
                    None => Err(Refusal::Overflow),
                }
            }
        }
    };
}

unit_u64! {
    /// Concept: This value is an amount of SOL in lamports, the base unit of
    /// 10⁻⁹ SOL.
    ///
    /// [solana-sdk `native_token::LAMPORTS_PER_SOL`]
    Lamports
}

unit_u64! {
    /// Concept: This value is an amount of a mint's token in its base unit.
    ///
    /// pump.fun mints use six decimals: one whole token is 1,000,000 units.
    /// [pump.fun `PUMP_PROGRAM_README`, token decimals]
    TokenUnits
}

unit_u64! {
    /// Concept: This value is an amount of US dollars scaled by 10⁶.
    ///
    /// The unit of every price tick and every USD-denominated threshold.
    /// Never a float: $135.00 is `MicroUsd::new(135_000_000)`.
    MicroUsd
}

unit_u64! {
    /// Concept: This value is a Solana slot number.
    ///
    /// The leader's block-production interval a shred, entry, or transaction
    /// belongs to. [agave `sdk/clock`: `Slot`]
    Slot
}

/// Concept: This value is a signed change in lamports, such as a realized
/// profit or loss.
///
/// Distinct from [`Lamports`] so that a balance and a delta cannot be
/// confused; the only way to obtain one is from the difference of two
/// balances.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct LamportsDelta(i64);

impl LamportsDelta {
    /// The signed difference `after - before`, refused if it does not fit.
    pub const fn between(before: Lamports, after: Lamports) -> Result<Self, Refusal> {
        let (Ok(before), Ok(after)) = (i64_from(before.0), i64_from(after.0)) else {
            return Err(Refusal::Overflow);
        };
        match after.checked_sub(before) {
            Some(delta) => Ok(Self(delta)),
            None => Err(Refusal::Overflow),
        }
    }

    /// The raw signed count.
    #[must_use]
    pub const fn get(self) -> i64 {
        self.0
    }
}

const fn i64_from(raw: u64) -> Result<i64, Refusal> {
    if raw > i64::MAX as u64 {
        Err(Refusal::Overflow)
    } else {
        Ok(raw as i64)
    }
}

/// Concept: This value is a Meteora DLMM active bin, signed steps from the
/// reference bin (bin zero).
///
/// [Meteora DLMM: `active_id`]
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct BinId(i32);

impl BinId {
    /// Wrap a raw bin index.
    #[must_use]
    pub const fn new(raw: i32) -> Self {
        Self(raw)
    }

    /// The raw bin index.
    #[must_use]
    pub const fn get(self) -> i32 {
        self.0
    }
}

/// Concept: This value is a ratio in basis points, 10⁻⁴ of one.
///
/// A ratio may exceed one (a 3× take-profit trigger is `Bps::new(30_000)`).
/// A ratio that must not exceed one is a [`Fraction`].
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct Bps(u32);

impl Bps {
    /// Basis points in one whole.
    pub const ONE: Self = Self(10_000);

    /// Wrap a raw basis-point count.
    #[must_use]
    pub const fn new(raw: u32) -> Self {
        Self(raw)
    }

    /// The raw basis-point count.
    #[must_use]
    pub const fn get(self) -> u32 {
        self.0
    }
}

/// Concept: This value is a ratio in basis points that is at most one whole.
///
/// The type of a stop, a trim, and a trailing offset: the constructor refuses
/// more than 10,000 basis points, so a consumer never re-checks that a
/// fraction is a fraction.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(try_from = "Bps")]
pub struct Fraction(Bps);

impl TryFrom<Bps> for Fraction {
    type Error = Refusal;

    /// A fraction read back from the wire is refused above one whole, as
    /// [`Fraction::new`] refuses it.
    fn try_from(bps: Bps) -> Result<Self, Refusal> {
        Self::new(bps)
    }
}

impl Fraction {
    /// A fraction from basis points, refused above one whole.
    pub const fn new(bps: Bps) -> Result<Self, Refusal> {
        if bps.0 > Bps::ONE.0 {
            Err(Refusal::FractionAboveOne)
        } else {
            Ok(Self(bps))
        }
    }

    /// The fraction as basis points.
    #[must_use]
    pub const fn bps(self) -> Bps {
        self.0
    }
}

/// Concept: This value is an instant in nanoseconds since the Unix epoch, UTC.
///
/// The unit of a [`crate::edge::Receipt`]. Signed, because it is a point on
/// a line and durations between points are signed.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct Nanos(i64);

impl Nanos {
    /// Wrap a raw nanosecond count.
    #[must_use]
    pub const fn new(raw: i64) -> Self {
        Self(raw)
    }

    /// The raw nanosecond count.
    #[must_use]
    pub const fn get(self) -> i64 {
        self.0
    }

    /// The signed duration `self - earlier`, refused if it does not fit.
    pub const fn since(self, earlier: Self) -> Result<Self, Refusal> {
        match self.0.checked_sub(earlier.0) {
            Some(duration) => Ok(Self(duration)),
            None => Err(Refusal::Overflow),
        }
    }
}

/// Concept: This value is a price of one whole token in lamports, as a
/// fixed-point number scaled by 10¹⁸.
///
/// One type for the bonding curve and the pool, so a trailing stop compares
/// like with like across graduation. The scale is large enough that a
/// sub-lamport price of a six-decimal token is exact.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct Price(u128);

impl Price {
    /// The fixed-point scale: one lamport per whole token is `10^18`.
    pub const SCALE: u128 = 1_000_000_000_000_000_000;

    /// Wrap a raw scaled price.
    #[must_use]
    pub const fn new(scaled: u128) -> Self {
        Self(scaled)
    }

    /// The raw scaled price.
    #[must_use]
    pub const fn get(self) -> u128 {
        self.0
    }
}

/// Concept: This value is a Solana account address: 32 bytes.
///
/// In the core an address is bytes. Base58 is an encoding for humans and
/// exists only in the shell. [solana-sdk `pubkey::Pubkey`]
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub struct Pubkey([u8; 32]);

impl Pubkey {
    /// Wrap 32 address bytes.
    #[must_use]
    pub const fn new(bytes: [u8; 32]) -> Self {
        Self(bytes)
    }

    /// The address bytes.
    #[must_use]
    pub const fn bytes(&self) -> &[u8; 32] {
        &self.0
    }
}

/// Concept: This value is an Ed25519 transaction signature: 64 bytes.
///
/// The identity by which a decoded transaction is reconciled against the
/// chain's record. [solana-sdk `signature::Signature`]
///
/// Serde derives no impl for an array of 64, so the impls below write it as a
/// tuple of 64 bytes, the shape serde gives an array of 32.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Signature([u8; 64]);

impl Signature {
    /// Wrap 64 signature bytes.
    #[must_use]
    pub const fn new(bytes: [u8; 64]) -> Self {
        Self(bytes)
    }

    /// The signature bytes.
    #[must_use]
    pub const fn bytes(&self) -> &[u8; 64] {
        &self.0
    }
}

impl Serialize for Signature {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut tuple = serializer.serialize_tuple(SIGNATURE_BYTES)?;
        for byte in &self.0 {
            tuple.serialize_element(byte)?;
        }
        tuple.end()
    }
}

/// The bytes of a [`Signature`].
const SIGNATURE_BYTES: usize = 64;

/// Reads the 64 bytes of a [`Signature`] from a sequence.
struct SignatureVisitor;

impl<'de> Visitor<'de> for SignatureVisitor {
    type Value = Signature;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "a sequence of {SIGNATURE_BYTES} bytes")
    }

    fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Signature, A::Error> {
        let mut bytes = [0_u8; SIGNATURE_BYTES];
        for (at, slot) in bytes.iter_mut().enumerate() {
            *slot = seq
                .next_element()?
                .ok_or_else(|| A::Error::invalid_length(at, &self))?;
        }
        Ok(Signature(bytes))
    }
}

impl<'de> Deserialize<'de> for Signature {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        deserializer.deserialize_tuple(SIGNATURE_BYTES, SignatureVisitor)
    }
}
