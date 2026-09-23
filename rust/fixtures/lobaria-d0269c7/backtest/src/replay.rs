//! The replay: observations through `decide` and the simulate interpreter.
//!
//! Concept: This module is the loop that reads each observation of a stream,
//! lets the simulator observe it, gives it to the one `decide` core, and
//! interprets what `decide` emits. A [`Replay`] takes the observations one at a
//! time; [`replay`] runs it over a corpus.
//!
//! A Decision does not fill where it is made. It lands one
//! [`Latency`](crate::latency::Latency) later, and fills against the reserves in
//! force then: the last observation received at or before that moment. The
//! replay holds each Decision [`InFlight`] until an observation shows that
//! moment has passed, and fills them in the order they were made. A Decision
//! still in flight when the stream ends never lands: the run reports it and does
//! not fill it. With [`Latency::INSTANT`](crate::latency::Latency::INSTANT) a
//! Decision lands on its own observation.
//!
//! An Enter is a race. When it reaches its landing moment the replay draws
//! against the [`LandProbability`](crate::land::LandProbability) of the
//! simulator: an Enter that does not land fills nothing and opens no position,
//! and is rolled back and voids the Decisions in flight on its pair exactly as a
//! refused Enter does. It has no [`Record`], for nothing was interpreted. A Trim
//! or an Exit sells a position already won, and the strategy has no retry for
//! it, so it always lands. See `docs/land-probability.md`.
//!
//! The shell keeps one State for each pair it sees, as the strategy's core
//! asks: a quote goes to every State, and a trade or a graduation goes to the
//! State of its pair. A pair's State begins at the quote last read. When the
//! simulator refuses an Enter, the position is rolled back to Watching: the
//! core had already moved to Holding, and nothing was bought. A refused Trim
//! or Exit cannot be rolled back, and stops the replay. A refused Enter also voids
//! the Decisions made on that pair while it was in flight: each is recorded as
//! refused for holding nothing.
//!
//! Each Decision the replay interprets is written as a [`Record`], the one
//! shape of `pump_strategy::record`: the Decision with its outcome, a fill or a
//! refusal. The settlement of a position still open is not a Decision and has
//! no such record. A [`Run`] is not settled unless [`Run::settle`] is called:
//! its realized PnL is then only what the strategy closed, and the positions
//! still open are the unrealized PnL of its [`Summary`]. Each closed round
//! trip, a settled one too, has a
//! [`Trade`](pump_strategy::record::Trade) of the same module, from
//! [`Run::trades`].

use std::collections::{BTreeMap, VecDeque};

use pump_strategy::decide::decide;
use pump_strategy::decision::Decision;
use pump_strategy::read;
use pump_strategy::record::{Outcome, Record, Trade};
use pump_strategy::state::{Position, SolPrice, State};
use pump_strategy::units::{Curve, Lamports, Mint, Receipt, Since, TokenUnits};
use serde::{Deserialize, Serialize};
use statechart::programs::Observation;

use crate::book::Refusal;
use crate::corpus::{pair_of, Corpus};
use crate::cost::LegCost;
use crate::log::{self, mint_of, Leg};
use crate::simulate::Simulator;
use crate::trajectory::{self, TrajectoryRow};
use crate::units::SignedLamports;

/// Concept: This value is a Decision the simulator refused.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Refused {
    /// The receipt time of the observation that produced the Decision.
    pub at: Receipt,
    /// The Decision.
    pub decision: Decision,
    /// Why it was refused.
    pub refusal: Refusal,
}

/// Concept: This value is an Enter that lost its race: it did not land.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Unlanded {
    /// The receipt time of the observation that produced the Decision.
    pub at: Receipt,
    /// The Decision.
    pub decision: Decision,
}

/// Concept: This value is a Decision that was made and has not yet landed.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct InFlight {
    /// The receipt time of the observation the Decision was made on.
    pub decided: Receipt,
    /// The moment the Decision lands.
    pub landed: Receipt,
    /// The Decision.
    pub decision: Decision,
}

