//! The capture reader: a pcap carried to the transactions the machine received.
//!
//! Concept: This module reads an ordered run of pcap files into entry batches,
//! each paired with the receipt of the packet that completed it, and reads each
//! batch into the [`Observed`] transactions the reconstruction takes as input.
//!
//! The receipt is the time this machine received the last shred of a batch,
//! never a time from a payload. When recovery rebuilt the last shred, no packet
//! carried it, and the receipt is that of the erasure set that held it. Every source of observations that replays a
//! capture reads it here, so the reconstruction, the price decode and the
//! backtest see one ordered stream.
//!
//! The run is streamed. The [`Window`] holds the erasure sets of the newest
//! [`EVICTION_DISTANCE`] slots and no more: when the newest slot moves on, the
//! sets of an older slot are recovered, joined into batches, handed on and
//! dropped (`docs/chart.json5`, Recovering: the arena is bounded). The memory
//! it uses is bounded by that window, not by the length of the run, and the
//! window carries across the boundary of one file and the next. No erasure set
//! and no entry batch crosses a slot, so the batches a slot yields do not
//! depend on when it is handed on.

use std::collections::BTreeMap;
use std::num::NonZeroUsize;
use std::path::{Path, PathBuf};
use std::sync::mpsc::{self, Receiver, SyncSender};
use std::sync::{Arc, Mutex, PoisonError};
use std::thread;

use statechart::edge::Packet;
use statechart::edge::Receipt;
use statechart::parse;
use statechart::units::Slot;
use statechart::wire::{FecSetIndex, Shred, ShredIndex};
use statechart::Refusal;

use crate::deshred::Deshredded;
use crate::market::market_of;
use crate::pcap::PcapRefused;
use crate::port::Observed;
use crate::reconstruct::{batches, Report};
use crate::sequence::{expand, Packets, PcapSequence};
use crate::sets::Sets;

/// How many slots behind the newest a slot stays in the arena, unless the run
/// names another distance.
pub const EVICTION_DISTANCE: u64 = 64;

/// Concept: This value is how many slots behind the newest a slot stays in the
/// window. A shred of an older slot arrives too late and is counted, not read.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Distance(u64);

impl Distance {
    /// A distance of `slots` slots.
    #[must_use]
    pub const fn new(slots: u64) -> Self {
        Self(slots)
    }
}

impl Distance {
    /// How many slots behind the newest a slot stays in the window.
    #[must_use]
    pub const fn slots(self) -> u64 {
        self.0
    }
}

impl Default for Distance {
    fn default() -> Self {
        Self(EVICTION_DISTANCE)
    }
}

/// Concept: This value is how many threads recover an eviction's erasure sets,
/// beside the thread that reads packets and moves the window.
///
/// A set's Reed-Solomon recovery does not depend on any other set's
/// (`docs/chart.json5`, Recovering: the arena is bounded to one window), so
/// [`crate::reconstruct::batches`] splits an eviction's sets across the
/// workers. One worker recovers every set inline, on the calling thread.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DecodeWorkers(NonZeroUsize);

impl DecodeWorkers {
    /// One worker: the packet-reading thread decodes every eviction inline.
    pub const SEQUENTIAL: Self = Self(NonZeroUsize::MIN);

    /// `count` decode workers, beside the packet-reading thread.
    #[must_use]
    pub const fn new(count: NonZeroUsize) -> Self {
        Self(count)
    }

    /// How many decode workers.
    #[must_use]
    pub const fn get(self) -> usize {
        self.0.get()
    }

    /// The worker count a run applies: `named` when the run names one, else
    /// one worker.
    #[must_use]
    pub fn configured(named: Option<Self>) -> Self {
        named.unwrap_or(Self::SEQUENTIAL)
    }

    /// Read a worker count written as a positive integer.
    ///
    /// # Errors
    /// The text of the refusal when `text` is not a positive integer.
    pub fn parse(text: &str) -> Result<Self, String> {
        let refuse = || format!("{text}: a positive integer");
        let count: usize = text.parse().map_err(|_| refuse())?;
        NonZeroUsize::new(count).map(Self).ok_or_else(refuse)
    }
}

impl Default for DecodeWorkers {
    fn default() -> Self {
        Self::SEQUENTIAL
    }
}

