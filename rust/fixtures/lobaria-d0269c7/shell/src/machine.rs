//! The machine: the five regions' state, their inboxes, and the pure
//! calculation of one transition.
//!
//! Concept: This module is the machine's state as a value and the pure step
//! over it.
//!
//! `docs/thesis.md`, "What the machine actually is": the regions communicate
//! by events, and a region takes an event when it reaches a state that fires
//! on it. Each region has an inbox. An event is addressed to every region
//! whose transitions fire on it, and it stays in that inbox until a
//! transition consumes it. The step is [`next`] then [`apply`]: `next` finds
//! the first enabled transition, the driver reads what it needs from the
//! ports, and `apply` calculates the new state. Nothing here does I/O.
//!
//! Only the transitions whose bodies are derived (`chart/src/bodies.rs`) are
//! enabled. An event that no derived transition consumes stays in its inbox,
//! and the driver reports the count. A guard that would need a branch the body
//! does not derive (an `Orphaned` confirmation) leaves its transition not
//! enabled.
//!
//! The chart's events carry no payload, so a derived body returns its path's
//! target and the shell evaluates each guard. `Executing` shows that split.
//! `sign` moves to `Signed` only when the signer made a transaction, and a
//! signer's refusal is the outcome the chart names. `submit` moves to
//! `Submitted` only when the wire took the transaction, and to `Rejected` when
//! the send failed. `accept` fires only on a `ConfirmedObservation` of the
//! signature the machine signed, and only on one delivered after the
//! submission: an observation that came before it cannot be of the submission,
//! so `submit` drops it. `reject` fires when the finalized slot passes the
//! last slot of the blockhash without that observation. Nothing the wire
//! answers moves the region to `Accepted`.
//!
//! `Recovering` holds several live instances at once, one per (slot,
//! fec_set_index) pair, inside a bounded arena (`docs/chart.json5` line 61):
//! a shred advances only the instance its own pair keys, and a pair the
//! arena has no room for is refused with `ArenaFull`. `Confirming` holds
//! several live instances at once, one per signature, inside a bounded arena
//! (`docs/chart.json5` line 129): a recovered transaction starts its own
//! instance, and a signature the arena has no room for is not admitted, so a
//! second signature in flight does not wait on the first's decision.
//! `Executing` holds one instance per `Decision`: each `Decision` event
//! starts its own instance, and every instance runs its own path to
//! `Accepted` or `Rejected` without waiting on any other instance.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use statechart::chart::{
    confirming as cf, deciding as dc, event, executing as ex, reconstructing as rc,
    recovering as rv, Hole, Owed,
};
use statechart::curve::{self, Settled, Venue};
use statechart::edge::Receipt;
use statechart::fire::{self, Firing, Region};
use statechart::programs::{Pool, PoolState, PriceTick, SwapCall};
use statechart::units::{Bps, Pubkey, Signature, Slot};
use statechart::wire::FecSetIndex;
use statechart::{dlmm, pool, Refusal};

use crate::edge::{Batch, Completion};
use crate::market::Transacted;
use crate::observation;
use crate::port::{
    Decision, Grant, Held, Market, Observed, PoolHeld, Record, SendFailed, SignRefusal,
    SignedTransaction, Standing,
};

/// The total fee pump.fun takes on the SOL of a trade, in basis points: the
/// protocol fee of 95 and the creator fee of 30.
///
/// It fixes the token result of a `BuyExactSolIn` and the price bound of every
/// trade (`statechart::curve::advance`). A confirmed trade that reports its own
/// reserves is checked against the result, so a wrong fee shows as a
/// `ReserveMismatch` and not as a silent drift. The program's fee account holds
/// the live value; reading it is a shell adapter that does not exist yet.
pub const PUMP_FEE: Bps = Bps::new(125);

/// Concept: This value is where the Recovering region is.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RecoveringAt {
    /// Shreds of the set have arrived.
    Collecting(rv::Collecting),
    /// A coding shred has told the set its shape.
    Shaped(rv::Shaped),
    /// Enough shreds are held to recover the rest.
    Recoverable(rv::Recoverable),
    /// The batch is emitted.
    Recovered(rv::Recovered),
    /// The set was evicted.
    Evicted(rv::Evicted),
}

/// How many live Recovering instances the arena holds at once
/// (`docs/chart.json5` line 61: "per (slot, fec_set_index), bounded arena").
const RECOVERING_ARENA_CAPACITY: usize = 8;

/// Concept: This value identifies one erasure set's Recovering instance: its
/// slot and its erasure-set index within that slot.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
struct RecoveringKey {
    slot: Slot,
    fec_set_index: FecSetIndex,
}

impl RecoveringKey {
    /// The key of the erasure set a batch's shred belongs to.
    const fn of(batch: &Batch) -> Self {
        Self {
            slot: batch.slot,
            fec_set_index: batch.fec_set_index,
        }
    }
}

/// Concept: This value is the Recovering region's state: one live instance
/// per (slot, fec_set_index) pair, held inside a bounded arena. A pair the
/// arena has no room for is refused, not admitted past the capacity.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
struct RecoveringArena {
    live: BTreeMap<RecoveringKey, RecoveringAt>,
}

impl RecoveringArena {
    /// The live instance of the key's erasure set, if the arena holds one.
    fn get(&self, key: RecoveringKey) -> Option<RecoveringAt> {
        self.live.get(&key).copied()
    }

    /// Move the key's live instance to `at`, admitting it into the arena if
    /// it was not already held.
    fn set(&mut self, key: RecoveringKey, at: RecoveringAt) {
        self.live.insert(key, at);
    }

    /// Whether the arena holds as many live instances as its capacity
    /// allows.
    fn is_full(&self) -> bool {
        self.live.len() >= RECOVERING_ARENA_CAPACITY
    }
}

/// Concept: This value is where one Confirming instance is.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ConfirmingAt {
    /// The transaction is decoded.
    Decoded(cf::Decoded),
    /// The chain's record holds the signature.
    Confirmed(cf::Confirmed),
    /// The chain's record does not hold the signature.
    Orphaned(cf::Orphaned),
}

/// How many live Confirming instances the arena holds at once
/// (`docs/chart.json5` line 129: "per signature, bounded arena").
const CONFIRMING_ARENA_CAPACITY: usize = 8;

/// Concept: This value is one signature's live instance in the Confirming
/// region: where it is, and the decoded transaction it carries.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct ConfirmingInstance {
    at: ConfirmingAt,
    transacted: Transacted,
}

/// Concept: This value is the Confirming region's state: one live instance
/// per signature, held inside a bounded arena. A signature the arena has no
/// room for is not admitted past the capacity.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
struct ConfirmingArena {
    live: BTreeMap<Signature, ConfirmingInstance>,
}

impl ConfirmingArena {
    /// Where the signature's live instance is, if the arena holds one.
    fn get(&self, signature: Signature) -> Option<ConfirmingAt> {
        self.live.get(&signature).map(|instance| instance.at)
    }

    /// Whether the arena holds as many live instances as its capacity
    /// allows.
    fn is_full(&self) -> bool {
        self.live.len() >= CONFIRMING_ARENA_CAPACITY
    }

    /// Admit the transaction's signature into the arena at `Decoded`, if the
    /// arena does not already hold it and has room for it. A signature
    /// already held, or a full arena, admits nothing.
    fn admit(&mut self, transacted: Transacted) {
        if self.get(transacted.signature).is_some() || self.is_full() {
            return;
        }
        self.live.insert(
            transacted.signature,
            ConfirmingInstance {
                at: ConfirmingAt::Decoded(cf::Decoded),
                transacted,
            },
        );
    }

    /// Move the signature's live instance to `at`, leaving its decoded
    /// transaction as it is. A signature the arena does not hold is left
    /// untouched.
    fn set(&mut self, signature: Signature, at: ConfirmingAt) {
        if let Some(instance) = self.live.get_mut(&signature) {
            instance.at = at;
        }
    }

    /// Every live instance at `Decoded`, with the transaction it carries.
    fn decoded(&self) -> impl Iterator<Item = (Signature, Transacted)> + '_ {
        self.live.iter().filter_map(|(signature, instance)| {
            matches!(instance.at, ConfirmingAt::Decoded(_))
                .then_some((*signature, instance.transacted))
        })
    }
}

/// Concept: This value is where the Reconstructing region is.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReconstructingAt {
    /// The pair has no reserves yet.
    Unseen(rc::Unseen),
    /// The pair trades on the curve.
    OnCurve(rc::OnCurve),
    /// The pair is moving to the pool.
    Migrating(rc::Migrating),
    /// The pair trades on the pool.
    OnPool(rc::OnPool),
}

