//! The edge: the single contract both packet sources produce.
//!
//! Concept: This module is the one input type of the machine.
//!
//! A packet from the wire and a packet from a capture file are the same
//! [`Packet`]; everything past this module cannot tell them apart. That is
//! where "backtest equals live" lives (`docs/process.md`, "The machine").

use serde::{Deserialize, Serialize};

use crate::units::{newtype, Nanos};
use crate::Refusal;

newtype! {
    /// Concept: This value is how many bytes a datagram carries.
    PacketLen(u16)
}

/// Concept: This value is the instant a packet arrived at this machine.
///
/// The sole ordering key for everything downstream. A chain-side time (a
/// slot's wall-clock estimate) is never a Receipt.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
pub struct Receipt(Nanos);

impl Receipt {
    /// A receipt at the given instant.
    #[must_use]
    pub const fn at(instant: Nanos) -> Self {
        Self(instant)
    }

    /// The instant.
    #[must_use]
    pub const fn instant(self) -> Nanos {
        self.0
    }
}

/// The most bytes one Solana shred datagram carries.
///
/// [agave `ledger/src/shred.rs`: the legacy and Merkle payload sizes are at
/// most 1228 bytes; 1232 is the transport bound.]
pub const MAX_PACKET_BYTES: usize = 1232;

/// Concept: This value is the bytes of one datagram, in a bounded buffer.
///
/// The one owned buffer in the core. It is copied exactly once, from the
/// socket or file buffer the datagram arrived in, and never again: every
/// later type is a view into it or into a batch recovered from it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PacketBytes {
    len: PacketLen,
    buf: [u8; MAX_PACKET_BYTES],
}

impl PacketBytes {
    /// The datagram's bytes, refused if longer than the wire allows.
    pub fn new(bytes: &[u8]) -> Result<Self, Refusal> {
        if bytes.len() > MAX_PACKET_BYTES {
            return Err(Refusal::PacketTooLong);
        }
        let mut buf = [0u8; MAX_PACKET_BYTES];
        let Some(head) = buf.get_mut(..bytes.len()) else {
            return Err(Refusal::PacketTooLong);
        };
        head.copy_from_slice(bytes);
        let Ok(len) = u16::try_from(bytes.len()) else {
            return Err(Refusal::PacketTooLong);
        };
        Ok(Self {
            len: PacketLen::new(len),
            buf,
        })
    }

    /// The datagram's bytes.
    #[must_use]
    pub fn as_slice(&self) -> &[u8] {
        self.buf.get(..usize::from(self.len.get())).unwrap_or(&[])
    }

    /// How many bytes the datagram has.
    #[must_use]
    pub const fn len(&self) -> PacketLen {
        self.len
    }

    /// Whether the datagram is empty.
    #[must_use]
    pub const fn is_empty(&self) -> bool {
        self.len.get() == 0
    }
}

/// Concept: This value is one datagram as this machine received it: when,
/// and what.
///
/// The single input contract; both sources produce it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Packet {
    receipt: Receipt,
    bytes: PacketBytes,
}

impl Packet {
    /// A packet received at `receipt` carrying `bytes`.
    #[must_use]
    pub const fn new(receipt: Receipt, bytes: PacketBytes) -> Self {
        Self { receipt, bytes }
    }

    /// When the packet arrived.
    #[must_use]
    pub const fn receipt(&self) -> Receipt {
        self.receipt
    }

    /// The datagram.
    #[must_use]
    pub const fn bytes(&self) -> &PacketBytes {
        &self.bytes
    }
}
