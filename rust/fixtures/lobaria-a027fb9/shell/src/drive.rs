//! The driver: the step loop over the ports.
//!
//! Concept: This module runs the machine, one event at a time, to completion.
//!
//! `docs/process.md`, step 6. Each event the shell delivers is a step
//! (Harel & Naamad 1996): the loop fires every transition the event and the
//! events it emitted enable, in every region, until none is enabled. Each
//! transition is composed as read, calculate, write (6.2): the read is at
//! most one call to a port, and the calculation is [`machine::apply`]. The
//! price, the clock and the principal are read before the first packet (6.3),
//! because a transition must not query a port after a write starts.
//!
//! `Executing.submit` is the one transition whose port call is a write: the
//! send is its read, because the chart makes the send's failure a target
//! (`Rejected`). Nothing is read after it inside the transition. Between
//! steps the driver reads the chain again: the record of each packet's slot,
//! and the finalized slot. A submission comes back through the chain as
//! shreds, so the run continues for as long as the packet source has packets.

use statechart::fire::{Fired, Firing};
use statechart::Refusal;

use crate::edge::{self, Decoded};
use crate::machine::{self, Event, ExecutingAt, Facts, Kind, Running};
use crate::port::{
    Allocator, ChainRecord, Clock, Grant, Occupant, PacketSource, PriceSource, Signer,
    SubmissionSink,
};
use statechart::edge::Packet;

/// Every port the machine reads or writes.
pub struct Ports<'a> {
    /// Where packets come from.
    pub packets: &'a mut dyn PacketSource,
    /// The chain's record.
    pub chain: &'a dyn ChainRecord,
    /// The SOL/USD price.
    pub prices: &'a dyn PriceSource,
    /// Receipt time.
    pub clock: &'a dyn Clock,
    /// The signing key.
    pub signer: &'a dyn Signer,
    /// Where signed transactions go.
    pub sink: &'a mut dyn SubmissionSink,
    /// Where principal comes from.
    pub allocator: &'a dyn Allocator,
    /// The strategy slot's occupant.
    pub occupant: &'a mut dyn Occupant,
}

/// Concept: This value says whether the price is delivered before or after
/// the packet.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PriceOrder {
    /// The price and the clock are delivered before the packet.
    BeforePacket,
    /// The price and the clock are delivered after the run of the packet.
    AfterPacket,
}

/// Concept: This value is why a run did not finish.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Refused {
    /// The packet source had no packet.
    NoPacket,
    /// A parse at the edge refused.
    Edge(Refusal),
    /// The packet was a coding shred, and the fixed path takes a data shred.
    NotData,
    /// A transition did not fire: a guard refused or its body is owed.
    NotFired(Firing),
}

/// Concept: This value is what a run did.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Run {
    /// The transitions that fired, in order.
    pub fired: Vec<Fired>,
    /// How many events still wait in an inbox.
    pub waiting: usize,
    /// Where every Executing instance ended.
    pub executing: Vec<ExecutingAt>,
}

/// Fire every enabled transition until none is left.
fn complete(
    mut running: Running,
    ports: &mut Ports<'_>,
    fired: &mut Vec<Fired>,
) -> Result<Running, Refused> {
    while let Some(enabled) = running.next() {
        let facts = read(&running, &enabled.kind, ports);
        let (next, firing) = machine::apply(running, enabled, facts);
        match firing {
            Some(Firing::Fired(one)) => fired.push(one),
            Some(other) => return Err(Refused::NotFired(other)),
            None => {}
        }
        running = next;
    }
    Ok(running)
}

/// The one port call a transition reads, if it has one.
fn read(running: &Running, kind: &Kind, ports: &mut Ports<'_>) -> Facts {
    match kind {
        Kind::Observe(_, observed) => Facts::Decision(ports.occupant.observe(observed)),
        Kind::Sign(_, _, decision) => Facts::Signing(
            ports
                .signer
                .sign(decision, running.standing(ports.chain.finalized())),
        ),
        Kind::Submit(_, _, signed) => Facts::Sending(ports.sink.submit(signed)),
        Kind::InstantiateConfirming(_)
        | Kind::InstantiateExecuting(_)
        | Kind::Collect(..)
        | Kind::Confirm(..)
        | Kind::Create(..)
        | Kind::Trade(..)
        | Kind::Pool(..)
        | Kind::Swap(..)
        | Kind::Fund(_)
        | Kind::Accept(..)
        | Kind::Reject(..)
        | Kind::Settle(_) => Facts::Nothing,
    }
}

/// Deliver one event and run the step to completion.
fn step(
    running: Running,
    event: Event,
    ports: &mut Ports<'_>,
    fired: &mut Vec<Fired>,
) -> Result<Running, Refused> {
    let done = complete(running.deliver(event), ports, fired)?;
    Ok(done.end_turn())
}

/// Deliver the events of one packet: the shred, the chain's record of its
/// slot, the principal on the first, the machine's two turns, and the
/// finalized slot.
fn packet_turn(
    mut running: Running,
    packet: &Packet,
    grant: Option<Grant>,
    ports: &mut Ports<'_>,
    fired: &mut Vec<Fired>,
) -> Result<Running, Refused> {
    let Decoded::Data(batch) = edge::decode(packet).map_err(Refused::Edge)? else {
        return Err(Refused::NotData);
    };
    let record = ports.chain.record(batch.slot);
    let mut events = vec![Event::DataShred(batch), Event::ConfirmedBlock(record)];
    if let Some(grant) = grant {
        events.push(Event::Allocation(grant));
    }
    events.extend([Event::Step, Event::Step]);
    for event in events {
        running = step(running, event, ports, fired)?;
    }
    step(
        running,
        Event::WatermarkPassed(ports.chain.finalized()),
        ports,
        fired,
    )
}

/// Drive the packets of the source through every region.
///
/// The run ends when the source has no more packets. The chain's finalized
/// slot is read once more then, so a submission whose window closed while the
/// source was dry is rejected.
pub fn run(ports: &mut Ports<'_>, order: PriceOrder) -> Result<Run, Refused> {
    // Read up front: no port is queried once a transition has written.
    let price = ports.prices.price().map_err(Refused::Edge)?;
    let now = ports.clock.now();
    let grant = ports.allocator.grant();
    let mut packet = ports.packets.next_packet().ok_or(Refused::NoPacket)?;
    let on_time = [Event::PriceTick(price), Event::Clock(now)];
    let mut fired = Vec::new();
    let mut running = Running::boot();
    if order == PriceOrder::BeforePacket {
        for event in on_time.clone() {
            running = step(running, event, ports, &mut fired)?;
        }
    }
    let mut principal = Some(grant);
    loop {
        running = packet_turn(running, &packet, principal.take(), ports, &mut fired)?;
        match ports.packets.next_packet() {
            Some(next) => packet = next,
            None => break,
        }
    }
    running = step(
        running,
        Event::WatermarkPassed(ports.chain.finalized()),
        ports,
        &mut fired,
    )?;
    if order == PriceOrder::AfterPacket {
        for event in on_time {
            running = step(running, event, ports, &mut fired)?;
        }
    }
    Ok(Run {
        fired,
        waiting: running.waiting(),
        executing: running.executing(),
    })
}