/// Concept: This value is where one Executing instance is.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ExecutingAt {
    /// A decision is received.
    Decided(ex::Decided),
    /// The transaction is signed.
    Signed(ex::Signed),
    /// The transaction is on the wire.
    Submitted(ex::Submitted),
    /// Our signature was seen confirmed.
    Accepted(ex::Accepted),
    /// The decision is closed without a fill.
    Rejected(ex::Rejected),
}

/// Concept: This value names one Executing instance among the several the
/// region holds at once, so a transition can say which instance it moves.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ExecutingId(u32);

/// Concept: This value is one Decision's own instance in the Executing
/// region: where it is, the decision it carries, and the transaction it
/// signed, once it has one.
#[derive(Clone, Debug, PartialEq, Eq)]
struct ExecutingInstance {
    /// The instance's identity.
    id: ExecutingId,
    /// Where the instance is.
    at: ExecutingAt,
    /// The decision it carries.
    decision: Decision,
    /// The transaction the signer made for it, once `sign` fires.
    signed: Option<SignedTransaction>,
}

/// Concept: This value is where the Deciding region is.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DecidingAt {
    /// An occupant is bound, and holds no principal.
    Attached(dc::Attached),
    /// The occupant holds principal.
    Active(dc::Active),
    /// The occupant is winding down.
    Draining(dc::Draining),
    /// The occupant is unbound.
    Retired(dc::Retired),
}

/// Concept: This value is how a decision ended, for the occupant that placed it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Filled {
    /// Our signature was seen confirmed: the fill is real.
    Accepted(Signature),
    /// The decision closed without our signature confirmed.
    Rejected(Signature),
}

/// Concept: This value is one event of the machine, with what it carries.
///
/// `ConfirmedObservation(Observed)` can carry a Meteora DLMM
/// `statechart::dlmm::Ladder` (via `Market::Graduated`), a small `Copy`
/// value sized to model a swap crossing several bins in one fill
/// (`statechart::dlmm`'s own doc). That makes it the largest variant here by
/// a wide margin; boxing it would ripple `Box::new`/`*` through every match
/// arm below for a size trade this crate — which does allocate — can also
/// make by carrying the enum itself less densely; the allow is the
/// documented choice instead of that churn.
#[allow(clippy::large_enum_variant)]
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Event {
    /// A data shred, parsed, from the shell.
    DataShred(Batch),
    /// The batch a set recovered.
    RecoveredBatch(Batch),
    /// The chain's record of a slot, from the shell.
    ConfirmedBlock(Record),
    /// A transaction the chain confirmed.
    ConfirmedObservation(Observed),
    /// A decision of the occupant.
    Decision(Decision),
    /// How a submission ended.
    Fill(Filled),
    /// The machine's own turn, from the shell.
    Step,
    /// The newest slot the chain has finalized, from the shell.
    WatermarkPassed(Slot),
    /// The SOL/USD price, from the shell.
    PriceTick(PriceTick),
    /// Receipt time, from the shell.
    Clock(Receipt),
    /// Principal for the occupant, from the shell.
    Allocation(Grant),
}

/// Concept: This value is an event in one region's inbox.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Addressed {
    /// The region whose inbox holds the event.
    pub region: Region,
    /// The event.
    pub event: Event,
}

/// Concept: This value is the machine: one instance of each region, and the
/// events waiting for them.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Running {
    recovering: RecoveringArena,
    confirming: ConfirmingArena,
    reconstructing: ReconstructingAt,
    executing: Vec<ExecutingInstance>,
    next_executing_id: u32,
    deciding: DecidingAt,
    pair: Option<Pubkey>,
    held: Option<Held>,
    pooled: Option<PoolHeld>,
    fee: Bps,
    pending: Vec<Addressed>,
}

/// Concept: This value is where the Reconstructing region is, as a value that
/// carries from one run to the next.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Reconstructing {
    /// The pair has no reserves yet.
    Unseen,
    /// The pair trades on the curve.
    OnCurve,
    /// The pair is moving to the pool.
    Migrating,
    /// The pair trades on the pool.
    OnPool,
}

/// Concept: This value is the state a replay leaves in the machine of a pair:
/// where the Reconstructing region is and what it holds.
///
/// A replay delivers only confirmed observations and ends each turn with every
/// inbox empty, so this is all of the machine that differs from its boot state.
/// [`Running::carry`] refuses a machine of which it is not true.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Carried {
    at: Reconstructing,
    pair: Option<Pubkey>,
    held: Option<Held>,
    pooled: Option<PoolHeld>,
    fee: Bps,
}

/// Concept: This value is why a machine is not the one a replay leaves.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct NotCarried;

impl std::fmt::Display for NotCarried {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "the machine holds state a replay does not leave")
    }
}

impl std::error::Error for NotCarried {}

/// The order the step scans the regions in.
const ORDER: [Region; 5] = [
    Region::Recovering,
    Region::Confirming,
    Region::Reconstructing,
    Region::Deciding,
    Region::Executing,
];

/// The regions whose transitions fire on the event.
const fn consumers(event: &Event) -> &'static [Region] {
    match event {
        Event::DataShred(_) => &[Region::Recovering],
        Event::RecoveredBatch(_) | Event::ConfirmedBlock(_) => &[Region::Confirming],
        Event::ConfirmedObservation(_) => {
            &[Region::Reconstructing, Region::Deciding, Region::Executing]
        }
        Event::Decision(_) => &[Region::Executing],
        Event::Fill(_) | Event::PriceTick(_) | Event::Clock(_) | Event::Allocation(_) => {
            &[Region::Deciding]
        }
        Event::Step => &[Region::Recovering, Region::Executing, Region::Deciding],
        Event::WatermarkPassed(_) => &[Region::Recovering, Region::Confirming, Region::Executing],
    }
}

/// One enabled transition, with the typed source it fires from.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Kind {
    /// A Confirming instance comes into being for each of the batch's
    /// signatures the arena admits.
    InstantiateConfirming(Batch),
    /// A new Executing instance comes into being for the decision.
    InstantiateExecuting(Decision),
    /// `Recovering.collect`.
    Collect(rv::Collecting, Batch),
    /// `Confirming.confirm`, with the observation of each held signature.
    Confirm(cf::Decoded, Vec<Observed>),
    /// `Reconstructing.create`, on the observation that made the instance.
    Create(rc::Unseen, Observed),
    /// `Reconstructing.trade`.
    Trade(rc::OnCurve, Observed),
    /// `Reconstructing.pool`.
    Pool(rc::PoolFrom, Observed),
    /// `Reconstructing.swap`.
    Swap(rc::OnPool, Observed),
    /// `Deciding.fund`.
    Fund(dc::Attached),
    /// `Deciding.observe`.
    Observe(dc::ObserveFrom, Observed),
    /// `Executing.sign`, naming the instance it moves.
    Sign(ExecutingId, ex::Decided, Decision),
    /// `Executing.submit`, naming the instance it moves.
    Submit(ExecutingId, ex::Signed, SignedTransaction),
    /// `Executing.accept`, naming the instance it moves and carrying the
    /// observation of its own transaction.
    Accept(ExecutingId, ex::Submitted, Observed),
    /// `Executing.reject`, naming the instance it moves.
    Reject(ExecutingId, ex::Submitted),
    /// `Deciding.settle`.
    Settle(dc::SettleFrom),
}

/// Concept: This value is a transition the step found enabled, and the inbox
/// position of the event it consumes.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Enabled {
    /// The position of the event in the pending list.
    pub at: usize,
    /// The transition.
    pub kind: Kind,
}

/// Concept: This value is what the driver read for a transition.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Facts {
    /// The transition reads nothing.
    Nothing,
    /// What the occupant decided on an observation.
    Decision(Option<Decision>),
    /// The transaction the signer made, or its refusal.
    Signing(Result<SignedTransaction, SignRefusal>),
    /// What the wire answered to the send.
    Sending(Result<(), SendFailed>),
}

impl Running {
    /// The machine at boot: every region in its initial substate.
    #[must_use]
    pub fn boot() -> Self {
        Self {
            recovering: RecoveringArena::default(),
            confirming: ConfirmingArena::default(),
            reconstructing: ReconstructingAt::Unseen(rc::Unseen),
            executing: Vec::new(),
            next_executing_id: 0,
            deciding: DecidingAt::Attached(dc::Attached),
            pair: None,
            held: None,
            pooled: None,
            fee: PUMP_FEE,
            pending: Vec::new(),
        }
    }