/// Concept: This value is why a replay stopped.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReplayError {
    /// A Trim or an Exit was refused: the position cannot be rolled back.
    Unrecoverable(Refused),
    /// The sale that settles an open position at the end of the stream was
    /// refused.
    Unsettled {
        /// The pair.
        mint: Mint,
        /// Why it was refused.
        refusal: Refusal,
    },
}

impl std::fmt::Display for ReplayError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Unrecoverable(r) => write!(
                f,
                "a {:?} was refused ({:?}) at receipt {}",
                r.decision,
                r.refusal,
                r.at.instant().get()
            ),
            Self::Unsettled { refusal, .. } => {
                write!(f, "an open position was not settled ({refusal:?})")
            }
        }
    }
}

impl std::error::Error for ReplayError {}

/// Concept: This value is a finished replay.
pub struct Run {
    /// The simulator, with its wallet and trade log.
    pub simulator: Simulator,
    /// The State of each pair at the end.
    pub states: BTreeMap<Mint, State>,
    /// Every Enter the simulator refused, in order.
    pub refused: Vec<Refused>,
    /// Every Decision the replay interpreted with its outcome, in the order
    /// they landed.
    pub records: Vec<Record>,
    /// Every Decision still in flight when the stream ended: it never landed,
    /// and nothing was filled for it.
    pub in_flight: Vec<InFlight>,
    /// Every Enter that reached its landing moment and won its race.
    pub landed: usize,
    /// Every Enter that reached its landing moment and lost its race, in order.
    pub unlanded: Vec<Unlanded>,
    /// The receipt time each position still open opened at, for
    /// [`Run::settle`] to date the rows it writes to the position-history log.
    entries: BTreeMap<Mint, Receipt>,
    /// The position-history rows [`Run::settle`] wrote for the positions it
    /// closed. Empty unless `settle` was called.
    pub settled_history: Vec<TrajectoryRow>,
}

/// Concept: This value is the shell's State for each pair, and the quote last
/// read.
#[derive(Clone, Serialize, Deserialize)]
struct Pairs {
    quote: SolPrice,
    #[serde(with = "crate::pairs")]
    states: BTreeMap<Mint, State>,
}

impl Pairs {
    /// Give the observation to the State it belongs to, and collect the
    /// Decisions it makes. A trade or a graduation is one pair's, so it makes
    /// zero or one Decision. A tick goes to every State, and each held pair
    /// past the max-hold horizon closes on it, so a tick makes zero or more.
    fn route(&mut self, observation: &Observation) -> Vec<Decision> {
        match observation {
            Observation::PriceTick(tick) => {
                self.quote = SolPrice::Quoted(read::quote(tick));
                self.states
                    .values_mut()
                    .filter_map(|state| decide(observation, state))
                    .collect()
            }
            Observation::CurveTrade(trade) => self
                .pair(read::mint(trade.mint_key()), observation)
                .into_iter()
                .collect(),
            Observation::Graduation(graduation) => self
                .pair(read::mint(graduation.mint_key()), observation)
                .into_iter()
                .collect(),
            Observation::AmmSwap(_) | Observation::OwnFill(_) | Observation::Creation(_) => {
                Vec::new()
            }
        }
    }

    /// Give the observation to the State of `mint`, made at the quote last
    /// read when the pair is new.
    fn pair(&mut self, mint: Mint, observation: &Observation) -> Option<Decision> {
        let quote = self.quote;
        let state = self.states.entry(mint).or_insert(State {
            quote,
            position: Position::Watching,
        });
        decide(observation, state)
    }

    /// Undo an Enter the simulator refused.
    fn roll_back(&mut self, mint: Mint) {
        if let Some(state) = self.states.get_mut(&mint) {
            state.position = Position::Watching;
        }
    }
}

