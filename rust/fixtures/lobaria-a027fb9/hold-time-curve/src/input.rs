//! The typed inputs this command reads: the executable-exit-value
//! trajectory log, the trade log, and the position-label file.
//!
//! Concept: the trajectory log (`TrajectoryRow`) and the trade log (`Trade`)
//! are lob-c2e's own shapes, read here unchanged: a dependency this tool
//! consumes, not one it defines. Neither carries a position's venue regime
//! or entry-momentum bucket, so the position-label file (`PositionLabel`) is
//! this tool's own additional input for those two splits, keyed the same way
//! the trajectory log's own rows are: the mint and the entry receipt.

use std::io::BufRead;
use std::path::Path;

use serde::{Deserialize, Serialize};

/// The pair's base token, 32 bytes as the wire holds it.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub struct Mint(pub [u8; 32]);

/// The receipt time of an event, nanoseconds since the Unix epoch.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub struct Receipt(pub i64);

/// A span of time in nanoseconds.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct Nanos(pub u64);

/// A signed amount of SOL in lamports.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct SignedLamports(pub i64);

/// One row of the executable-exit-value trajectory log: a position's mark at
/// one observation since entry. The row at a position's actual close carries
/// the round trip's real earnings instead of a hypothetical mark.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct TrajectoryRow {
    /// The pair's base token.
    pub mint: Mint,
    /// The receipt time of the observation this row marks.
    pub at: Receipt,
    /// The receipt time the position opened.
    pub entered_at: Receipt,
    /// The time since entry.
    pub holding_ns: Nanos,
    /// The executable exit value at `at`.
    pub exit_value_lamports: SignedLamports,
}

/// One closed round trip of the trade log.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Trade {
    /// The pair's base token.
    pub mint: Mint,
    /// The legs of the trip.
    pub legs: usize,
    /// The earnings of the trade: the wallet's net flow over its legs.
    pub earnings: SignedLamports,
    /// The receipt time of the fill that closed the trade.
    pub closed_at: Receipt,
}

/// The venue regime a position traded in.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Regime {
    /// Still trading on the Pump.fun bonding curve.
    OnCurve,
    /// Graduated to the PumpSwap AMM pool.
    Graduated,
}

/// A position's regime and entry-momentum bucket: the classification neither
/// the trajectory log nor the trade log carries.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct PositionLabel {
    /// The pair's base token.
    pub mint: Mint,
    /// The receipt time the position opened: together with `mint`, the same
    /// key the trajectory log's rows carry.
    pub entered_at: Receipt,
    /// The venue regime the position closed in.
    pub regime: Regime,
    /// The entry-momentum bucket an analyst assigned this position.
    pub momentum_bucket: String,
}

/// The lines of `path`, each parsed as one `T`. A blank line is skipped.
///
/// # Errors
/// The file cannot be read, or a line does not parse as `T`.
pub fn read_jsonl<T: serde::de::DeserializeOwned>(path: &Path) -> Result<Vec<T>, String> {
    let file = std::fs::File::open(path).map_err(|e| format!("{}: {e}", path.display()))?;
    std::io::BufReader::new(file)
        .lines()
        .filter(|line| !matches!(line, Ok(text) if text.trim().is_empty()))
        .map(|line| {
            let text = line.map_err(|e| format!("{}: {e}", path.display()))?;
            serde_json::from_str(&text).map_err(|e| format!("{}: {e}: {text}", path.display()))
        })
        .collect()
}