    /// The state a replay left in the machine, as a value.
    ///
    /// # Errors
    /// [`NotCarried`] when the machine differs from the boot state anywhere but
    /// the Reconstructing region and what it holds.
    pub fn carry(&self) -> Result<Carried, NotCarried> {
        let at = match self.reconstructing {
            ReconstructingAt::Unseen(_) => Reconstructing::Unseen,
            ReconstructingAt::OnCurve(_) => Reconstructing::OnCurve,
            ReconstructingAt::Migrating(_) => Reconstructing::Migrating,
            ReconstructingAt::OnPool(_) => Reconstructing::OnPool,
        };
        let carried = Carried {
            at,
            pair: self.pair,
            held: self.held,
            pooled: self.pooled,
            fee: self.fee,
        };
        (Self::resume(carried) == *self)
            .then_some(carried)
            .ok_or(NotCarried)
    }

    /// The machine a replay left, from the state it carried.
    #[must_use]
    pub fn resume(carried: Carried) -> Self {
        let reconstructing = match carried.at {
            Reconstructing::Unseen => ReconstructingAt::Unseen(rc::Unseen),
            Reconstructing::OnCurve => ReconstructingAt::OnCurve(rc::OnCurve),
            Reconstructing::Migrating => ReconstructingAt::Migrating(rc::Migrating),
            Reconstructing::OnPool => ReconstructingAt::OnPool(rc::OnPool),
        };
        Self {
            reconstructing,
            pair: carried.pair,
            held: carried.held,
            pooled: carried.pooled,
            fee: carried.fee,
            ..Self::boot()
        }
    }

    /// Address the event to every region whose transitions fire on it.
    #[must_use]
    pub fn deliver(mut self, event: Event) -> Self {
        for region in consumers(&event) {
            if !self.addresses(*region, &event) {
                continue;
            }
            self.pending.push(Addressed {
                region: *region,
                event: event.clone(),
            });
        }
        self
    }

    /// Whether the region's inbox takes the event. The Reconstructing instance
    /// holds one pair, so an observation of another pair is not its input.
    fn addresses(&self, region: Region, event: &Event) -> bool {
        match (region, event, self.pair) {
            (Region::Reconstructing, Event::ConfirmedObservation(observed), Some(pair)) => {
                observed.market.mint() == Some(pair)
            }
            _ => true,
        }
    }

    /// End the turn of a replay that runs no region but Reconstructing: what
    /// still waits is addressed to a region the replay does not run, or no
    /// transition takes it, so every inbox is emptied. The inboxes of a replay
    /// do not grow with the length of its stream.
    #[must_use]
    pub fn end_replay_turn(mut self) -> Self {
        self.pending.clear();
        self
    }

    /// End the turn: a `Step` or a watermark that no transition took is gone.
    #[must_use]
    pub fn end_turn(mut self) -> Self {
        self.pending
            .retain(|a| !matches!(a.event, Event::Step | Event::WatermarkPassed(_)));
        self
    }

    /// Where every live Executing instance is, oldest first.
    #[must_use]
    pub fn executing(&self) -> Vec<ExecutingAt> {
        self.executing.iter().map(|instance| instance.at).collect()
    }

    /// The pair's reserves as the Reconstructing region holds them: only on the
    /// curve, and only once a reserve is known.
    #[must_use]
    pub const fn curve(&self) -> Option<Held> {
        match self.reconstructing {
            ReconstructingAt::OnCurve(_) => self.held,
            ReconstructingAt::Unseen(_)
            | ReconstructingAt::Migrating(_)
            | ReconstructingAt::OnPool(_) => None,
        }
    }

    /// The reserves the region holds, whatever venue state it is in.
    #[must_use]
    pub const fn reserves(&self) -> Option<Held> {
        self.held
    }

    /// The pool the region holds, and its running reserves: only on the pool,
    /// and only once a graduation seeded them.
    #[must_use]
    pub const fn pool_reserves(&self) -> Option<PoolHeld> {
        self.pooled
    }

    /// What the executor reads of the reconstruction when it signs.
    #[must_use]
    pub const fn standing(&self, finalized: Slot) -> Standing {
        Standing {
            held: self.curve(),
            finalized,
        }
    }

    /// How many events wait in the inboxes.
    #[must_use]
    pub fn waiting(&self) -> usize {
        self.pending.len()
    }

    /// The first transition an inbox event enables, scanning the regions in
    /// order and each inbox oldest first.
    #[must_use]
    pub fn next(&self) -> Option<Enabled> {
        ORDER.iter().find_map(|region| {
            self.pending
                .iter()
                .enumerate()
                .filter(|(_, a)| a.region == *region)
                .find_map(|(at, a)| {
                    self.enabled(*region, &a.event)
                        .map(|kind| Enabled { at, kind })
                })
        })
    }

    fn enabled(&self, region: Region, event: &Event) -> Option<Kind> {
        match region {
            Region::Recovering => self.recovering_takes(event),
            Region::Confirming => self.confirming_takes(event),
            Region::Reconstructing => self.reconstructing_takes(event),
            Region::Deciding => self.deciding_takes(event),
            Region::Executing => self.executing_takes(event),
        }
    }

    /// A shred's own (slot, fec_set_index) key selects the live instance it
    /// advances: a key the arena does not hold, or holds at a terminal
    /// state, starts fresh at `Collecting`; every other key's instance is
    /// left untouched.
    fn recovering_takes(&self, event: &Event) -> Option<Kind> {
        match event {
            Event::DataShred(batch) if batch.completion == Completion::Complete => {
                match self.recovering.get(RecoveringKey::of(batch)) {
                    None
                    | Some(RecoveringAt::Collecting(_))
                    | Some(RecoveringAt::Recovered(_))
                    | Some(RecoveringAt::Evicted(_)) => {
                        Some(Kind::Collect(rv::Collecting, batch.clone()))
                    }
                    Some(RecoveringAt::Shaped(_) | RecoveringAt::Recoverable(_)) => None,
                }
            }
            _ => None,
        }
    }

    /// A `RecoveredBatch` starts its own instance for each signature it
    /// carries; every live instance that a confirmed block's signatures name
    /// advances together, in the same step.
    fn confirming_takes(&self, event: &Event) -> Option<Kind> {
        match event {
            Event::RecoveredBatch(batch) => {
                (!batch.transactions.is_empty()).then(|| Kind::InstantiateConfirming(batch.clone()))
            }
            Event::ConfirmedBlock(Record::Held { slot, signatures }) => {
                let held: Vec<Observed> = self
                    .confirming
                    .decoded()
                    .filter(|(signature, _)| signatures.contains(signature))
                    .map(|(signature, transacted)| Observed {
                        slot: *slot,
                        receipt: transacted.receipt,
                        signature,
                        market: transacted.market,
                    })
                    .collect();
                (!held.is_empty()).then_some(Kind::Confirm(cf::Decoded, held))
            }
            _ => None,
        }
    }

    fn reconstructing_takes(&self, event: &Event) -> Option<Kind> {
        match (self.reconstructing, event) {
            (ReconstructingAt::Unseen(from), Event::ConfirmedObservation(observed))
                if is_a_graduation(observed) =>
            {
                Some(Kind::Pool(rc::PoolFrom::Unseen(from), *observed))
            }
            (ReconstructingAt::Unseen(from), Event::ConfirmedObservation(observed)) => {
                Some(Kind::Create(from, *observed))
            }
            (ReconstructingAt::OnCurve(from), Event::ConfirmedObservation(observed))
                if is_a_graduation(observed) =>
            {
                Some(Kind::Pool(rc::PoolFrom::OnCurve(from), *observed))
            }
            (ReconstructingAt::OnCurve(from), Event::ConfirmedObservation(observed))
                if is_venue_fact(observed) =>
            {
                Some(Kind::Trade(from, *observed))
            }
            (ReconstructingAt::Migrating(from), Event::ConfirmedObservation(observed)) => {
                Some(Kind::Pool(rc::PoolFrom::Migrating(from), *observed))
            }
            (ReconstructingAt::OnPool(from), Event::ConfirmedObservation(observed))
                if is_venue_fact(observed) =>
            {
                Some(Kind::Swap(from, *observed))
            }
            _ => None,
        }
    }

    fn deciding_takes(&self, event: &Event) -> Option<Kind> {
        match (self.deciding, event) {
            (DecidingAt::Attached(from), Event::Allocation(_)) => Some(Kind::Fund(from)),
            (DecidingAt::Active(from), Event::ConfirmedObservation(observed)) => {
                Some(Kind::Observe(dc::ObserveFrom::Active(from), *observed))
            }
            (DecidingAt::Active(from), Event::Fill(_)) => {
                Some(Kind::Settle(dc::SettleFrom::Active(from)))
            }
            _ => None,
        }
    }