/// The record of a Decision made at `at` and the outcome the simulator gave.
fn record_of(at: Receipt, decision: Decision, outcome: &Result<Leg, Refusal>) -> Record {
    Record {
        at,
        decision,
        outcome: match outcome {
            Ok(leg) => Outcome::Filled(leg.flows),
            Err(refusal) => Outcome::Refused(*refusal),
        },
    }
}

/// The tokens `book` holds open for `mint`, when it holds a position there.
fn open_tokens(book: &crate::book::Book, mint: Mint) -> Option<TokenUnits> {
    book.open()
        .find_map(|(m, o)| (*m == mint).then_some(o.tokens))
}

/// Concept: This value is a replay under way, as a value that carries from one
/// run to the next: the State of each pair, the simulator, the Decisions in
/// flight and what the replay has written.
#[derive(Clone, Serialize, Deserialize)]
pub struct Carried {
    pairs: Pairs,
    simulator: crate::simulate::Carried,
    in_flight: Vec<InFlight>,
    refused: Vec<Refused>,
    records: Vec<Record>,
    landed: usize,
    unlanded: Vec<Unlanded>,
    #[serde(with = "crate::pairs")]
    entries: BTreeMap<Mint, Receipt>,
}

/// Concept: This value is a replay under way: the shell's State of each pair,
/// the simulator, and what the replay has written so far.
///
/// The replay takes one observation at a time and keeps none of them, so the
/// memory it holds does not grow with the length of the stream.
#[derive(Clone)]
pub struct Replay {
    pairs: Pairs,
    simulator: Simulator,
    in_flight: VecDeque<InFlight>,
    refused: Vec<Refused>,
    records: Vec<Record>,
    landed: usize,
    unlanded: Vec<Unlanded>,
    /// The receipt time each position still open opened at.
    entries: BTreeMap<Mint, Receipt>,
    /// The position-history rows [`Replay::step`] wrote since the last
    /// [`Replay::drain_history`], not yet read: never more than the rows of
    /// one observation, so this does not grow with the length of the stream.
    history: Vec<TrajectoryRow>,
}

impl Replay {
    /// The replay as it stands, as a value that [`Replay::resume`] takes back.
    #[must_use]
    pub fn carry(&self) -> Carried {
        Carried {
            pairs: self.pairs.clone(),
            simulator: self.simulator.carry(),
            in_flight: self.in_flight.iter().copied().collect(),
            refused: self.refused.clone(),
            records: self.records.clone(),
            landed: self.landed,
            unlanded: self.unlanded.clone(),
            entries: self.entries.clone(),
        }
    }

    /// The replay `carried` holds, into `simulator`, which names what the run
    /// configures: its fill model, latency, race and cost.
    #[must_use]
    pub fn resume(simulator: Simulator, carried: Carried) -> Self {
        Self {
            pairs: carried.pairs,
            simulator: simulator.resume(carried.simulator),
            in_flight: carried.in_flight.into(),
            refused: carried.refused,
            records: carried.records,
            landed: carried.landed,
            unlanded: carried.unlanded,
            entries: carried.entries,
            history: Vec::new(),
        }
    }

    /// A replay that has read nothing, into `simulator`.
    #[must_use]
    pub const fn new(simulator: Simulator) -> Self {
        Self {
            pairs: Pairs {
                quote: SolPrice::Unquoted,
                states: BTreeMap::new(),
            },
            simulator,
            in_flight: VecDeque::new(),
            refused: Vec::new(),
            records: Vec::new(),
            landed: 0,
            unlanded: Vec::new(),
            entries: BTreeMap::new(),
            history: Vec::new(),
        }
    }