/// Concept: This value is why a capture could not be read into batches.
#[derive(Debug)]
pub enum CaptureRefused {
    /// The pcap file was refused.
    Pcap(PcapRefused),
    /// The core's parsers refused the bytes of a shred, a batch or a transaction.
    Parse(Refusal),
    /// The capture holds no packet of the last shred of a batch.
    NoReceipt {
        /// The slot of the batch.
        slot: Slot,
        /// The index of the batch's last shred.
        last: ShredIndex,
    },
    /// A decode worker ended without a result for the job it took.
    WorkerLost,
}

impl From<PcapRefused> for CaptureRefused {
    fn from(refused: PcapRefused) -> Self {
        Self::Pcap(refused)
    }
}

impl From<Refusal> for CaptureRefused {
    fn from(refusal: Refusal) -> Self {
        Self::Parse(refusal)
    }
}

/// Concept: This value is the receipts of the packets the window holds.
///
/// A data shred that arrived has the receipt of its own packet. A data shred
/// that recovery rebuilt has no packet, so it takes the receipt of its erasure
/// set: the latest receipt of any packet of the set. Recovery needs the packets
/// of the set, so the shred was not known before the last of them arrived, and
/// the set's receipt is never earlier than the moment the shred became known.
#[derive(Clone, Debug, Default)]
pub(crate) struct Receipts {
    pub(crate) shreds: BTreeMap<(Slot, ShredIndex), Receipt>,
    pub(crate) sets: BTreeMap<(Slot, FecSetIndex), Receipt>,
    /// The earliest receipt of any packet of each slot.
    pub(crate) firsts: BTreeMap<Slot, Receipt>,
}

impl Receipts {
    /// Note the packet of a shred of `slot` and `set`, and of the data shred at
    /// `index` if it is one.
    fn note(&mut self, slot: Slot, set: FecSetIndex, data: Option<ShredIndex>, receipt: Receipt) {
        if let Some(index) = data {
            self.shreds.insert((slot, index), receipt);
        }
        self.sets
            .entry((slot, set))
            .and_modify(|held| *held = (*held).max(receipt))
            .or_insert(receipt);
        self.firsts
            .entry(slot)
            .and_modify(|held| *held = (*held).min(receipt))
            .or_insert(receipt);
    }

    /// The earliest receipt of any packet the window still holds.
    fn earliest(&self) -> Option<Receipt> {
        self.firsts.values().min().copied()
    }

    /// The receipt of the data shred at `index` of `slot`: the receipt of its
    /// packet if it arrived, else that of the erasure set that holds it, the
    /// set with the greatest first index not after `index`.
    fn of(&self, slot: Slot, index: ShredIndex) -> Option<Receipt> {
        self.shreds.get(&(slot, index)).copied().or_else(|| {
            let from = (slot, FecSetIndex::new(0));
            let to = (slot, FecSetIndex::new(index.get()));
            self.sets.range(from..=to).next_back().map(|(_, r)| *r)
        })
    }

    /// Take out the receipts of every slot before `floor`, leaving the rest.
    fn drain_before(&mut self, floor: Slot) -> Self {
        let from = (floor, ShredIndex::new(0));
        let shreds = self.shreds.split_off(&from);
        let sets = self.sets.split_off(&(floor, FecSetIndex::new(0)));
        let firsts = self.firsts.split_off(&floor);
        Self {
            shreds: std::mem::replace(&mut self.shreds, shreds),
            sets: std::mem::replace(&mut self.sets, sets),
            firsts: std::mem::replace(&mut self.firsts, firsts),
        }
    }
}

/// One entry batch, with the receipt of the packet that completed it.
pub type Received = (Deshredded, Receipt);

/// The batches of the sets, each with the receipt of its last shred.
///
/// `workers` threads recover the sets' Reed-Solomon shape; one worker
/// recovers them inline, on the calling thread.
fn received(
    mut sets: Sets,
    receipts: &Receipts,
    workers: DecodeWorkers,
) -> Result<Vec<Received>, CaptureRefused> {
    batches(&mut sets, &mut Report::default(), workers)?
        .into_iter()
        .map(|batch| {
            let receipt = receipts
                .of(batch.slot, batch.last)
                .ok_or(CaptureRefused::NoReceipt {
                    slot: batch.slot,
                    last: batch.last,
                })?;
            Ok((batch, receipt))
        })
        .collect()
}