    /// A `Decision` always starts a new instance; every other event is taken
    /// by scanning the live instances, oldest first, for the first whose
    /// substate fires on it.
    fn executing_takes(&self, event: &Event) -> Option<Kind> {
        if let Event::Decision(decision) = event {
            return Some(Kind::InstantiateExecuting(*decision));
        }
        self.executing
            .iter()
            .find_map(|instance| match (instance.at, event) {
                (ExecutingAt::Decided(from), Event::Step) => {
                    Some(Kind::Sign(instance.id, from, instance.decision))
                }
                (ExecutingAt::Signed(from), Event::Step) => instance
                    .signed
                    .clone()
                    .map(|signed| Kind::Submit(instance.id, from, signed)),
                (ExecutingAt::Submitted(from), Event::ConfirmedObservation(observed))
                    if instance
                        .signed
                        .as_ref()
                        .is_some_and(|s| s.signature == observed.signature) =>
                {
                    Some(Kind::Accept(instance.id, from, *observed))
                }
                (ExecutingAt::Submitted(from), Event::WatermarkPassed(finalized))
                    if instance
                        .signed
                        .as_ref()
                        .is_some_and(|s| s.valid_until < *finalized) =>
                {
                    Some(Kind::Reject(instance.id, from))
                }
                _ => None,
            })
    }

    /// A new instance, at `Decoded`, for each of the batch's signatures the
    /// arena admits.
    fn instantiate_confirming(mut self, batch: Batch) -> Self {
        for transacted in batch.transactions {
            self.confirming.admit(transacted);
        }
        self
    }

    /// A new instance, in `Decided`, for the decision.
    fn instantiate_executing(mut self, decision: Decision) -> Self {
        let id = ExecutingId(self.next_executing_id);
        self.next_executing_id = self.next_executing_id.wrapping_add(1);
        self.executing.push(ExecutingInstance {
            id,
            at: ExecutingAt::Decided(ex::Decided),
            decision,
            signed: None,
        });
        self
    }

    /// The signature of the instance's signed transaction, when it has one.
    fn executing_signature(&self, id: ExecutingId) -> Option<Signature> {
        self.executing
            .iter()
            .find(|instance| instance.id == id)
            .and_then(|instance| instance.signed.as_ref())
            .map(|signed| signed.signature)
    }

    /// Move the instance to a new substate, leaving its signed transaction as
    /// it is.
    fn set_executing_state(mut self, id: ExecutingId, at: ExecutingAt) -> Self {
        if let Some(instance) = self.executing.iter_mut().find(|instance| instance.id == id) {
            instance.at = at;
        }
        self
    }

    /// Move the instance to a new substate and bind the transaction the
    /// signer made for it.
    fn sign_executing(
        mut self,
        id: ExecutingId,
        at: ExecutingAt,
        signed: SignedTransaction,
    ) -> Self {
        if let Some(instance) = self.executing.iter_mut().find(|instance| instance.id == id) {
            instance.at = at;
            instance.signed = Some(signed);
        }
        self
    }

    /// Drop a confirmed observation addressed to Executing that matches no
    /// signature any live `Submitted` instance holds: it cannot be the
    /// confirmation of any decision this region is still waiting on.
    fn forget_unmatched_observations(mut self) -> Self {
        let signatures: Vec<Signature> = self
            .executing
            .iter()
            .filter_map(|instance| match instance.at {
                ExecutingAt::Submitted(_) => instance.signed.as_ref().map(|s| s.signature),
                ExecutingAt::Decided(_)
                | ExecutingAt::Signed(_)
                | ExecutingAt::Accepted(_)
                | ExecutingAt::Rejected(_) => None,
            })
            .collect();
        self.pending.retain(|a| {
            !(a.region == Region::Executing
                && matches!(&a.event, Event::ConfirmedObservation(observed) if !signatures.contains(&observed.signature)))
        });
        self
    }

    fn consume(mut self, at: usize) -> Self {
        if at < self.pending.len() {
            self.pending.remove(at);
        }
        self
    }
}

/// Calculate one transition: the new machine, and what the chart's body
/// returned. An instantiation is not a transition and returns no firing.
#[must_use]
pub fn apply(running: Running, enabled: Enabled, facts: Facts) -> (Running, Option<Firing>) {
    let running = running.consume(enabled.at);
    match enabled.kind {
        Kind::InstantiateConfirming(batch) => (running.instantiate_confirming(batch), None),
        Kind::InstantiateExecuting(decision) => (running.instantiate_executing(decision), None),
        Kind::Collect(from, batch) => collect(running, from, batch),
        Kind::Confirm(from, observed) => confirm(running, from, observed),
        Kind::Create(from, observed) => create(running, from, &observed),
        Kind::Trade(from, observed) => trade(running, from, &observed),
        Kind::Pool(from, observed) => pool(running, from, &observed),
        Kind::Swap(from, observed) => swap(running, from, &observed),
        Kind::Fund(from) => fund(running, from),
        Kind::Observe(from, observed) => observe(running, from, facts, &observed),
        Kind::Sign(id, from, _) => sign(running, id, from, facts),
        Kind::Submit(id, from, _) => submit(running, id, from, facts),
        Kind::Accept(id, from, observed) => accept(running, id, from, &observed),
        Kind::Reject(id, from) => reject(running, id, from),
        Kind::Settle(from) => settle(running, from),
    }
}

/// A key the arena does not yet hold is admitted only if the arena has room;
/// a key it already holds always advances, since advancing it grows the
/// arena by none.
fn collect(running: Running, from: rv::Collecting, batch: Batch) -> (Running, Option<Firing>) {
    let key = RecoveringKey::of(&batch);
    let admits_new_key = running.recovering.get(key).is_none();
    let outcome = if admits_new_key && running.recovering.is_full() {
        Hole::Derived(rv::CollectOutcome::ArenaFull)
    } else {
        rv::collect(from, event::DataShred)
    };
    let mut recovering = running.recovering.clone();
    let recovered = match outcome {
        Hole::Derived(rv::CollectOutcome::Recovered(to)) => {
            recovering.set(key, RecoveringAt::Recovered(to));
            true
        }
        Hole::Derived(rv::CollectOutcome::Collecting(to)) => {
            recovering.set(key, RecoveringAt::Collecting(to));
            false
        }
        Hole::Derived(rv::CollectOutcome::DuplicateShred | rv::CollectOutcome::ForeignSet)
        | Hole::Owed(_) => {
            recovering.set(key, RecoveringAt::Collecting(from));
            false
        }
        Hole::Derived(rv::CollectOutcome::ArenaFull) => false,
    };
    let running = Running {
        recovering,
        ..running
    };
    let running = if recovered {
        running.deliver(Event::RecoveredBatch(batch))
    } else {
        running
    };
    (running, Some(fire::collect(outcome)))
}

fn confirm(
    running: Running,
    from: cf::Decoded,
    observed: Vec<Observed>,
) -> (Running, Option<Firing>) {
    let outcome = cf::confirm(from, event::ConfirmedBlock);
    let (at, confirmed) = match outcome {
        Hole::Derived(cf::ConfirmOutcome::Confirmed(to)) => (ConfirmingAt::Confirmed(to), true),
        Hole::Derived(cf::ConfirmOutcome::Orphaned(to)) => (ConfirmingAt::Orphaned(to), false),
        Hole::Owed(_) => (ConfirmingAt::Decoded(from), false),
    };
    let mut confirming = running.confirming.clone();
    if confirmed {
        for one in &observed {
            confirming.set(one.signature, at);
        }
    }
    let through = observed.iter().map(|o| o.slot).max();
    let running = Running {
        confirming,
        held: match (confirmed, running.held, through) {
            (true, Some(held), Some(slot)) => Some(Held {
                as_of: held.as_of.max(slot),
                ..held
            }),
            _ => running.held,
        },
        ..running
    };
    let running = if confirmed {
        observed.into_iter().fold(running, |r, one| {
            r.deliver(Event::ConfirmedObservation(one))
        })
    } else {
        running
    };
    (running, Some(fire::confirm(outcome)))
}

/// Whether the observation is one of the venue's facts: a trade, a swap or a
/// migration. A creation or a transaction the reconstruction does not read
/// moves no reserve.
const fn is_venue_fact(observed: &Observed) -> bool {
    match observed.market {
        Market::Traded(_) | Market::Swapped(_) | Market::Graduated(_) => true,
        Market::Created(_) | Market::Elsewhere => false,
    }
}

/// Whether the observation is a migration: the chain's own proof the curve
/// completed, read before this region's own replay of the curve has to agree.
const fn is_a_graduation(observed: &Observed) -> bool {
    matches!(observed.market, Market::Graduated(_))
}

