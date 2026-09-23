//! Units: every quantity the strategy reads or emits is its own type.
//!
//! Concept: This module is the set of unit newtypes the strategy's core is
//! expressed in.
//!
//! A bare integer in the core is untyped (`docs/process.md`, "Units are
//! types"). Each newtype states its scale on the type. Arithmetic widens to
//! `u128` and refuses, by returning `None`, on a result that does not fit; a
//! percentage of a value never overflows, so it returns the value itself.

use serde::{Deserialize, Serialize};

/// Basis points in one whole: 10,000 basis points are 100%.
const WHOLE_BPS: u128 = 10_000;
/// Percent in one whole.
const WHOLE_PERCENT: u128 = 100;
/// Lamports in one SOL.
const LAMPORTS_PER_SOL: u128 = 1_000_000_000;
/// The pump.fun token supply in raw token units: 10⁹ tokens of 10⁶ each.
const SUPPLY_RAW: u128 = 1_000_000_000_000_000;
/// The scale of a curve price: lamports per raw token times 10¹⁸.
const PRICE_SCALE: u128 = 1_000_000_000_000_000_000;

/// Concept: This value is an amount of SOL in lamports, 10⁻⁹ SOL.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct Lamports(u64);

impl Lamports {
    /// Wrap a raw count of lamports.
    #[must_use]
    pub const fn new(raw: u64) -> Self {
        Self(raw)
    }

    /// The raw count.
    #[must_use]
    pub const fn get(self) -> u64 {
        self.0
    }

    /// The difference, saturating at zero.
    #[must_use]
    pub const fn saturating_sub(self, rhs: Self) -> Self {
        Self(self.0.saturating_sub(rhs.0))
    }

    /// The part of this amount that `part` names. A percent above 100 is
    /// clamped to this amount, so the result never exceeds it.
    #[must_use]
    pub fn portion(self, part: Percent) -> Self {
        let share = u128::from(self.0)
            .saturating_mul(u128::from(part.get()))
            .checked_div(WHOLE_PERCENT)
            .unwrap_or_default();
        Self(u64::try_from(share).unwrap_or(self.0).min(self.0))
    }
}

/// Concept: This value is an amount of raw token units of the pair's base.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct TokenUnits(u64);

impl TokenUnits {
    /// Wrap a raw count of token units.
    #[must_use]
    pub const fn new(raw: u64) -> Self {
        Self(raw)
    }

    /// The raw count.
    #[must_use]
    pub const fn get(self) -> u64 {
        self.0
    }
}

/// Concept: This value is an amount of USD in micro-USD, 10⁻⁶ USD.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct UsdMicros(u64);

impl UsdMicros {
    /// Wrap a raw count of micro-USD.
    #[must_use]
    pub const fn new(raw: u64) -> Self {
        Self(raw)
    }

    /// The raw count.
    #[must_use]
    pub const fn get(self) -> u64 {
        self.0
    }
}

/// Concept: This value is the price of one SOL in micro-USD.
///
/// It is the SOL/USD leg of the quote path, as a `PriceTick` carries it.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct UsdPerSol(u64);

impl UsdPerSol {
    /// Wrap a raw price in micro-USD per SOL.
    #[must_use]
    pub const fn new(raw: u64) -> Self {
        Self(raw)
    }

    /// The raw price.
    #[must_use]
    pub const fn get(self) -> u64 {
        self.0
    }
}

/// Concept: This value is a fraction in basis points, 10⁻⁴ of a whole.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct Bps(u32);

impl Bps {
    /// Wrap a raw count of basis points.
    #[must_use]
    pub const fn new(raw: u32) -> Self {
        Self(raw)
    }

    /// The raw count.
    #[must_use]
    pub const fn get(self) -> u32 {
        self.0
    }
}

/// Concept: This value is a fraction in percent of a whole.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct Percent(u8);

impl Percent {
    /// Wrap a raw percentage.
    #[must_use]
    pub const fn new(raw: u8) -> Self {
        Self(raw)
    }

    /// The raw percentage.
    #[must_use]
    pub const fn get(self) -> u8 {
        self.0
    }
}

/// Concept: This value is a span of time in nanoseconds.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct Nanos(u64);

impl Nanos {
    /// Wrap a raw count of nanoseconds.
    #[must_use]
    pub const fn new(raw: u64) -> Self {
        Self(raw)
    }

    /// The raw count.
    #[must_use]
    pub const fn get(self) -> u64 {
        self.0
    }
}

/// Concept: This value is the receipt time of an event, in nanoseconds since
/// the Unix epoch, read from the shell's clock and never from a payload.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct Receipt(i64);

impl Receipt {
    /// Wrap a raw count of nanoseconds since the epoch.
    #[must_use]
    pub const fn new(raw: i64) -> Self {
        Self(raw)
    }