/// Concept: This value is the erasure sets of the newest slots of a capture,
/// and the receipts of their data shreds.
#[derive(Clone, Debug)]
pub struct Window {
    pub(crate) distance: Distance,
    pub(crate) sets: Sets,
    pub(crate) receipts: Receipts,
    pub(crate) newest: Option<Slot>,
    pub(crate) floor: Slot,
    pub(crate) late: usize,
    pub(crate) evicted: usize,
}

impl Default for Window {
    fn default() -> Self {
        Self::new(Distance::default())
    }
}

impl Window {
    /// An empty window that keeps the newest `distance` slots.
    #[must_use]
    pub fn new(distance: Distance) -> Self {
        Self {
            distance,
            sets: Sets::default(),
            receipts: Receipts::default(),
            newest: None,
            floor: Slot::default(),
            late: 0,
            evicted: 0,
        }
    }

    /// Take one packet in. The batches of every slot it moves out of the
    /// window come back, in slot and index order.
    ///
    /// # Errors
    /// [`CaptureRefused`] when the packet is not a shred, or a batch does not
    /// read.
    pub fn accept(&mut self, packet: &Packet) -> Result<Vec<Received>, CaptureRefused> {
        match self.accept_pending(packet)? {
            Some((sets, gone)) => received(sets, &gone, DecodeWorkers::SEQUENTIAL),
            None => Ok(Vec::new()),
        }
    }

    /// Take one packet in, as [`Window::accept`], but leave the sets an
    /// eviction moves out undecoded: the caller decodes them, inline or on a
    /// decode worker of its own. [`Window::accept`] is this decoded inline,
    /// on the spot.
    ///
    /// One eviction is usually a handful of sets (one slot's worth), so
    /// [`feed_flow_parallel`] spreads evictions themselves across a pool of
    /// decode workers that outlives any one of them, rather than spinning up
    /// threads anew for each: a thread's own cost would otherwise dwarf a
    /// small eviction's.
    ///
    /// # Errors
    /// [`CaptureRefused`] when the packet is not a shred.
    pub(crate) fn accept_pending(
        &mut self,
        packet: &Packet,
    ) -> Result<Option<(Sets, Receipts)>, CaptureRefused> {
        let shred = parse::shred(packet)?;
        let header = shred.header();
        let newest = self.newest.map_or(header.slot, |at| at.max(header.slot));
        self.newest = Some(newest);
        let floor = Slot::new(newest.get().saturating_sub(self.distance.0));
        let pending = if floor > self.floor {
            self.floor = floor;
            Some(self.evict_pending())
        } else {
            None
        };
        if header.slot < self.floor {
            self.late = self.late.saturating_add(1);
            return Ok(pending);
        }
        let data = match shred {
            Shred::Data(data) => Some(data.header().index),
            Shred::Coding(_) => None,
        };
        self.receipts
            .note(header.slot, header.fec_set_index, data, packet.receipt());
        self.sets.insert(packet)?;
        Ok(pending)
    }

    /// The sets of the slots before the floor, which leave the window,
    /// undecoded.
    fn evict_pending(&mut self) -> (Sets, Receipts) {
        let gone = self.receipts.drain_before(self.floor);
        let sets = self.sets.drain_before(self.floor);
        self.evicted = self.evicted.saturating_add(sets.len());
        (sets, gone)
    }

    /// The earliest receipt of any packet of a slot the window holds. No batch
    /// the window hands on later has an earlier receipt than this one, nor than
    /// the packet the window took in last, when the packets come in receipt order.
    #[must_use]
    pub fn earliest_held(&self) -> Option<Receipt> {
        self.receipts.earliest()
    }

    /// How many erasure sets the window has moved out before the end of the run.
    #[must_use]
    pub const fn evicted(&self) -> usize {
        self.evicted
    }

    /// How many shreds arrived for a slot the window had already moved past.
    #[must_use]
    pub const fn late(&self) -> usize {
        self.late
    }

    /// The batches of every slot still in the window, at the end of the run.
    ///
    /// `workers` threads recover the window's erasure sets; one worker
    /// recovers them inline, on the calling thread.
    ///
    /// # Errors
    /// [`CaptureRefused`] when a batch does not read.
    pub fn finish(self, workers: DecodeWorkers) -> Result<Vec<Received>, CaptureRefused> {
        received(self.sets, &self.receipts, workers)
    }
}

