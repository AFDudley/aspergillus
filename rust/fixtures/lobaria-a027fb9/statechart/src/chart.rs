//! The chart, as types. GENERATED from `docs/chart.json5`; do not edit.
//!
//! Concept: This module is the machine's chart: one module per region, one
//! type per substate, one signature per transition.
//!
//! `docs/chart.json5` is the only declaration (`docs/process.md`, "Draw the
//! machine as a contract before any body"). The `chart` crate writes this
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

/// Concept: This module is the events of the chart: one type for each.
pub mod event {
    /// Concept: the occupant's own statement of its book, in its objective's unit.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Accounting;

    /// Concept: principal lobaria assigns to the slot's occupant: an amount in an asset, and its cap.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Allocation;

    /// Concept: receipt time, from the shell's clock, never from a payload.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Clock;

    /// Concept: a coding shred, parsed once at the edge.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct CodingShred;

    /// Concept: the chain's record of a slot: the signatures it holds, or that it was skipped.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct ConfirmedBlock;

    /// Concept: an event a transition of the chart emits.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct ConfirmedObservation(pub super::Hole<crate::programs::Observation>);

    /// Concept: a data shred, parsed once at the edge (statechart::parse::shred).
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct DataShred;

    /// Concept: an event a transition of the chart emits.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Decision;

    /// Concept: the operator's instruction to wind the occupant down.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Drain;

    /// Concept: an event a transition of the chart emits.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Fill;

    /// Concept: the SOL/USD leg of a quote path, timestamped (unified-trading-stack.md §0).
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct PriceTick;

    /// Concept: an event a transition of the chart emits.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct RecoveredBatch;

    /// Concept: an event a transition of the chart emits.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Refused;

    /// Concept: the machine's own turn: run one step to completion (Harel & Naamad 1996).
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Step;

    /// Concept: the live slot has moved past this instance's slot by the eviction distance.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct WatermarkPassed;
}

/// An erasure set collects shreds until the batch can be read.
pub mod recovering {
    use super::{event, Hole, Owed};

    /// Concept: shreds of the set have arrived; the set's shape (data count, coding count) is not yet known.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Collecting;

    /// Concept: a coding shred has told the set its shape; fewer than data-count shreds are held.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Shaped;

    /// Concept: at least data-count shreds of any kind are held; Reed–Solomon can fill the rest.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Recoverable;

    /// Concept: every data shred is held or reconstructed; the batch is emitted.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Recovered;

    /// Concept: the live slot passed the watermark first; the set is left to the archive.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Evicted;