    /// Read the next observation: fill the Decisions that landed before it,
    /// let the simulator see it, give it to `decide`, and send the Decision it
    /// emits in flight. A Decision that lands on this observation fills now.
    ///
    /// # Errors
    /// [`ReplayError`] when a Trim or an Exit is refused.
    pub fn step(&mut self, observation: &Observation) -> Result<(), ReplayError> {
        let at = observation.receipt();
        self.land(|landed| landed < at)?;
        self.simulator.observe(observation);
        self.mark_reserves(observation, at);
        let decisions = self.pairs.route(observation);
        if !decisions.is_empty() {
            let landed = self.simulator.latency().landing(at);
            for decision in decisions {
                self.in_flight.push_back(InFlight {
                    decided: at,
                    landed,
                    decision,
                });
            }
        }
        self.land(|landed| landed <= at)
    }

    /// Fill the Decisions in flight, oldest first, while `due` holds of the
    /// moment the oldest lands.
    fn land(&mut self, due: impl Fn(Receipt) -> bool) -> Result<(), ReplayError> {
        while let Some(flight) = self.in_flight.front().copied().filter(|f| due(f.landed)) {
            self.in_flight.pop_front();
            self.fill(flight)?;
        }
        Ok(())
    }

    /// Whether the Enter of `flight` wins its race. Any other Decision lands.
    /// The ordinal of a race is the count of races run before it, so the draws
    /// do not depend on the outcome of the fills.
    fn wins(&mut self, decision: Decision) -> bool {
        if !matches!(decision, Decision::Enter { .. }) {
            return true;
        }
        let ordinal = self.landed.saturating_add(self.unlanded.len());
        let ordinal = u64::try_from(ordinal).unwrap_or(u64::MAX);
        let won = self.simulator.land().lands(ordinal);
        if won {
            self.landed = self.landed.saturating_add(1);
        }
        won
    }

    /// Drop an Enter that lost its race: the position it was to open is rolled
    /// back, and the Decisions made while it was in flight are voided.
    fn lose(&mut self, flight: InFlight) {
        let mint = mint_of(flight.decision);
        self.pairs.roll_back(mint);
        self.void(mint);
        self.unlanded.push(Unlanded {
            at: flight.decided,
            decision: flight.decision,
        });
    }

    /// Fill one Decision and write its record. A refused Enter is rolled back.
    /// An Enter that loses its race is dropped, with no record.
    fn fill(&mut self, flight: InFlight) -> Result<(), ReplayError> {
        let InFlight {
            decided,
            landed,
            decision,
        } = flight;
        if !self.wins(decision) {
            self.lose(flight);
            return Ok(());
        }
        let outcome = self.simulator.fill(decision, decided, landed);
        if let Ok(leg) = &outcome {
            self.track(decision, leg);
        }
        self.records.push(record_of(decided, decision, &outcome));
        let Err(refusal) = outcome else {
            return Ok(());
        };
        let miss = Refused {
            at: decided,
            decision,
            refusal,
        };
        match decision {
            Decision::Enter { mint, .. } => {
                self.pairs.roll_back(mint);
                self.void(mint);
                self.refused.push(miss);
                Ok(())
            }
            Decision::Trim { .. } | Decision::Exit { .. } => Err(ReplayError::Unrecoverable(miss)),
        }
    }

    /// Void the Decisions in flight on `mint`, made while the position its
    /// refused Enter was to open still looked open.
    fn void(&mut self, mint: Mint) {
        let (voided, kept): (VecDeque<InFlight>, VecDeque<InFlight>) = self
            .in_flight
            .drain(..)
            .partition(|f| mint_of(f.decision) == mint);
        self.in_flight = kept;
        self.records.extend(voided.into_iter().map(|f| Record {
            at: f.decided,
            decision: f.decision,
            outcome: Outcome::Refused(Refusal::NothingHeld),
        }));
    }