/// Concept: This value is what a run of capture files held.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Session {
    /// How many files the run read.
    pub files: usize,
    /// How many CORVUS capture-markers the files hold.
    pub markers: usize,
    /// How many shreds arrived after their slot left the window.
    pub late: usize,
    /// How many erasure sets left the window before the end of the run.
    pub evicted: usize,
}

/// Read the capture files `paths` name as one capture, in order, and hand each
/// entry batch to `sink` with the receipt of the packet that completed it.
///
/// A directory stands for its `.pcap` files in file-name order. The batches
/// come in the order the window moves past their slots.
///
/// # Errors
/// The refusal of the capture, or of `sink`.
pub fn stream_batches<E: From<CaptureRefused>>(
    paths: &[PathBuf],
    distance: Distance,
    sink: impl FnMut(&Deshredded, Receipt) -> Result<(), E>,
) -> Result<Session, E> {
    let mut source = PcapSequence::new(expand(paths).map_err(CaptureRefused::from)?);
    stream_batches_from(&mut source, distance, sink)
}

/// What the reader of a capture hands on.
#[derive(Clone, Copy, Debug)]
pub enum Flow<'a> {
    /// An entry batch, with the receipt of the packet that completed it.
    Batch(&'a Deshredded, Receipt),
    /// No batch handed on after this has an earlier receipt, when the packets
    /// come in receipt order.
    Floor(Receipt),
}

/// Read the packets of `source` as one capture, and hand each entry batch to
/// `sink` with the receipt of the packet that completed it.
///
/// [`stream_batches`] is this over the files a run of paths names.
///
/// # Errors
/// The refusal of the capture, or of `sink`.
pub fn stream_batches_from<E: From<CaptureRefused>>(
    source: &mut impl Packets,
    distance: Distance,
    mut sink: impl FnMut(&Deshredded, Receipt) -> Result<(), E>,
) -> Result<Session, E> {
    stream_flow_from(source, distance, |flow| match flow {
        Flow::Batch(batch, receipt) => sink(batch, receipt),
        Flow::Floor(_) => Ok(()),
    })
}