fn create(running: Running, from: rc::Unseen, observed: &Observed) -> (Running, Option<Firing>) {
    let Market::Created(mint) = observed.market else {
        return (running, None);
    };
    let minted = observation::creation(observed, mint);
    let outcome = rc::create(from, observation::carrying(minted));
    let (next, pair, held) = match outcome {
        Hole::Derived(rc::CreateOutcome::OnCurve(to)) => (
            ReconstructingAt::OnCurve(to),
            observed.market.mint(),
            created(observed),
        ),
        Hole::Derived(rc::CreateOutcome::NotACreate) | Hole::Owed(_) => {
            (ReconstructingAt::Unseen(from), running.pair, running.held)
        }
    };
    (
        Running {
            reconstructing: next,
            pair,
            held,
            ..running
        },
        Some(fire::create(outcome)),
    )
}

/// The reserves a curve holds when a create observation made it: the initial
/// reserves. Any other first observation gives the region no reserve to start
/// from, and a trade against it is a mismatch.
const fn created(observed: &Observed) -> Option<Held> {
    match observed.market {
        Market::Created(_) => Some(Held {
            reserves: curve::INITIAL,
            as_of: observed.slot,
        }),
        Market::Traded(_) | Market::Graduated(_) | Market::Swapped(_) | Market::Elsewhere => None,
    }
}

/// What `trade` returned for the observation, and the reserves it moved to.
///
/// A trade applies to the held reserves and is checked against the reserves the
/// observation reports (`statechart::curve::settle`). Reserves the curve has
/// used up move the pair to `Migrating`. An observation of the pool while the
/// pair is on the curve is `WrongVenue`.
fn trading(
    from: rc::OnCurve,
    running: &Running,
    observed: &Observed,
) -> (Hole<rc::TradeOutcome>, Option<Held>) {
    let refused = |outcome| (Hole::Derived(outcome), running.held);
    match observed.market {
        Market::Traded(trade) => {
            let Some(held) = running.held else {
                return refused(rc::TradeOutcome::ReserveMismatch);
            };
            match curve::settle(
                held.reserves,
                trade.instruction,
                trade.reported,
                running.fee,
            ) {
                Settled::ReserveMismatch => refused(rc::TradeOutcome::ReserveMismatch),
                Settled::Moved(reserves) => {
                    let moved = Some(Held {
                        reserves,
                        as_of: observed.slot,
                    });
                    match curve::venue(reserves) {
                        Venue::Curve => (
                            rc::trade(
                                from,
                                observation::carrying(observation::curve_trade(
                                    observed, trade, reserves,
                                )),
                            ),
                            moved,
                        ),
                        Venue::Complete => (
                            Hole::Derived(rc::TradeOutcome::Migrating(rc::Migrating)),
                            moved,
                        ),
                    }
                }
            }
        }
        Market::Swapped(_) | Market::Graduated(_) | Market::Created(_) | Market::Elsewhere => {
            refused(rc::TradeOutcome::WrongVenue)
        }
    }
}

fn trade(running: Running, from: rc::OnCurve, observed: &Observed) -> (Running, Option<Firing>) {
    let (outcome, held) = trading(from, &running, observed);
    let next = match outcome {
        Hole::Derived(rc::TradeOutcome::Migrating(to)) => ReconstructingAt::Migrating(to),
        Hole::Derived(rc::TradeOutcome::OnCurve(to)) => ReconstructingAt::OnCurve(to),
        Hole::Derived(rc::TradeOutcome::ReserveMismatch | rc::TradeOutcome::WrongVenue)
        | Hole::Owed(_) => ReconstructingAt::OnCurve(from),
    };
    (
        Running {
            reconstructing: next,
            held,
            ..running
        },
        Some(fire::trade(outcome)),
    )
}

/// The substate `pool` leaves the region in when it declines: the one it
/// fired from.
const fn declined_pool(from: rc::PoolFrom) -> ReconstructingAt {
    match from {
        rc::PoolFrom::Unseen(at) => ReconstructingAt::Unseen(at),
        rc::PoolFrom::OnCurve(at) => ReconstructingAt::OnCurve(at),
        rc::PoolFrom::Migrating(at) => ReconstructingAt::Migrating(at),
    }
}

/// What `pool` returned for the observation, and the pool it seeded.
///
/// A migration observation moves the pair to the pool, seeded from the
/// reserves this region tracked the curve at, or from the curve's
/// deterministic completion reserves ([`curve::COMPLETED`]) when it tracked
/// none: the migrate instruction is the chain's own proof the curve
/// completed, so it does not wait for this region's own replay to agree.
/// Any other observation of the pair, and a migration the seed reserves
/// cannot take, is not a pool creation.
fn pooling(
    from: rc::PoolFrom,
    running: &Running,
    observed: &Observed,
) -> (Hole<rc::PoolOutcome>, Option<PoolHeld>) {
    let declined = (Hole::Derived(rc::PoolOutcome::NotAPoolCreate), None);
    match observed.market {
        Market::Graduated(migration) => {
            let seeded = match migration.pool {
                Pool::PumpSwap { .. } => {
                    let completed = running.held.map_or(curve::COMPLETED, |held| held.reserves);
                    pool::seed(completed).map(PoolState::ConstantProduct)
                }
                Pool::Dlmm { .. } => migration
                    .dlmm_ladder
                    .ok_or(Refusal::ShapeUnknown)
                    .map(PoolState::Bin),
            };
            match seeded {
                Ok(reserves) => (
                    rc::pool(
                        from,
                        observation::carrying(observation::graduation(
                            observed, migration, reserves,
                        )),
                    ),
                    Some(PoolHeld {
                        pool: migration.pool,
                        reserves,
                        as_of: observed.slot,
                    }),
                ),
                Err(_) => declined,
            }
        }
        Market::Traded(_) | Market::Swapped(_) | Market::Created(_) | Market::Elsewhere => declined,
    }
}

fn pool(running: Running, from: rc::PoolFrom, observed: &Observed) -> (Running, Option<Firing>) {
    let (outcome, pooled) = pooling(from, &running, observed);
    let (next, held, pair) = match outcome {
        Hole::Derived(rc::PoolOutcome::OnPool(to)) => (
            ReconstructingAt::OnPool(to),
            None,
            observed.market.mint().or(running.pair),
        ),
        Hole::Derived(rc::PoolOutcome::NotAPoolCreate) | Hole::Owed(_) => {
            (declined_pool(from), running.held, running.pair)
        }
    };
    (
        Running {
            reconstructing: next,
            held,
            pooled,
            pair,
            ..running
        },
        Some(fire::pool(outcome)),
    )
}

/// The reserves the pool holds after the swap, when the swap is against the
/// pool the region holds and applies to its reserves.
fn swapped(held: PoolHeld, call: SwapCall, observed: &Observed) -> Option<PoolHeld> {
    if call.pool != held.pool.key() {
        return None;
    }
    let reserves: PoolState = match (held.pool, held.reserves) {
        (Pool::PumpSwap { .. }, PoolState::ConstantProduct(reserves)) => {
            PoolState::ConstantProduct(pool::advance(reserves, call.amount_in).ok()?)
        }
        (Pool::Dlmm { .. }, PoolState::Bin(ladder)) => {
            PoolState::Bin(dlmm::advance(ladder, call.amount_in).ok()?)
        }
        (Pool::PumpSwap { .. }, PoolState::Bin(_))
        | (Pool::Dlmm { .. }, PoolState::ConstantProduct(_)) => return None,
    };
    Some(PoolHeld {
        reserves,
        as_of: observed.slot,
        ..held
    })
}

/// What `swap` returned for the observation, and the pool's reserves after it.
///
/// A swap applies to the held pool reserves. A swap against another pool, or
/// one the reserves cannot take, is a `ReserveMismatch`. A curve fact while the
/// pair is on the pool is `WrongVenue`.
fn swapping(
    from: rc::OnPool,
    running: &Running,
    observed: &Observed,
) -> (Hole<rc::SwapOutcome>, Option<PoolHeld>) {
    match (observed.market, running.pooled) {
        (Market::Swapped(call), Some(held)) => match swapped(held, call, observed) {
            Some(moved) => match observation::amm_swap(observed, call, moved.reserves) {
                Ok(swap) => (rc::swap(from, observation::carrying(swap)), Some(moved)),
                Err(_) => (
                    Hole::Derived(rc::SwapOutcome::ReserveMismatch),
                    running.pooled,
                ),
            },
            None => (
                Hole::Derived(rc::SwapOutcome::ReserveMismatch),
                running.pooled,
            ),
        },
        (Market::Swapped(_), None) => (
            Hole::Derived(rc::SwapOutcome::ReserveMismatch),
            running.pooled,
        ),
        (Market::Traded(_) | Market::Graduated(_) | Market::Created(_) | Market::Elsewhere, _) => {
            (Hole::Derived(rc::SwapOutcome::WrongVenue), running.pooled)
        }
    }
}