    /// Concept: This value is what `collect` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum CollectOutcome {
        /// The transition moved to `Collecting`.
        Collecting(Collecting),
        /// The transition moved to `Recovered`.
        Recovered(Recovered),
        /// The guard refused with `DuplicateShred`.
        DuplicateShred,
        /// The guard refused with `ForeignSet`.
        ForeignSet,
        /// The guard refused with `ArenaFull`.
        ArenaFull,
    }

    /// The transition `collect`: it fires on `DataShred` from Collecting, and emits RecoveredBatch. Its body is derived: it returns `Recovered`.
    #[must_use]
    pub const fn collect(from: Collecting, on: event::DataShred) -> Hole<CollectOutcome> {
        let _ = (from, on);
        Hole::Derived(CollectOutcome::Recovered(Recovered))
    }

    /// Concept: This value is what `shape` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum ShapeOutcome {
        /// The transition moved to `Shaped`.
        Shaped(Shaped),
        /// The transition moved to `Recoverable`.
        Recoverable(Recoverable),
        /// The guard refused with `DuplicateShred`.
        DuplicateShred,
        /// The guard refused with `ForeignSet`.
        ForeignSet,
        /// The guard refused with `ArenaFull`.
        ArenaFull,
    }

    /// The transition `shape`: it fires on `CodingShred` from Collecting. Its body is owed.
    #[must_use]
    pub const fn shape(from: Collecting, on: event::CodingShred) -> Hole<ShapeOutcome> {
        let _ = (from, on);
        Hole::Owed(Owed)
    }

    /// Concept: This value is what `fill` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum FillOutcome {
        /// The transition moved to `Shaped`.
        Shaped(Shaped),
        /// The transition moved to `Recoverable`.
        Recoverable(Recoverable),
        /// The transition moved to `Recovered`.
        Recovered(Recovered),
        /// The guard refused with `DuplicateShred`.
        DuplicateShred,
        /// The guard refused with `ForeignSet`.
        ForeignSet,
    }

    /// The transition `fill`: it fires on `DataShred` from Shaped, and emits RecoveredBatch. Its body is owed.
    #[must_use]
    pub const fn fill(from: Shaped, on: event::DataShred) -> Hole<FillOutcome> {
        let _ = (from, on);
        Hole::Owed(Owed)
    }

    /// Concept: This value is what `fill_parity` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum FillParityOutcome {
        /// The transition moved to `Shaped`.
        Shaped(Shaped),
        /// The transition moved to `Recoverable`.
        Recoverable(Recoverable),
        /// The guard refused with `DuplicateShred`.
        DuplicateShred,
        /// The guard refused with `ForeignSet`.
        ForeignSet,
    }

    /// The transition `fill_parity`: it fires on `CodingShred` from Shaped. Its body is owed.
    #[must_use]
    pub const fn fill_parity(from: Shaped, on: event::CodingShred) -> Hole<FillParityOutcome> {
        let _ = (from, on);
        Hole::Owed(Owed)
    }

    /// Concept: This value is what `recover` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum RecoverOutcome {
        /// The transition moved to `Recovered`.
        Recovered(Recovered),
        /// The guard refused with `ParityFailed`.
        ParityFailed,
    }

    /// The transition `recover`: it fires on `Step` from Recoverable, and emits RecoveredBatch. Its body is derived: it returns `Recovered`.
    #[must_use]
    pub const fn recover(from: Recoverable, on: event::Step) -> Hole<RecoverOutcome> {
        let _ = (from, on);
        Hole::Derived(RecoverOutcome::Recovered(Recovered))
    }

    /// Concept: This value is what `evict` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum EvictOutcome {
        /// The transition moved to `Evicted`.
        Evicted(Evicted),
    }

    /// Concept: This value is the substate `evict` fires from.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum EvictFrom {
        /// The region is in `Collecting`.
        Collecting(Collecting),
        /// The region is in `Shaped`.
        Shaped(Shaped),
        /// The region is in `Recoverable`.
        Recoverable(Recoverable),
    }

    /// The transition `evict`: it fires on `WatermarkPassed` from Collecting, Shaped, Recoverable. Its body is owed.
    #[must_use]
    pub const fn evict(from: EvictFrom, on: event::WatermarkPassed) -> Hole<EvictOutcome> {
        let _ = (from, on);
        Hole::Owed(Owed)
    }
}

/// A decoded transaction is held until the chain says it is in the block, or is not.
pub mod confirming {
    use super::{event, Hole, Owed};

    /// Concept: parsed from a recovered batch (statechart::parse::transaction); the observation exists at evidence Decoded.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Decoded;

    /// Concept: the chain's record of the slot holds this signature; the observation is at evidence Confirmed.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Confirmed;

    /// Concept: the slot's record is final and does not hold this signature (skipped slot, or a shred the leader never had confirmed).
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Orphaned;

    /// Concept: This value is what `confirm` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum ConfirmOutcome {
        /// The transition moved to `Confirmed`.
        Confirmed(Confirmed),
        /// The transition moved to `Orphaned`.
        Orphaned(Orphaned),
    }

    /// The transition `confirm`: it fires on `ConfirmedBlock` from Decoded, and emits ConfirmedObservation. Its body is derived: it returns `Confirmed`.
    #[must_use]
    pub const fn confirm(from: Decoded, on: event::ConfirmedBlock) -> Hole<ConfirmOutcome> {
        let _ = (from, on);
        Hole::Derived(ConfirmOutcome::Confirmed(Confirmed))
    }

    /// Concept: This value is what `expire` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum ExpireOutcome {
        /// The transition moved to `Orphaned`.
        Orphaned(Orphaned),
    }

    /// The transition `expire`: it fires on `WatermarkPassed` from Decoded. Its body is owed.
    #[must_use]
    pub const fn expire(from: Decoded, on: event::WatermarkPassed) -> Hole<ExpireOutcome> {
        let _ = (from, on);
        Hole::Owed(Owed)
    }
}

/// The venue's state for one pair, moved only by confirmed observations.
pub mod reconstructing {
    use super::{event, Hole};