    /// Record the position-history rows a fill produces: the pair opens, marks
    /// at its post-fill reserves, or closes, marking with the round trip's real
    /// earnings instead of a hypothetical value. Called after every leg the
    /// simulator actually fills.
    fn track(&mut self, decision: Decision, leg: &Leg) {
        let mint = mint_of(decision);
        if let Decision::Enter { .. } = decision {
            self.entries.insert(mint, leg.landed);
        }
        let Some(entered_at) = self.entries.get(&mint).copied() else {
            return;
        };
        match open_tokens(self.simulator.book(), mint) {
            Some(tokens) => self.push_mark(mint, leg.landed, entered_at, leg.read, tokens),
            None => {
                self.entries.remove(&mint);
                if let Some(closed) = log::closed(self.simulator.log())
                    .and_then(|trips| trips.into_iter().rev().find(|c| c.trade.mint == mint))
                {
                    self.history.push(TrajectoryRow {
                        mint,
                        at: leg.landed,
                        entered_at,
                        holding_ns: leg.landed.since(entered_at),
                        exit_value_lamports: closed.trade.earnings,
                    });
                }
            }
        }
    }

    /// Record a hypothetical position-history row: `tokens` valued at `curve`,
    /// net of the run's execution cost and scaled by its land probability.
    /// Nothing is recorded when the fill or a sum does not fit.
    fn push_mark(
        &mut self,
        mint: Mint,
        at: Receipt,
        entered_at: Receipt,
        curve: Curve,
        tokens: TokenUnits,
    ) {
        let Some(cost) = self.simulator.cost().per_leg() else {
            return;
        };
        let probability = self.simulator.land().probability;
        let Some(exit_value_lamports) = trajectory::executable_exit_value(
            curve,
            tokens,
            self.simulator.model(),
            cost,
            probability,
        ) else {
            return;
        };
        self.history.push(TrajectoryRow {
            mint,
            at,
            entered_at,
            holding_ns: at.since(entered_at),
            exit_value_lamports,
        });
    }

    /// Record a position-history row for the pair `observation` moved the
    /// reserves of, when it holds an open position: a curve trade, a
    /// graduation or a pool swap. A price tick moves no pair's reserves and
    /// marks nothing.
    fn mark_reserves(&mut self, observation: &Observation, at: Receipt) {
        let Some(mint) = pair_of(observation) else {
            return;
        };
        let Some(entered_at) = self.entries.get(&mint).copied() else {
            return;
        };
        let Some(tokens) = open_tokens(self.simulator.book(), mint) else {
            return;
        };
        let Some(curve) = self.simulator.held(mint) else {
            return;
        };
        self.push_mark(mint, at, entered_at, curve, tokens);
    }

    /// The position-history rows recorded since the last call, drained: never
    /// more than the rows of one observation, so the caller can write them out
    /// and hold none of them.
    pub fn drain_history(&mut self) -> Vec<TrajectoryRow> {
        std::mem::take(&mut self.history)
    }

    /// The replay as it stands, as a finished [`Run`].
    #[must_use]
    pub fn finish(self) -> Run {
        Run {
            simulator: self.simulator,
            states: self.pairs.states,
            refused: self.refused,
            records: self.records,
            in_flight: self.in_flight.into(),
            landed: self.landed,
            unlanded: self.unlanded,
            entries: self.entries,
            settled_history: Vec::new(),
        }
    }
}

/// Replay the corpus through `decide` into `simulator`.
///
/// # Errors
/// [`ReplayError`] when a Trim or an Exit is refused.
pub fn replay(corpus: &Corpus, simulator: Simulator) -> Result<Run, ReplayError> {
    let mut replay = Replay::new(simulator);
    for observation in corpus.events() {
        replay.step(observation)?;
    }
    Ok(replay.finish())
}

impl Run {
    /// Settle every position still open when the stream ends: the simulator
    /// sells each at the last reserves observed, so that its PnL is realized.
    /// The strategy decides nothing of the settlement.
    ///
    /// # Errors
    /// [`ReplayError::Unsettled`] when a settlement is refused.
    pub fn settle(mut self) -> Result<Self, ReplayError> {
        let opening: Vec<(Mint, Receipt)> =
            self.entries.iter().map(|(mint, at)| (*mint, *at)).collect();
        self.simulator
            .settle()
            .map_err(|(mint, refusal)| ReplayError::Unsettled { mint, refusal })?;
        if let Some(closed) = log::closed(self.simulator.log()) {
            for (mint, entered_at) in opening {
                if let Some(trade) = closed.iter().find(|c| c.trade.mint == mint) {
                    self.settled_history.push(TrajectoryRow {
                        mint,
                        at: trade.trade.closed_at,
                        entered_at,
                        holding_ns: trade.trade.closed_at.since(entered_at),
                        exit_value_lamports: trade.trade.earnings,
                    });
                }
            }
        }
        Ok(self)
    }
}