fn swap(running: Running, from: rc::OnPool, observed: &Observed) -> (Running, Option<Firing>) {
    let (outcome, pooled) = swapping(from, &running, observed);
    let next = match outcome {
        Hole::Derived(rc::SwapOutcome::OnPool(to)) => ReconstructingAt::OnPool(to),
        Hole::Derived(rc::SwapOutcome::ReserveMismatch | rc::SwapOutcome::WrongVenue)
        | Hole::Owed(_) => ReconstructingAt::OnPool(from),
    };
    (
        Running {
            reconstructing: next,
            pooled,
            ..running
        },
        Some(fire::swap(outcome)),
    )
}

fn fund(running: Running, from: dc::Attached) -> (Running, Option<Firing>) {
    let outcome = dc::fund(from, event::Allocation);
    let next = match outcome {
        Hole::Derived(dc::FundOutcome::Active(to)) => DecidingAt::Active(to),
        Hole::Owed(_) => DecidingAt::Attached(from),
    };
    (
        Running {
            deciding: next,
            ..running
        },
        Some(fire::fund(outcome)),
    )
}

fn observe(
    running: Running,
    from: dc::ObserveFrom,
    facts: Facts,
    observed: &Observed,
) -> (Running, Option<Firing>) {
    let _ = observed;
    let outcome = dc::observe(from, observation::owed());
    let next = match outcome {
        Hole::Derived(dc::ObserveOutcome::Active(to)) => DecidingAt::Active(to),
        Hole::Derived(dc::ObserveOutcome::Draining(to)) => DecidingAt::Draining(to),
        Hole::Owed(_) => match from {
            dc::ObserveFrom::Active(same) => DecidingAt::Active(same),
            dc::ObserveFrom::Draining(same) => DecidingAt::Draining(same),
        },
    };
    let running = Running {
        deciding: next,
        ..running
    };
    let running = match facts {
        Facts::Decision(Some(decision)) => running.deliver(Event::Decision(decision)),
        Facts::Decision(None) | Facts::Nothing | Facts::Signing(_) | Facts::Sending(_) => running,
    };
    (running, Some(fire::observe(outcome)))
}

/// What `sign` returned for the signer's answer, and the transaction to keep.
///
/// A fact that is not the signer's answer leaves the body owed, and the driver
/// reports the transition as not fired.
fn signing(from: ex::Decided, facts: Facts) -> (Hole<ex::SignOutcome>, Option<SignedTransaction>) {
    let refused = |outcome| (Hole::Derived(outcome), None);
    match facts {
        Facts::Signing(Ok(signed)) => (ex::sign(from, event::Step), Some(signed)),
        Facts::Signing(Err(SignRefusal::InsufficientBalance)) => {
            refused(ex::SignOutcome::InsufficientBalance)
        }
        Facts::Signing(Err(SignRefusal::NoRoute)) => refused(ex::SignOutcome::NoRoute),
        Facts::Signing(Err(SignRefusal::StaleReconstruction)) => {
            refused(ex::SignOutcome::StaleReconstruction)
        }
        Facts::Nothing | Facts::Decision(_) | Facts::Sending(_) => (Hole::Owed(Owed), None),
    }
}

fn sign(
    running: Running,
    id: ExecutingId,
    from: ex::Decided,
    facts: Facts,
) -> (Running, Option<Firing>) {
    let (outcome, made) = signing(from, facts);
    let running = match (outcome, made) {
        (Hole::Derived(ex::SignOutcome::Signed(to)), Some(signed)) => {
            running.sign_executing(id, ExecutingAt::Signed(to), signed)
        }
        (
            Hole::Derived(
                ex::SignOutcome::InsufficientBalance
                | ex::SignOutcome::NoRoute
                | ex::SignOutcome::StaleReconstruction,
            )
            | Hole::Owed(_),
            _,
        ) => running,
        (Hole::Derived(ex::SignOutcome::Signed(_)), None) => running,
    };
    (running, Some(fire::sign(outcome)))
}

/// What `submit` returned for the wire's answer.
fn sending(from: ex::Signed, facts: &Facts) -> Hole<ex::SubmitOutcome> {
    match facts {
        Facts::Sending(Ok(())) => ex::submit(from, event::Step),
        Facts::Sending(Err(SendFailed(_))) => {
            Hole::Derived(ex::SubmitOutcome::Rejected(ex::Rejected))
        }
        Facts::Nothing | Facts::Decision(_) | Facts::Signing(_) => Hole::Owed(Owed),
    }
}

fn submit(
    running: Running,
    id: ExecutingId,
    from: ex::Signed,
    facts: Facts,
) -> (Running, Option<Firing>) {
    let outcome = sending(from, &facts);
    let running = match outcome {
        Hole::Derived(ex::SubmitOutcome::Submitted(to)) => running
            .set_executing_state(id, ExecutingAt::Submitted(to))
            .forget_unmatched_observations(),
        Hole::Derived(ex::SubmitOutcome::Rejected(to)) => {
            close_executing(running, id, ExecutingAt::Rejected(to), Filled::Rejected)
        }
        Hole::Owed(_) => running,
    };
    (running, Some(fire::submit(outcome)))
}

fn accept(
    running: Running,
    id: ExecutingId,
    from: ex::Submitted,
    observed: &Observed,
) -> (Running, Option<Firing>) {
    let outcome = ex::accept(from, observation::carrying(observation::own_fill(observed)));
    let running = match outcome {
        Hole::Derived(ex::AcceptOutcome::Accepted(to)) => {
            close_executing(running, id, ExecutingAt::Accepted(to), Filled::Accepted)
        }
        Hole::Derived(ex::AcceptOutcome::NotOurSignature) | Hole::Owed(_) => running,
    };
    (running, Some(fire::accept(outcome)))
}

fn reject(running: Running, id: ExecutingId, from: ex::Submitted) -> (Running, Option<Firing>) {
    let outcome = ex::reject(from, event::WatermarkPassed);
    let running = match outcome {
        Hole::Derived(ex::RejectOutcome::Rejected(to)) => {
            close_executing(running, id, ExecutingAt::Rejected(to), Filled::Rejected)
        }
        Hole::Owed(_) => running,
    };
    (running, Some(fire::reject(outcome)))
}

/// Move the instance to its final substate and tell the occupant how the
/// decision ended, with the signature that named it.
fn close_executing(
    running: Running,
    id: ExecutingId,
    at: ExecutingAt,
    filled: fn(Signature) -> Filled,
) -> Running {
    let signature = running.executing_signature(id);
    let running = running.set_executing_state(id, at);
    match signature {
        Some(signature) => running.deliver(Event::Fill(filled(signature))),
        None => running,
    }
}

fn settle(running: Running, from: dc::SettleFrom) -> (Running, Option<Firing>) {
    let outcome = dc::settle(from, event::Fill);
    let next = match outcome {
        Hole::Derived(dc::SettleOutcome::Active(to)) => DecidingAt::Active(to),
        Hole::Derived(dc::SettleOutcome::Draining(to)) => DecidingAt::Draining(to),
        Hole::Owed(_) => match from {
            dc::SettleFrom::Active(same) => DecidingAt::Active(same),
            dc::SettleFrom::Draining(same) => DecidingAt::Draining(same),
        },
    };
    (
        Running {
            deciding: next,
            ..running
        },
        Some(fire::settle(outcome)),
    )
}

#[cfg(test)]
mod arena_test_support {
    use super::{apply, Event, Facts, Running};

    /// Deliver one event and fire every transition it enables to
    /// completion, as `shell::drive::step` does. Every transition the
    /// arena tests reach reads no port, so `Facts::Nothing` answers each
    /// one.
    pub(super) fn feed(running: Running, event: Event) -> Running {
        let mut running = running.deliver(event);
        while let Some(enabled) = running.next() {
            let (next, _firing) = apply(running, enabled, Facts::Nothing);
            running = next;
        }
        running.end_turn()
    }
}

#[cfg(test)]
mod recovering_arena_tests {
    use super::arena_test_support::feed;
    use super::{
        Batch, Completion, Event, FecSetIndex, RecoveringAt, RecoveringKey, Running, Slot,
        RECOVERING_ARENA_CAPACITY,
    };

    /// A Complete-shred batch of the erasure set named by `slot` and
    /// `fec_set_index`, holding no transactions: `collect` reads only the
    /// key and the completion flag.
    fn batch(slot: u64, fec_set_index: u32) -> Batch {
        Batch {
            slot: Slot::new(slot),
            fec_set_index: FecSetIndex::new(fec_set_index),
            completion: Completion::Complete,
            transactions: Vec::new(),
        }
    }