    /// The raw count.
    #[must_use]
    pub const fn get(self) -> i64 {
        self.0
    }

    /// The time from `earlier` to this receipt; zero if `earlier` is later.
    #[must_use]
    pub fn since(self, earlier: Self) -> Nanos {
        let span = i128::from(self.0).saturating_sub(i128::from(earlier.0));
        Nanos(u64::try_from(span.max(0)).unwrap_or(u64::MAX))
    }
}

/// Concept: This value is the mint of the pair's base token, 32 bytes as the
/// wire holds it.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub struct Mint([u8; 32]);

impl Mint {
    /// Wrap the 32 bytes of a mint.
    #[must_use]
    pub const fn new(raw: [u8; 32]) -> Self {
        Self(raw)
    }

    /// The 32 bytes.
    #[must_use]
    pub const fn get(self) -> [u8; 32] {
        self.0
    }
}

/// Concept: This value is the marginal price of one raw token on the curve,
/// in lamports times 10¹⁸.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct CurvePrice(u128);

impl CurvePrice {
    /// Wrap a raw scaled price.
    #[must_use]
    pub const fn new(raw: u128) -> Self {
        Self(raw)
    }

    /// The raw scaled price.
    #[must_use]
    pub const fn get(self) -> u128 {
        self.0
    }

    /// This price times `fraction` basis points of a whole, rounded down.
    ///
    /// A product too wide for `u128` is taken in the other order, which
    /// keeps the result total and loses only the last digits.
    #[must_use]
    pub fn scaled(self, fraction: Bps) -> Self {
        let bps = u128::from(fraction.get());
        let scaled = match self.0.checked_mul(bps) {
            Some(product) => product.checked_div(WHOLE_BPS).unwrap_or_default(),
            None => self
                .0
                .checked_div(WHOLE_BPS)
                .unwrap_or_default()
                .saturating_mul(bps),
        };
        Self(scaled)
    }

    /// The larger of two prices.
    #[must_use]
    pub const fn max(self, other: Self) -> Self {
        if self.0 >= other.0 {
            self
        } else {
            other
        }
    }
}

/// Concept: This value is the bonding curve's virtual reserves, the two
/// numbers its price and market cap are read from.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Curve {
    /// The virtual token reserve.
    pub virtual_token: TokenUnits,
    /// The virtual SOL reserve.
    pub virtual_sol: Lamports,
}

impl Curve {
    /// The marginal price: `virtual_sol · 10¹⁸ / virtual_token`. `None` when
    /// the token reserve is zero or the price does not fit.
    #[must_use]
    pub fn price(self) -> Option<CurvePrice> {
        u128::from(self.virtual_sol.get())
            .checked_mul(PRICE_SCALE)?
            .checked_div(u128::from(self.virtual_token.get()))
            .map(CurvePrice)
    }

    /// The market cap in micro-USD at the SOL price: the whole supply at the
    /// marginal price, in lamports, converted through `usd`. `None` when the
    /// token reserve is zero or the result does not fit.
    #[must_use]
    pub fn market_cap(self, usd: UsdPerSol) -> Option<UsdMicros> {
        let lamports = u128::from(self.virtual_sol.get())
            .checked_mul(SUPPLY_RAW)?
            .checked_div(u128::from(self.virtual_token.get()))?;
        let micros = lamports
            .checked_mul(u128::from(usd.get()))?
            .checked_div(LAMPORTS_PER_SOL)?;
        u64::try_from(micros).ok().map(UsdMicros)
    }
}

/// Concept: This value is a signed amount of SOL in lamports: positive into
/// the party it is stated for, negative out of it.
///
/// A wallet gains and loses SOL, so a flow has a sign. [`Lamports`] never goes
/// below zero, so a flow is its own type.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct SignedLamports(i64);

impl SignedLamports {
    /// Wrap a raw signed count of lamports.
    #[must_use]
    pub const fn new(raw: i64) -> Self {
        Self(raw)
    }

    /// The raw signed count.
    #[must_use]
    pub const fn get(self) -> i64 {
        self.0
    }

    /// This amount as a gain. `None` when it does not fit.
    #[must_use]
    pub fn inflow(amount: Lamports) -> Option<Self> {
        i64::try_from(amount.get()).ok().map(Self)
    }

    /// This amount as a loss. `None` when it does not fit.
    #[must_use]
    pub fn outflow(amount: Lamports) -> Option<Self> {
        i64::try_from(amount.get())
            .ok()
            .and_then(i64::checked_neg)
            .map(Self)
    }

    /// The sum. `None` when it does not fit.
    #[must_use]
    pub fn checked_add(self, rhs: Self) -> Option<Self> {
        self.0.checked_add(rhs.0).map(Self)
    }
}