/// Replay the corpus, then settle every position still open when it ends: the
/// simulator sells each at the last reserves observed, so that its PnL is
/// realized. The strategy decides nothing of the settlement.
///
/// # Errors
/// [`ReplayError`] when a Trim or an Exit is refused, or a settlement is.
pub fn replay_settled(corpus: &Corpus, simulator: Simulator) -> Result<Run, ReplayError> {
    replay(corpus, simulator)?.settle()
}

/// Concept: This value is the figures of a finished replay.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Summary {
    /// The legs of the trade log.
    pub legs: usize,
    /// The closed round trips.
    pub trades: usize,
    /// The Enters the simulator refused.
    pub refused: usize,
    /// The Decisions still in flight when the stream ended: never filled.
    pub in_flight: usize,
    /// The Enters that reached their landing moment: `landed` and `unlanded`.
    pub submitted: usize,
    /// The Enters that won their race and landed.
    pub landed: usize,
    /// The Enters that lost their race: no fill, no position.
    pub unlanded: usize,
    /// The positions open at the end.
    pub open_positions: usize,
    /// The realized PnL of the round trips the strategy closed, net of the
    /// execution cost of their legs. A position still open at the end is not in it.
    pub realized: SignedLamports,
    /// The unrealized PnL of the positions still open at the end: their value
    /// at the last reserves observed, less what they cost net of their Trims,
    /// and net of the execution cost of their legs.
    pub unrealized: SignedLamports,
    /// What every leg was charged to land, by part. Its total is already out of
    /// the PnL of the summary.
    pub execution_cost: LegCost,
    /// The sum of every flow of every leg; zero when SOL is conserved.
    pub imbalance: SignedLamports,
    /// The cash at the end.
    pub cash: Lamports,
    /// The open positions at the last reserves observed.
    pub open_value: Lamports,
}

impl Run {
    /// The per-trade records of the run: one for each closed round trip, in the
    /// order they closed. Their earnings sum to the realized PnL of the
    /// [`Summary`]. `None` when a sum does not fit.
    #[must_use]
    pub fn trades(&self) -> Option<Vec<Trade>> {
        log::trips(self.simulator.log())
    }

    /// The closed round trips of the run, each with what its legs were charged
    /// to land, in the order they closed. `None` when a sum does not fit.
    #[must_use]
    pub fn closed(&self) -> Option<Vec<log::Closed>> {
        log::closed(self.simulator.log())
    }

    /// The unrealized PnL of the positions still open: what they are worth at
    /// the last reserves observed, with the net flow their legs moved so far.
    /// Zero when nothing is open. `None` when a sum does not fit.
    fn unrealized(&self) -> Option<SignedLamports> {
        let value = SignedLamports::inflow(self.simulator.open_value()?)?;
        value.checked_add(log::open_flow(self.simulator.log())?)
    }

    /// The figures of the run. `None` when a sum does not fit.
    #[must_use]
    pub fn summary(&self) -> Option<Summary> {
        let log = self.simulator.log();
        Some(Summary {
            legs: log.len(),
            trades: log::trips(log)?.len(),
            refused: self.refused.len(),
            in_flight: self.in_flight.len(),
            submitted: self.landed.checked_add(self.unlanded.len())?,
            landed: self.landed,
            unlanded: self.unlanded.len(),
            open_positions: self.simulator.book().open().count(),
            realized: log::realized(log)?,
            unrealized: self.unrealized()?,
            execution_cost: log::execution_cost(log)?,
            imbalance: log::imbalance(log)?,
            cash: self.simulator.book().cash(),
            open_value: self.simulator.open_value()?,
        })
    }
}