    #[test]
    fn recovering_tracks_two_concurrent_sets() {
        let running = Running::boot();
        let running = feed(running, Event::DataShred(batch(1_000, 0)));
        let running = feed(running, Event::DataShred(batch(1_000, 1)));

        let key_a = RecoveringKey::of(&batch(1_000, 0));
        let key_b = RecoveringKey::of(&batch(1_000, 1));
        assert!(matches!(
            running.recovering.get(key_a),
            Some(RecoveringAt::Recovered(_))
        ));
        assert!(matches!(
            running.recovering.get(key_b),
            Some(RecoveringAt::Recovered(_))
        ));
        assert_eq!(running.recovering.live.len(), 2);
    }

    #[test]
    fn recovering_keys_instance_by_slot_and_fec_set_index() {
        let running = Running::boot();
        let running = feed(running, Event::DataShred(batch(1_000, 0)));
        let running = feed(running, Event::DataShred(batch(1_000, 1)));

        let key_a = RecoveringKey::of(&batch(1_000, 0));
        let key_b = RecoveringKey::of(&batch(1_000, 1));
        let before_b = running.recovering.get(key_b);

        // A shred of key_a's own set advances only key_a's instance.
        let running = feed(running, Event::DataShred(batch(1_000, 0)));

        assert_eq!(running.recovering.get(key_b), before_b);
        assert!(matches!(
            running.recovering.get(key_a),
            Some(RecoveringAt::Recovered(_))
        ));
    }

    #[test]
    fn recovering_arena_is_bounded() {
        let mut running = Running::boot();
        for index in 0..RECOVERING_ARENA_CAPACITY {
            let fec_set_index = u32::try_from(index).expect("capacity fits in a u32");
            running = feed(running, Event::DataShred(batch(1_000, fec_set_index)));
        }
        assert_eq!(running.recovering.live.len(), RECOVERING_ARENA_CAPACITY);

        let overflow = u32::try_from(RECOVERING_ARENA_CAPACITY).expect("capacity fits in a u32");
        let overflow_key = RecoveringKey::of(&batch(1_000, overflow));
        let running = feed(running, Event::DataShred(batch(1_000, overflow)));

        assert_eq!(running.recovering.live.len(), RECOVERING_ARENA_CAPACITY);
        assert_eq!(running.recovering.get(overflow_key), None);
    }
}

#[cfg(test)]
mod confirming_arena_tests {
    use super::arena_test_support::feed;
    use super::{
        Batch, Completion, ConfirmingAt, Event, FecSetIndex, Market, Record, RecoveringAt,
        RecoveringKey, Running, Signature, Slot, Transacted, CONFIRMING_ARENA_CAPACITY,
    };
    use statechart::edge::Receipt;
    use statechart::units::Nanos;

    /// The signature a fixture transaction carries, keyed by `seed`.
    fn signature_of(seed: u8) -> Signature {
        let mut bytes = [0u8; 64];
        bytes[0] = seed;
        Signature::new(bytes)
    }

    /// A decoded transaction naming no venue fact, keyed by `seed` so its
    /// signature is distinct from every other seed's.
    fn transacted(seed: u8) -> Transacted {
        Transacted {
            receipt: Receipt::at(Nanos::new(0)),
            signature: signature_of(seed),
            market: Market::Elsewhere,
        }
    }

    /// A Complete-shred batch of its own erasure set, named by
    /// `fec_set_index`, carrying the given transactions. Delivered as a
    /// `DataShred`, it recovers through `Recovering.collect` the way a real
    /// shred does, which in turn delivers `RecoveredBatch` to Confirming.
    fn batch(fec_set_index: u32, transactions: Vec<Transacted>) -> Batch {
        Batch {
            slot: Slot::new(1_000),
            fec_set_index: FecSetIndex::new(fec_set_index),
            completion: Completion::Complete,
            transactions,
        }
    }

    /// Two signatures recovered into their own live, `Decoded` instances,
    /// through the ordinary `Recovering` path: the shreds that named them
    /// also recovered, and a recovered batch naming no transaction starts
    /// no instance.
    fn two_signatures_decoded() -> Running {
        let running = Running::boot();
        let running = feed(running, Event::DataShred(batch(0, vec![transacted(1)])));
        let running = feed(running, Event::DataShred(batch(1, vec![transacted(2)])));

        assert!(matches!(
            running
                .recovering
                .get(RecoveringKey::of(&batch(0, Vec::new()))),
            Some(RecoveringAt::Recovered(_))
        ));
        assert!(matches!(
            running
                .recovering
                .get(RecoveringKey::of(&batch(1, Vec::new()))),
            Some(RecoveringAt::Recovered(_))
        ));
        assert!(matches!(
            running.confirming.get(signature_of(1)),
            Some(ConfirmingAt::Decoded(_))
        ));
        assert!(matches!(
            running.confirming.get(signature_of(2)),
            Some(ConfirmingAt::Decoded(_))
        ));
        assert_eq!(running.confirming.live.len(), 2);

        let running = feed(running, Event::DataShred(batch(2, Vec::new())));
        assert_eq!(running.confirming.live.len(), 2);
        running
    }

    /// The arena admits only up to its capacity: fill it, then the next
    /// signature is refused, and the instances already live stay live.
    ///
    /// Every batch reuses `fec_set_index` 0, already `Recovered`: reusing a
    /// held key always re-collects (`Running::recovering_takes`), so it
    /// keeps delivering fresh `RecoveredBatch` events without growing
    /// Recovering's own arena past its unrelated capacity.
    fn fill_to_capacity_and_assert_bounded(mut running: Running) -> Running {
        let capacity = u8::try_from(CONFIRMING_ARENA_CAPACITY).expect("capacity fits in a u8");
        for seed in 3..=capacity {
            running = feed(running, Event::DataShred(batch(0, vec![transacted(seed)])));
        }
        assert_eq!(running.confirming.live.len(), CONFIRMING_ARENA_CAPACITY);

        let overflow_seed = capacity
            .checked_add(1)
            .expect("capacity leaves room for one more seed");
        let running = feed(
            running,
            Event::DataShred(batch(0, vec![transacted(overflow_seed)])),
        );
        assert_eq!(running.confirming.live.len(), CONFIRMING_ARENA_CAPACITY);
        assert_eq!(running.confirming.get(signature_of(overflow_seed)), None);
        assert!(matches!(
            running.confirming.get(signature_of(1)),
            Some(ConfirmingAt::Decoded(_))
        ));
        assert!(matches!(
            running.confirming.get(signature_of(2)),
            Some(ConfirmingAt::Decoded(_))
        ));
        running
    }

    /// Confirming one signature's block does not touch another's live
    /// instance: each is decided by its own block, independently.
    fn assert_confirmations_are_independent(running: Running) {
        let running = feed(
            running,
            Event::ConfirmedBlock(Record::Held {
                slot: Slot::new(1_000),
                signatures: vec![signature_of(1)],
            }),
        );
        assert!(matches!(
            running.confirming.get(signature_of(1)),
            Some(ConfirmingAt::Confirmed(_))
        ));
        assert!(matches!(
            running.confirming.get(signature_of(2)),
            Some(ConfirmingAt::Decoded(_))
        ));

        let running = feed(
            running,
            Event::ConfirmedBlock(Record::Held {
                slot: Slot::new(1_001),
                signatures: vec![signature_of(2)],
            }),
        );
        assert!(matches!(
            running.confirming.get(signature_of(2)),
            Some(ConfirmingAt::Confirmed(_))
        ));
    }

    /// Drive the Confirming region through recovery, instantiation, the
    /// arena's bound, and a partial confirmation: every fact both
    /// acceptance clauses need, so either clause's own test can stand on
    /// its own.
    fn drive_and_assert() {
        let running = two_signatures_decoded();
        let running = fill_to_capacity_and_assert_bounded(running);
        assert_confirmations_are_independent(running);
    }

    #[test]
    fn confirming_holds_one_instance_per_signature() {
        drive_and_assert();
    }