    /// Concept: the pair has a first confirmed observation but no reserves yet; the instance exists so the create is not lost.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Unseen;

    /// Concept: the pair trades on the bonding curve (programs::pump); Reserves are held and every confirmed trade moves them.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct OnCurve;

    /// Concept: the curve is complete; liquidity is moving to the pool and no trade is possible on either venue.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Migrating;

    /// Concept: the pair trades on the constant-product pool (programs::pump_amm); Reserves are the pool's.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct OnPool;

    /// Concept: This value is what `create` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum CreateOutcome {
        /// The transition moved to `OnCurve`.
        OnCurve(OnCurve),
        /// The guard refused with `NotACreate`.
        NotACreate,
    }

    /// The transition `create`: it fires on `ConfirmedObservation` from Unseen. Its body is derived: it returns `OnCurve`.
    #[must_use]
    pub const fn create(from: Unseen, on: event::ConfirmedObservation) -> Hole<CreateOutcome> {
        let _ = (from, on);
        Hole::Derived(CreateOutcome::OnCurve(OnCurve))
    }

    /// Concept: This value is what `trade` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum TradeOutcome {
        /// The transition moved to `OnCurve`.
        OnCurve(OnCurve),
        /// The transition moved to `Migrating`.
        Migrating(Migrating),
        /// The guard refused with `ReserveMismatch`.
        ReserveMismatch,
        /// The guard refused with `WrongVenue`.
        WrongVenue,
    }

    /// The transition `trade`: it fires on `ConfirmedObservation` from OnCurve. Its body is derived: it returns `OnCurve`.
    #[must_use]
    pub const fn trade(from: OnCurve, on: event::ConfirmedObservation) -> Hole<TradeOutcome> {
        let _ = (from, on);
        Hole::Derived(TradeOutcome::OnCurve(OnCurve))
    }

    /// Concept: This value is what `pool` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum PoolOutcome {
        /// The transition moved to `OnPool`.
        OnPool(OnPool),
        /// The guard refused with `NotAPoolCreate`.
        NotAPoolCreate,
    }

    /// Concept: This value is the substate `pool` fires from.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum PoolFrom {
        /// The region is in `Unseen`.
        Unseen(Unseen),
        /// The region is in `OnCurve`.
        OnCurve(OnCurve),
        /// The region is in `Migrating`.
        Migrating(Migrating),
    }

    /// The transition `pool`: it fires on `ConfirmedObservation` from Unseen, OnCurve, Migrating. Its body is derived: it returns `OnPool`.
    #[must_use]
    pub const fn pool(from: PoolFrom, on: event::ConfirmedObservation) -> Hole<PoolOutcome> {
        let _ = (from, on);
        Hole::Derived(PoolOutcome::OnPool(OnPool))
    }

    /// Concept: This value is what `swap` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum SwapOutcome {
        /// The transition moved to `OnPool`.
        OnPool(OnPool),
        /// The guard refused with `ReserveMismatch`.
        ReserveMismatch,
        /// The guard refused with `WrongVenue`.
        WrongVenue,
    }

    /// The transition `swap`: it fires on `ConfirmedObservation` from OnPool. Its body is derived: it returns `OnPool`.
    #[must_use]
    pub const fn swap(from: OnPool, on: event::ConfirmedObservation) -> Hole<SwapOutcome> {
        let _ = (from, on);
        Hole::Derived(SwapOutcome::OnPool(OnPool))
    }
}

/// One decision, from signed to accepted by the chain or rejected.
pub mod executing {
    use super::{event, Hole};

    /// Concept: a strategy's Decision has been received and is not yet a transaction.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Decided;

    /// Concept: the transaction is built from the reconstruction's accounts and signed; a blockhash is bound.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Signed;

    /// Concept: the signed transaction was handed to the wire; nothing is known about its fate.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Submitted;

    /// Concept: our signature was seen confirmed in a block; the fill is real.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Accepted;

    /// Concept: the blockhash's slot window closed without our signature, or the send itself failed.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Rejected;