#[cfg(test)]
mod tests {
    use chart::json5::{self, Value};
    use pump_strategy::decision::Cause;
    use pump_strategy::units::{Bps, Nanos};

    use super::*;
    use crate::corpus::event;
    use crate::cost::ExecutionCost;
    use crate::fill::FillModel;
    use crate::land::{LandDraw, LandProbability};
    use crate::latency::Latency;

    /// The corpus of a JSON5 array of events, in the notation of `corpus::event`.
    fn corpus(text: &str) -> Corpus {
        let Value::Array(items) = json5::read(text).unwrap() else {
            panic!("an array of events");
        };
        let events = items.iter().map(|v| event(v, "events").unwrap()).collect();
        Corpus::new(events).unwrap()
    }

    fn simulator(capital: u64, latency: Latency) -> Simulator {
        Simulator::new(
            Lamports::new(capital),
            FillModel { fee: Bps::new(100) },
            latency,
            LandDraw::ALWAYS,
            ExecutionCost::NONE,
        )
    }

    /// The entry gate is met at 1 ms, so an Enter lands at 407 ms. The price
    /// falls under the hard stop at 200 ms, so an Exit is made while the Enter
    /// is in flight. The wallet cannot pay for the Enter.
    const ENTER_THEN_STOP: &str = "[
        { at: 0, quote: 100000000 },
        { at: 1000000, curve: { mint: 1, vsol: 100000000000, vtok: 1000000000000000 } },
        { at: 200000000, curve: { mint: 1, vsol: 80000000000, vtok: 1000000000000000 } },
        { at: 500000000, curve: { mint: 1, vsol: 80000000000, vtok: 1000000000000000 } },
    ]";

    #[test]
    fn a_refused_enter_voids_the_exit_made_while_it_was_in_flight() {
        let run = replay(
            &corpus(ENTER_THEN_STOP),
            simulator(50_000_000, Latency::FALCON),
        )
        .unwrap();
        let outcomes: Vec<Outcome> = run.records.iter().map(|r| r.outcome).collect();
        assert_eq!(
            outcomes,
            [
                Outcome::Refused(Refusal::InsufficientCapital),
                Outcome::Refused(Refusal::NothingHeld),
            ]
        );
        assert_eq!(run.refused.len(), 1);
        assert!(run.in_flight.is_empty());
    }

    fn simulator_landing(capital: u64, latency: Latency, probability: &str) -> Simulator {
        Simulator::new(
            Lamports::new(capital),
            FillModel { fee: Bps::new(100) },
            latency,
            LandDraw::configured(LandProbability::parse(probability).ok(), None),
            ExecutionCost::NONE,
        )
    }

    #[test]
    fn an_enter_that_does_not_land_leaves_no_fill_and_no_position() {
        let run = replay(
            &corpus(ENTER_THEN_STOP),
            simulator_landing(10_000_000_000, Latency::INSTANT, "0"),
        )
        .unwrap();
        assert!(run.simulator.log().is_empty());
        assert!(run.records.is_empty());
        assert_eq!(run.unlanded.len(), 1);
        let summary = run.summary().unwrap();
        assert_eq!(
            (summary.submitted, summary.landed, summary.unlanded),
            (1, 0, 1)
        );
        assert_eq!(summary.open_positions, 0);
        assert_eq!(summary.cash.get(), 10_000_000_000);
    }

    #[test]
    fn the_exit_made_while_an_unlanded_enter_was_in_flight_is_voided() {
        let run = replay(
            &corpus(ENTER_THEN_STOP),
            simulator_landing(10_000_000_000, Latency::FALCON, "0"),
        )
        .unwrap();
        let outcomes: Vec<Outcome> = run.records.iter().map(|r| r.outcome).collect();
        assert_eq!(outcomes, [Outcome::Refused(Refusal::NothingHeld)]);
        assert!(run.simulator.log().is_empty());
        assert_eq!(run.unlanded.len(), 1);
    }

    #[test]
    fn an_exit_always_lands_and_is_not_a_race() {
        let run = replay(
            &corpus(ENTER_THEN_STOP),
            simulator_landing(10_000_000_000, Latency::INSTANT, "1"),
        )
        .unwrap();
        let summary = run.summary().unwrap();
        assert_eq!(summary.legs, 2);
        assert_eq!((summary.submitted, summary.landed), (1, 1));
    }

    #[test]
    fn a_decision_in_flight_when_the_stream_ends_is_reported_not_filled() {
        let ends_at_the_entry = "[
            { at: 0, quote: 100000000 },
            { at: 1000000, curve: { mint: 1, vsol: 100000000000, vtok: 1000000000000000 } },
            { at: 200000000, curve: { mint: 1, vsol: 100000000000, vtok: 1000000000000000 } },
        ]";
        let run = replay(
            &corpus(ends_at_the_entry),
            simulator(10_000_000_000, Latency::FALCON),
        )
        .unwrap();
        assert!(run.simulator.log().is_empty());
        assert_eq!(run.in_flight.len(), 1);
        assert_eq!(run.summary().unwrap().in_flight, 1);
    }

    #[test]
    fn an_instant_decision_fills_on_its_own_observation() {
        let run = replay(
            &corpus(ENTER_THEN_STOP),
            simulator(10_000_000_000, Latency::INSTANT),
        )
        .unwrap();
        assert_eq!(run.simulator.log().len(), 2);
        assert!(run.in_flight.is_empty());
    }

    /// The position-history rows [`Replay::step`] produces for the same
    /// Enter-then-Exit round trip: an entry row at zero holding time, and a
    /// close row whose value agrees with the round trip's real earnings.
    #[test]
    fn the_history_log_covers_entry_and_close() {
        let mut replay = Replay::new(simulator(10_000_000_000, Latency::INSTANT));
        let mut rows = Vec::new();
        for observation in corpus(ENTER_THEN_STOP).events() {
            replay.step(observation).unwrap();
            rows.extend(replay.drain_history());
        }
        let entry = rows.first().expect("an entry row");
        assert_eq!(entry.holding_ns, Nanos::new(0));

        let run = replay.finish();
        let trade = log::closed(run.simulator.log())
            .unwrap()
            .into_iter()
            .next()
            .expect("one closed round trip");
        let close = rows.last().expect("a close row");
        assert_eq!(close.exit_value_lamports, trade.trade.earnings);
        assert_eq!(close.at, trade.trade.closed_at);
    }

    /// A token that goes silent after entry — no more curve trades, only
    /// SOL/USD ticks — still closes. Entered at receipt 1,000,000; the tick at
    /// 28,800,001,000,001 is age 28,800,000,000,001 >= the 28,800 s max hold,
    /// so it force-exits the held position on elapsed time alone. Before the
    /// tick carried a Decision, the replay discarded it and the position never
    /// closed.
    #[test]
    fn a_silent_token_is_closed_by_a_max_hold_tick() {
        let silent_then_tick = "[
            { at: 0, quote: 100000000 },
            { at: 1000000, curve: { mint: 1, vsol: 100000000000, vtok: 1000000000000000 } },
            { at: 28800001000001, quote: 100000000 },
        ]";
        let run = replay(
            &corpus(silent_then_tick),
            simulator(10_000_000_000, Latency::INSTANT),
        )
        .unwrap();
        let closed = run.records.iter().any(|r| {
            matches!(
                (r.decision, r.outcome),
                (
                    Decision::Exit {
                        cause: Cause::MaxHold,
                        ..
                    },
                    Outcome::Filled(_)
                )
            )
        });
        assert!(closed, "a tick past the horizon closes the held position");
    }
}