/// Read the packets of `source` as one capture, and hand each entry batch to
/// `sink` with the receipt of the packet that completed it, and after each
/// packet the [`Flow::Floor`] under the receipt of every batch to come.
///
/// The batches of a slot come when the window moves past it, so the receipts of
/// the batches do not run in order. The floor lets a reader release what it holds
/// below it in order, and hold no more than the window does.
///
/// # Errors
/// The refusal of the capture, or of `sink`.
pub fn stream_flow_from<E: From<CaptureRefused>>(
    source: &mut impl Packets,
    distance: Distance,
    mut sink: impl FnMut(Flow<'_>) -> Result<(), E>,
) -> Result<Session, E> {
    let mut window = Window::new(distance);
    feed_flow(&mut window, source, &mut sink)?;
    let session = Session {
        files: source.files_read(),
        markers: source.markers(),
        late: window.late(),
        evicted: window.evicted(),
    };
    finish_flow(window, &mut sink)?;
    Ok(session)
}

/// Read every packet of `source` into `window`, and hand each entry batch that
/// leaves the window to `sink`, and after each packet the [`Flow::Floor`].
///
/// The window keeps the erasure sets of the newest slots: nothing is handed on
/// for them. A later call, with the next packets of the same capture, reads on
/// from the window as it stands, so a capture read in parts gives the flow of
/// the capture read whole, once [`finish_flow`] hands on what the window still
/// holds.
///
/// # Errors
/// The refusal of the capture, or of `sink`.
pub fn feed_flow<E: From<CaptureRefused>>(
    window: &mut Window,
    source: &mut impl Packets,
    sink: &mut impl FnMut(Flow<'_>) -> Result<(), E>,
) -> Result<(), E> {
    while let Some(packet) = source.next_packet().map_err(CaptureRefused::from)? {
        for (batch, receipt) in window.accept(&packet).map_err(E::from)? {
            sink(Flow::Batch(&batch, receipt))?;
        }
        let at = packet.receipt();
        sink(Flow::Floor(
            window.earliest_held().map_or(at, |held| held.min(at)),
        ))?;
    }
    Ok(())
}

/// One eviction's erasure sets, undecoded, on the way to a decode worker.
struct Job {
    id: u64,
    sets: Sets,
    receipts: Receipts,
}

/// One step of the flow [`feed_flow_parallel`] sinks, in the order the
/// packets produced it: a job's batches, once decoded, or a floor.
enum Step {
    /// The batches decoded from the job at this id, each as a [`Flow::Batch`].
    Batch(u64),
    /// A [`Flow::Floor`] at this receipt.
    Floor(Receipt),
}

/// Take jobs from `jobs` and decode each into `results`, under its id, until
/// `jobs` closes. A worker decodes its job alone, on the thread it already
/// has: the parallelism is many jobs across the pool, not many threads for
/// one job.
fn decode_worker(
    jobs: &Arc<Mutex<Receiver<Job>>>,
    results: &SyncSender<(u64, Result<Vec<Received>, CaptureRefused>)>,
) {
    loop {
        let job = {
            let queue = jobs.lock().unwrap_or_else(PoisonError::into_inner);
            queue.recv()
        };
        let Ok(job) = job else {
            return;
        };
        let decoded = received(job.sets, &job.receipts, DecodeWorkers::SEQUENTIAL);
        if results.send((job.id, decoded)).is_err() {
            return;
        }
    }
}

/// Read every packet of `source` into `window`, send each eviction's sets to
/// `jobs` for a decode worker, and describe the flow of the run as `steps`,
/// in the order [`feed_flow`] would sink it.
///
/// # Errors
/// The refusal of the capture.
fn dispatch_flow(
    window: &mut Window,
    source: &mut impl Packets,
    jobs: &SyncSender<Job>,
    steps: &SyncSender<Step>,
) -> Result<(), CaptureRefused> {
    let mut next_id: u64 = 0;
    let mut sent_floor: Option<Receipt> = None;
    while let Some(packet) = source.next_packet()? {
        if let Some((sets, receipts)) = window.accept_pending(&packet)? {
            let id = next_id;
            next_id = next_id.saturating_add(1);
            let dispatched = jobs.send(Job { id, sets, receipts }).is_ok()
                && steps.send(Step::Batch(id)).is_ok();
            if !dispatched {
                return Ok(());
            }
        }
        let at = packet.receipt();
        let floor = window.earliest_held().map_or(at, |held| held.min(at));
        // The floor is a non-decreasing lower bound: skipping a send when it
        // has not moved changes no batch a reader releases, only how many
        // Floor steps carry the same value, since a reader releases
        // everything below the floor it last saw, not one packet's worth.
        if sent_floor != Some(floor) {
            if steps.send(Step::Floor(floor)).is_err() {
                return Ok(());
            }
            sent_floor = Some(floor);
        }
    }
    Ok(())
}

/// Replay `steps` to `sink`, in order: a [`Step::Floor`] at once, a
/// [`Step::Batch`] once its job's result is in `results`. A job that finishes
/// out of order waits in a map no larger than the jobs still in flight.
///
/// # Errors
/// The refusal of a job, or of `sink`.
fn drain_flow<E: From<CaptureRefused>>(
    steps: &Receiver<Step>,
    results: &Receiver<(u64, Result<Vec<Received>, CaptureRefused>)>,
    sink: &mut impl FnMut(Flow<'_>) -> Result<(), E>,
) -> Result<(), E> {
    let mut pending: BTreeMap<u64, Result<Vec<Received>, CaptureRefused>> = BTreeMap::new();
    for step in steps {
        match step {
            Step::Floor(receipt) => sink(Flow::Floor(receipt))?,
            Step::Batch(id) => {
                let decoded = loop {
                    if let Some(result) = pending.remove(&id) {
                        break result;
                    }
                    let Ok((got_id, result)) = results.recv() else {
                        return Err(E::from(CaptureRefused::WorkerLost));
                    };
                    pending.insert(got_id, result);
                };
                for (batch, receipt) in decoded.map_err(E::from)? {
                    sink(Flow::Batch(&batch, receipt))?;
                }
            }
        }
    }
    Ok(())
}

/// [`feed_flow`], but a pool of `workers.get()` decode threads decodes the
/// erasure sets an eviction moves out, beside the thread that reads `source`
/// and moves `window`. The pool lives for this whole call, so its cost is
/// paid once, not once per eviction: an eviction is usually a slot's worth of
/// sets, too little work to be worth a thread of its own.
///
/// Every eviction recovers and deshreds independently of every other
/// (`docs/chart.json5`, Recovering: the arena is bounded to one window), so
/// the batches and the floors this sinks, and their order, are the same
/// [`feed_flow`] sinks: only the thread that decodes a batch, and when,
/// differ. One worker decodes inline, on the calling thread, exactly as
/// [`feed_flow`].
///
/// # Errors
/// The refusal of the capture, of a decode worker, or of `sink`.
pub fn feed_flow_parallel<E: From<CaptureRefused> + Send>(
    window: &mut Window,
    source: &mut impl Packets,
    workers: DecodeWorkers,
    sink: &mut (impl FnMut(Flow<'_>) -> Result<(), E> + Send),
) -> Result<(), E> {
    if workers.get() <= 1 {
        return feed_flow(window, source, sink);
    }
    let bound = workers.get().saturating_mul(2);
    let (jobs_tx, jobs_rx) = mpsc::sync_channel::<Job>(bound);
    let jobs_rx = Arc::new(Mutex::new(jobs_rx));
    let (results_tx, results_rx) = mpsc::sync_channel(bound);
    let (steps_tx, steps_rx) = mpsc::sync_channel::<Step>(bound);

    thread::scope(|scope| {
        for _ in 0..workers.get() {
            let jobs_rx = Arc::clone(&jobs_rx);
            let results_tx = results_tx.clone();
            scope.spawn(move || decode_worker(&jobs_rx, &results_tx));
        }
        drop(results_tx);
        let drainer = scope.spawn(move || drain_flow(&steps_rx, &results_rx, sink));

        let dispatched = dispatch_flow(window, source, &jobs_tx, &steps_tx);
        drop(jobs_tx);
        drop(steps_tx);
        let drained = drainer
            .join()
            .unwrap_or_else(|_| Err(CaptureRefused::WorkerLost.into()));
        dispatched.map_err(E::from).and(drained)
    })
}

/// Hand `sink` the entry batches of every slot the window still holds, at the
/// end of the capture.
///
/// # Errors
/// The refusal of the capture, or of `sink`.
pub fn finish_flow<E: From<CaptureRefused>>(
    window: Window,
    sink: &mut impl FnMut(Flow<'_>) -> Result<(), E>,
) -> Result<(), E> {
    finish_flow_parallel(window, DecodeWorkers::SEQUENTIAL, sink)
}

/// [`finish_flow`], but `workers.get()` threads recover the window's erasure
/// sets.
///
/// # Errors
/// The refusal of the capture, or of `sink`.
pub fn finish_flow_parallel<E: From<CaptureRefused>>(
    window: Window,
    workers: DecodeWorkers,
    sink: &mut impl FnMut(Flow<'_>) -> Result<(), E>,
) -> Result<(), E> {
    for (batch, receipt) in window.finish(workers).map_err(E::from)? {
        sink(Flow::Batch(&batch, receipt))?;
    }
    Ok(())
}

/// Every entry batch of the capture at `path`, each with the receipt of the
/// packet that completed it, in the order the machine received them.
///
/// The batches are all held at once, so the memory it uses grows with the
/// capture. A known-answer probe over one small capture reads it here. A run of
/// captures is read with [`stream_batches`].
///
/// # Errors
/// [`CaptureRefused`] when the capture does not read.
pub fn received_batches(path: &Path) -> Result<Vec<Received>, CaptureRefused> {
    let mut all = Vec::new();
    stream_batches(
        &[path.to_path_buf()],
        Distance::default(),
        |batch, receipt| {
            all.push((batch.clone(), receipt));
            Ok::<(), CaptureRefused>(())
        },
    )?;
    Ok(all)
}

/// Every transaction of the batch, read into what it did to the venue, at the
/// batch's slot and receipt.
///
/// # Errors
/// [`CaptureRefused::Parse`] when the batch does not parse.
pub fn observed_in(batch: &Deshredded, receipt: Receipt) -> Result<Vec<Observed>, CaptureRefused> {
    let mut found = Vec::new();
    for entry in parse::entries(&batch.bytes)? {
        for transaction in parse::transactions(&entry?) {
            let transaction = transaction?;
            found.push(Observed {
                slot: batch.slot,
                receipt,
                signature: parse::signature_of(&transaction)?,
                market: market_of(&transaction)?,
            });
        }
    }
    Ok(found)
}