    /// Concept: This value is what `sign` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum SignOutcome {
        /// The transition moved to `Signed`.
        Signed(Signed),
        /// The guard refused with `InsufficientBalance`.
        InsufficientBalance,
        /// The guard refused with `NoRoute`.
        NoRoute,
        /// The guard refused with `StaleReconstruction`.
        StaleReconstruction,
    }

    /// The transition `sign`: it fires on `Step` from Decided, and emits Refused. Its body is derived: it returns `Signed`.
    #[must_use]
    pub const fn sign(from: Decided, on: event::Step) -> Hole<SignOutcome> {
        let _ = (from, on);
        Hole::Derived(SignOutcome::Signed(Signed))
    }

    /// Concept: This value is what `submit` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum SubmitOutcome {
        /// The transition moved to `Submitted`.
        Submitted(Submitted),
        /// The transition moved to `Rejected`.
        Rejected(Rejected),
    }

    /// The transition `submit`: it fires on `Step` from Signed, and emits Fill. Its body is derived: it returns `Submitted`.
    #[must_use]
    pub const fn submit(from: Signed, on: event::Step) -> Hole<SubmitOutcome> {
        let _ = (from, on);
        Hole::Derived(SubmitOutcome::Submitted(Submitted))
    }

    /// Concept: This value is what `accept` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum AcceptOutcome {
        /// The transition moved to `Accepted`.
        Accepted(Accepted),
        /// The guard refused with `NotOurSignature`.
        NotOurSignature,
    }

    /// The transition `accept`: it fires on `ConfirmedObservation` from Submitted, and emits Fill. Its body is derived: it returns `Accepted`.
    #[must_use]
    pub const fn accept(from: Submitted, on: event::ConfirmedObservation) -> Hole<AcceptOutcome> {
        let _ = (from, on);
        Hole::Derived(AcceptOutcome::Accepted(Accepted))
    }

    /// Concept: This value is what `reject` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum RejectOutcome {
        /// The transition moved to `Rejected`.
        Rejected(Rejected),
    }

    /// The transition `reject`: it fires on `WatermarkPassed` from Submitted, and emits Fill. Its body is derived: it returns `Rejected`.
    #[must_use]
    pub const fn reject(from: Submitted, on: event::WatermarkPassed) -> Hole<RejectOutcome> {
        let _ = (from, on);
        Hole::Derived(RejectOutcome::Rejected(Rejected))
    }
}

/// The strategy slot: the one pluggable region.
pub mod deciding {
    use super::{event, Hole, Owed};

    /// Concept: an occupant is bound to the slot; no principal has been assigned.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Attached;

    /// Concept: the occupant holds principal and runs its own chart on the facts it receives (the hole; see `slot`).
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Active;

    /// Concept: the occupant may only reduce; it is winding down toward flat.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Draining;

    /// Concept: the occupant's book is flat and it is unbound.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Retired;