    #[test]
    fn confirming_two_in_flight_signatures_both_live() {
        drive_and_assert();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use statechart::units::Nanos;

    /// A pair, so `deliver` addresses the observation to Reconstructing only
    /// when it is of that pair: `Market::Elsewhere` is of none, so
    /// Reconstructing never competes with Executing for it.
    fn pair() -> Pubkey {
        Pubkey::new([9; 32])
    }

    fn signed(signature: Signature) -> SignedTransaction {
        SignedTransaction {
            signature,
            wire: Vec::new(),
            valid_until: Slot::new(1_000),
        }
    }

    /// One Executing instance, already submitted under `signature`.
    fn submitted_instance(signature: Signature) -> ExecutingInstance {
        ExecutingInstance {
            id: ExecutingId(0),
            at: ExecutingAt::Submitted(ex::Submitted),
            decision: Decision::Enter {
                mint: pump_strategy::units::Mint::new([7; 32]),
                size: pump_strategy::units::Lamports::new(1_000_000),
            },
            signed: Some(signed(signature)),
        }
    }

    /// When Executing holds a submitted signature and a `ConfirmedObservation`
    /// names that same signature, the transition Executing.accept becomes
    /// enabled carrying the real `Observed` the event delivered, not a
    /// synthesized placeholder.
    #[test]
    fn accept_becomes_enabled_carrying_the_events_real_observation() {
        let our_signature = Signature::new([1; 64]);
        let running = Running {
            executing: vec![submitted_instance(our_signature)],
            pair: Some(pair()),
            ..Running::boot()
        };
        let observed = Observed {
            slot: Slot::new(500),
            receipt: Receipt::at(Nanos::new(42)),
            signature: our_signature,
            market: Market::Elsewhere,
        };

        let running = running.deliver(Event::ConfirmedObservation(observed));
        let enabled = running.next().expect("accept is enabled");

        assert_eq!(
            enabled.kind,
            Kind::Accept(ExecutingId(0), ex::Submitted, observed)
        );
    }

    /// A `ConfirmedObservation` of a different signature is not our
    /// transaction, so it never enables Executing.accept.
    #[test]
    fn accept_ignores_a_confirmed_observation_of_another_signature() {
        let our_signature = Signature::new([1; 64]);
        let running = Running {
            executing: vec![submitted_instance(our_signature)],
            pair: Some(pair()),
            ..Running::boot()
        };
        let observed = Observed {
            slot: Slot::new(500),
            receipt: Receipt::at(Nanos::new(42)),
            signature: Signature::new([2; 64]),
            market: Market::Elsewhere,
        };

        let running = running.deliver(Event::ConfirmedObservation(observed));

        assert!(!matches!(
            running.next(),
            Some(Enabled {
                kind: Kind::Accept(..),
                ..
            })
        ));
    }
}

#[cfg(test)]
mod pooling {
    use statechart::programs::{Pool, PoolState, Reserves};
    use statechart::units::{Lamports, Nanos, TokenUnits};

    use super::*;
    use crate::port::Migration;

    pub(super) fn pool_account() -> Pool {
        Pool::PumpSwap {
            pool: Pubkey::new([3; 32]),
            base_vault: Pubkey::new([4; 32]),
            quote_vault: Pubkey::new([5; 32]),
        }
    }

    fn observed(market: Market) -> Observed {
        Observed {
            slot: Slot::new(1_000),
            receipt: Receipt::at(Nanos::new(1)),
            signature: Signature::new([1; 64]),
            market,
        }
    }

    #[test]
    fn carries_the_real_graduation_observation() {
        let migration = Migration {
            mint: Pubkey::new([2; 32]),
            pool: pool_account(),
            dlmm_ladder: None,
        };
        let observed = observed(Market::Graduated(migration));
        let running = Running::boot();

        let (outcome, pooled) = pooling(rc::PoolFrom::Unseen(rc::Unseen), &running, &observed);

        assert_eq!(outcome, Hole::Derived(rc::PoolOutcome::OnPool(rc::OnPool)));
        let seed = pool::seed(curve::COMPLETED).expect("the completion reserves seed the pool");
        let pooled = pooled.expect("a graduation seeds the pool");
        assert_eq!(pooled.pool, migration.pool);
        assert_eq!(pooled.reserves, PoolState::ConstantProduct(seed));
        assert_eq!(pooled.as_of, observed.slot);

        // The real graduation record, not the owed placeholder, is what the
        // call site now has to send to `rc::pool`.
        let carried = observation::carrying(observation::graduation(
            &observed,
            migration,
            PoolState::ConstantProduct(seed),
        ));
        assert_ne!(carried, observation::owed());
    }

    #[test]
    fn declines_a_migration_the_seed_reserves_cannot_take() {
        let migration = Migration {
            mint: Pubkey::new([2; 32]),
            pool: pool_account(),
            dlmm_ladder: None,
        };
        let held = Held {
            reserves: Reserves::new(
                Lamports::new(1),
                TokenUnits::new(1),
                Lamports::new(0),
                TokenUnits::new(0),
            )
            .expect("nonzero virtual reserves"),
            as_of: Slot::new(999),
        };
        let running = Running {
            held: Some(held),
            ..Running::boot()
        };
        let observed = observed(Market::Graduated(migration));

        let (outcome, pooled) = pooling(rc::PoolFrom::Unseen(rc::Unseen), &running, &observed);

        assert_eq!(outcome, Hole::Derived(rc::PoolOutcome::NotAPoolCreate));
        assert!(pooled.is_none());
    }

    #[test]
    fn declines_a_non_graduation_observation() {
        let running = Running::boot();
        let observed = observed(Market::Created(Pubkey::new([9; 32])));

        let (outcome, pooled) = pooling(rc::PoolFrom::Unseen(rc::Unseen), &running, &observed);

        assert_eq!(outcome, Hole::Derived(rc::PoolOutcome::NotAPoolCreate));
        assert!(pooled.is_none());
    }
}

#[cfg(test)]
mod swapping {
    use statechart::programs::{PoolReserves, PoolState, SwapAmount, SwapDirection};
    use statechart::units::{Lamports, Nanos, TokenUnits};

    use super::pooling::pool_account;
    use super::*;

    fn seeded() -> PoolReserves {
        PoolReserves::new(TokenUnits::new(1_000_000_000), Lamports::new(1_000_000_000))
            .expect("nonzero pool reserves")
    }

    fn held(reserves: PoolReserves) -> PoolHeld {
        PoolHeld {
            pool: pool_account(),
            reserves: PoolState::ConstantProduct(reserves),
            as_of: Slot::new(1_000),
        }
    }

    fn observed(market: Market) -> Observed {
        Observed {
            slot: Slot::new(1_001),
            receipt: Receipt::at(Nanos::new(2)),
            signature: Signature::new([6; 64]),
            market,
        }
    }

    fn buy(pool: Pubkey) -> SwapCall {
        SwapCall {
            mint: Pubkey::new([2; 32]),
            pool,
            signer: Pubkey::new([7; 32]),
            direction: SwapDirection::BuyBase,
            amount_in: SwapAmount::SolIn {
                sol: Lamports::new(1_000_000),
                min_tokens: TokenUnits::new(1),
            },
        }
    }

    #[test]
    fn carries_the_real_amm_swap_observation() {
        let call = buy(pool_account().key());
        let running = Running {
            pooled: Some(held(seeded())),
            ..Running::boot()
        };
        let observed = observed(Market::Swapped(call));

        let (outcome, pooled) = swapping(rc::OnPool, &running, &observed);

        assert_eq!(outcome, Hole::Derived(rc::SwapOutcome::OnPool(rc::OnPool)));
        let expected = pool::advance(seeded(), call.amount_in).expect("the buy fits the pool");
        let pooled = pooled.expect("a swap against the held pool advances its reserves");
        assert_eq!(pooled.reserves, PoolState::ConstantProduct(expected));
        assert_eq!(pooled.as_of, observed.slot);

        // The real swap record, not the owed placeholder, is what the call
        // site now has to send to `rc::swap`.
        let carried = observation::carrying(
            observation::amm_swap(&observed, call, PoolState::ConstantProduct(expected))
                .expect("a consistent call mints"),
        );
        assert_ne!(carried, observation::owed());
    }

    #[test]
    fn reserve_mismatch_against_a_different_pool() {
        let call = buy(Pubkey::new([99; 32]));
        let running = Running {
            pooled: Some(held(seeded())),
            ..Running::boot()
        };
        let observed = observed(Market::Swapped(call));

        let (outcome, pooled) = swapping(rc::OnPool, &running, &observed);

        assert_eq!(outcome, Hole::Derived(rc::SwapOutcome::ReserveMismatch));
        assert_eq!(pooled, running.pooled);
    }

    #[test]
    fn reserve_mismatch_with_no_pool_held() {
        let call = buy(pool_account().key());
        let running = Running::boot();
        let observed = observed(Market::Swapped(call));

        let (outcome, pooled) = swapping(rc::OnPool, &running, &observed);

        assert_eq!(outcome, Hole::Derived(rc::SwapOutcome::ReserveMismatch));
        assert!(pooled.is_none());
    }

    #[test]
    fn wrong_venue_for_a_curve_observation() {
        let running = Running {
            pooled: Some(held(seeded())),
            ..Running::boot()
        };
        let observed = observed(Market::Created(Pubkey::new([9; 32])));

        let (outcome, pooled) = swapping(rc::OnPool, &running, &observed);

        assert_eq!(outcome, Hole::Derived(rc::SwapOutcome::WrongVenue));
        assert_eq!(pooled, running.pooled);
    }
}