    /// Concept: This value is what `fund` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum FundOutcome {
        /// The transition moved to `Active`.
        Active(Active),
    }

    /// The transition `fund`: it fires on `Allocation` from Attached. Its body is derived: it returns `Active`.
    #[must_use]
    pub const fn fund(from: Attached, on: event::Allocation) -> Hole<FundOutcome> {
        let _ = (from, on);
        Hole::Derived(FundOutcome::Active(Active))
    }

    /// Concept: This value is what `observe` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum ObserveOutcome {
        /// The transition moved to `Active`.
        Active(Active),
        /// The transition moved to `Draining`.
        Draining(Draining),
    }

    /// Concept: This value is the substate `observe` fires from.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum ObserveFrom {
        /// The region is in `Active`.
        Active(Active),
        /// The region is in `Draining`.
        Draining(Draining),
    }

    /// The transition `observe`: it fires on `ConfirmedObservation` from Active, Draining, and emits Decision, Accounting. Its body is derived: it returns `Active`.
    #[must_use]
    pub const fn observe(
        from: ObserveFrom,
        on: event::ConfirmedObservation,
    ) -> Hole<ObserveOutcome> {
        let _ = (from, on);
        Hole::Derived(ObserveOutcome::Active(Active))
    }

    /// Concept: This value is what `tick` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum TickOutcome {
        /// The transition moved to `Active`.
        Active(Active),
        /// The transition moved to `Draining`.
        Draining(Draining),
    }

    /// Concept: This value is the substate `tick` fires from.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum TickFrom {
        /// The region is in `Active`.
        Active(Active),
        /// The region is in `Draining`.
        Draining(Draining),
    }

    /// The transition `tick`: it fires on `PriceTick` from Active, Draining, and emits Decision, Accounting. Its body is owed.
    #[must_use]
    pub const fn tick(from: TickFrom, on: event::PriceTick) -> Hole<TickOutcome> {
        let _ = (from, on);
        Hole::Owed(Owed)
    }

    /// Concept: This value is what `clock` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum ClockOutcome {
        /// The transition moved to `Active`.
        Active(Active),
        /// The transition moved to `Draining`.
        Draining(Draining),
    }

    /// Concept: This value is the substate `clock` fires from.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum ClockFrom {
        /// The region is in `Active`.
        Active(Active),
        /// The region is in `Draining`.
        Draining(Draining),
    }

    /// The transition `clock`: it fires on `Clock` from Active, Draining, and emits Decision, Accounting. Its body is owed.
    #[must_use]
    pub const fn clock(from: ClockFrom, on: event::Clock) -> Hole<ClockOutcome> {
        let _ = (from, on);
        Hole::Owed(Owed)
    }

    /// Concept: This value is what `settle` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum SettleOutcome {
        /// The transition moved to `Active`.
        Active(Active),
        /// The transition moved to `Draining`.
        Draining(Draining),
    }

    /// Concept: This value is the substate `settle` fires from.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum SettleFrom {
        /// The region is in `Active`.
        Active(Active),
        /// The region is in `Draining`.
        Draining(Draining),
    }

    /// The transition `settle`: it fires on `Fill` from Active, Draining, and emits Accounting. Its body is derived: it returns `Active`.
    #[must_use]
    pub const fn settle(from: SettleFrom, on: event::Fill) -> Hole<SettleOutcome> {
        let _ = (from, on);
        Hole::Derived(SettleOutcome::Active(Active))
    }

    /// Concept: This value is what `refuse` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum RefuseOutcome {
        /// The transition moved to `Active`.
        Active(Active),
        /// The transition moved to `Draining`.
        Draining(Draining),
    }

    /// Concept: This value is the substate `refuse` fires from.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum RefuseFrom {
        /// The region is in `Active`.
        Active(Active),
        /// The region is in `Draining`.
        Draining(Draining),
    }

    /// The transition `refuse`: it fires on `Refused` from Active, Draining, and emits Accounting. Its body is owed.
    #[must_use]
    pub const fn refuse(from: RefuseFrom, on: event::Refused) -> Hole<RefuseOutcome> {
        let _ = (from, on);
        Hole::Owed(Owed)
    }

    /// Concept: This value is what `drain` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum DrainOutcome {
        /// The transition moved to `Draining`.
        Draining(Draining),
    }

    /// The transition `drain`: it fires on `Drain` from Active. Its body is owed.
    #[must_use]
    pub const fn drain(from: Active, on: event::Drain) -> Hole<DrainOutcome> {
        let _ = (from, on);
        Hole::Owed(Owed)
    }

    /// Concept: This value is what `retire` returned: the substate it moved to, or the refusal that left the source unchanged.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum RetireOutcome {
        /// The transition moved to `Retired`.
        Retired(Retired),
        /// The guard refused with `BookNotFlat`.
        BookNotFlat,
    }

    /// The transition `retire`: it fires on `Step` from Draining. Its body is owed.
    #[must_use]
    pub const fn retire(from: Draining, on: event::Step) -> Hole<RetireOutcome> {
        let _ = (from, on);
        Hole::Owed(Owed)
    }
}

/// Concept: This module is the slot contract of `Deciding.Active`: what the occupant is given and what it gives back.
pub mod slot {
    use super::event;

    /// Concept: This value is one thing the machine gives the occupant.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum Down {
        /// The event `Allocation`.
        Allocation(event::Allocation),
        /// The event `ConfirmedObservation`.
        ConfirmedObservation(event::ConfirmedObservation),
        /// The event `PriceTick`.
        PriceTick(event::PriceTick),
        /// The event `Clock`.
        Clock(event::Clock),
        /// The event `Fill`.
        Fill(event::Fill),
        /// The event `Refused`.
        Refused(event::Refused),
    }

    /// Concept: This value is one thing the occupant gives the machine.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum Up {
        /// The event `Decision`.
        Decision(event::Decision),
        /// The event `Accounting`.
        Accounting(event::Accounting),
    }
}
