//! The simulate interpreter: the first implementation of the Decision seam.
//!
//! Concept: This module interprets a Decision by filling it against the
//! reserves the replay last observed, and logging the fill.
//!
//! A held token is valued at the reserves of the pool that holds it. On the curve
//! they are the curve's. A graduation replaces them with the pool's seed, and each
//! pool swap with the pool's reserves after it, so a graduated position is marked
//! and settled at the pool and never at the last curve reserves.
//!
//! The replay shows the simulator each observation with [`Simulator::observe`]
//! before `decide` reads it. [`Simulator::fill`] fills a Decision against the
//! reserves last observed: the replay calls it when the Decision lands, one
//! [`Latency`] after it was made, so the reserves the fill reads are those in
//! force then. With [`Latency::INSTANT`] they are the reserves the Decision was
//! made on. A refused Decision fills nothing and changes nothing. The simulator
//! only holds the [`LandDraw`]: the replay draws, because an unlanded Decision
//! is a matter of the strategy's State, and `fill` is never called for it. Every leg it
//! fills is charged the [`ExecutionCost`] of the simulator.

use std::collections::BTreeMap;

use pump_strategy::decision::Decision;
use pump_strategy::interpreter::Interpreter;
use pump_strategy::read;
use pump_strategy::units::{Curve, Lamports, Mint, Receipt, TokenUnits};
use serde::{Deserialize, Serialize};
use statechart::dlmm::{self, Ladder};
use statechart::programs::{Observation, PoolState};
use statechart::units::TokenUnits as CoreTokenUnits;

use crate::book::{Book, Refusal};
use crate::cost::{ExecutionCost, LegCost};
use crate::fill::{self, FillModel, Priced};
use crate::land::LandDraw;
use crate::latency::Latency;
use crate::log::{mint_of, Act, Leg};

/// One whole token, six decimals: pump.fun's own scale
/// (`statechart::units::TokenUnits`'s doc).
const WHOLE_TOKEN: u64 = 1_000_000;

/// The reserves a leg's log records it read: the curve or constant-product
/// pool's own, or — for a Meteora DLMM pool's active bin, which is not a
/// curve — the token/lamport pair one whole token is worth at the bin's
/// fixed price, so the log still reads the price the fill used. `None` when
/// the bin's price does not fit a pair.
fn read_of(priced: Priced) -> Option<Curve> {
    match priced {
        Priced::Curve(curve) => Some(curve),
        Priced::Dlmm(ladder) => {
            let quote = dlmm::value(&ladder, CoreTokenUnits::new(WHOLE_TOKEN)).ok()?;
            Some(Curve {
                virtual_token: TokenUnits::new(WHOLE_TOKEN),
                virtual_sol: Lamports::new(quote.get()),
            })
        }
    }
}

/// Concept: This value is the simulated wallet, and the trade log it wrote.
#[derive(Clone)]
pub struct Simulator {
    model: FillModel,
    latency: Latency,
    land: LandDraw,
    cost: ExecutionCost,
    book: Book,
    reserves: BTreeMap<Mint, Curve>,
    dlmm: BTreeMap<Mint, Ladder>,
    now: Receipt,
    log: Vec<Leg>,
}

/// Concept: This value is what a simulator has done: its wallet, the reserves
/// it last observed, the time it has read to and its trade log. What a run
/// configures, it does not carry: the run that resumes names it again.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Carried {
    book: Book,
    #[serde(with = "crate::pairs")]
    reserves: BTreeMap<Mint, Curve>,
    #[serde(with = "crate::pairs")]
    dlmm: BTreeMap<Mint, Ladder>,
    now: Receipt,
    log: Vec<Leg>,
}

impl Simulator {
    /// What the simulator has done so far.
    #[must_use]
    pub fn carry(&self) -> Carried {
        Carried {
            book: self.book.clone(),
            reserves: self.reserves.clone(),
            dlmm: self.dlmm.clone(),
            now: self.now,
            log: self.log.clone(),
        }
    }

    /// This simulator, its wallet, reserves, clock and log those of `carried`.
    #[must_use]
    pub fn resume(self, carried: Carried) -> Self {
        Self {
            book: carried.book,
            reserves: carried.reserves,
            dlmm: carried.dlmm,
            now: carried.now,
            log: carried.log,
            ..self
        }
    }

    /// A simulator holding only `capital`, filling by `model`, with each
    /// Decision landing one `latency` after it is made, each Decision that
    /// opens a position landing as `land` draws, and each leg charged `cost`
    /// to land.
    #[must_use]
    pub const fn new(
        capital: Lamports,
        model: FillModel,
        latency: Latency,
        land: LandDraw,
        cost: ExecutionCost,
    ) -> Self {
        Self {
            model,
            latency,
            land,
            cost,
            book: Book::new(capital),
            reserves: BTreeMap::new(),
            dlmm: BTreeMap::new(),
            now: Receipt::new(0),
            log: Vec::new(),
        }
    }

    /// Read an observation's reserves and receipt time. The replay calls this
    /// before `decide` reads the same observation.
    ///
    /// A curve trade sets the pair's reserves to the curve's. A graduation sets
    /// them to the pool's seed, and a pool swap to the pool's reserves after
    /// it: a constant-product pool's seed or reserves set the pair's
    /// [`Curve`], and a Meteora DLMM pool's seed or reserves set its active
    /// bin instead, never both for the same pair.
    pub fn observe(&mut self, observation: &Observation) {
        self.now = read::receipt(observation.receipt());
        match observation {
            Observation::CurveTrade(trade) => {
                self.reserves
                    .insert(read::mint(trade.mint_key()), read::curve(trade.reserves()));
            }
            Observation::Graduation(graduation) => {
                self.observe_pool(read::mint(graduation.mint_key()), graduation.seed());
            }
            Observation::AmmSwap(swap) => {
                self.observe_pool(read::mint(swap.mint_key()), swap.reserves());
            }
            Observation::PriceTick(_) | Observation::OwnFill(_) | Observation::Creation(_) => {}
        }
    }

    /// Set the pair's reserves from a pool's state, in whichever shape its
    /// venue carries.
    fn observe_pool(&mut self, mint: Mint, state: PoolState) {
        match state {
            PoolState::ConstantProduct(reserves) => {
                self.reserves.insert(mint, read::pool(reserves));
            }
            PoolState::Bin(price) => {
                self.dlmm.insert(mint, price);
            }
        }
    }

    /// The curve, or constant-product pool, reserves the simulator holds for
    /// the pair. `None` for a pair priced from a Meteora DLMM pool's active
    /// bin instead: read [`Simulator::open_value`] for a pair's value
    /// whichever venue prices it.
    #[must_use]
    pub fn held(&self, mint: Mint) -> Option<Curve> {
        self.reserves.get(&mint).copied()
    }

    /// What a fill against the pair's held reserves reads: the venue that
    /// last moved them, whichever it is.
    fn priced(&self, mint: Mint) -> Option<Priced> {
        self.dlmm
            .get(&mint)
            .map(|price| Priced::Dlmm(*price))
            .or_else(|| self.reserves.get(&mint).map(|curve| Priced::Curve(*curve)))
    }

    /// The delay between a Decision and its fill.
    #[must_use]
    pub const fn latency(&self) -> Latency {
        self.latency
    }

    /// The declared slippage and fee model of a fill.
    #[must_use]
    pub const fn model(&self) -> FillModel {
        self.model
    }

    /// The race each Decision that opens a position enters.
    #[must_use]
    pub const fn land(&self) -> LandDraw {
        self.land
    }

    /// What each leg is charged to land.
    #[must_use]
    pub const fn cost(&self) -> ExecutionCost {
        self.cost
    }

    /// The wallet.
    #[must_use]
    pub const fn book(&self) -> &Book {
        &self.book
    }

    /// The trade log, in fill order.
    #[must_use]
    pub fn log(&self) -> &[Leg] {
        &self.log
    }

    /// The value of the open positions at the last reserves observed, with no
    /// slippage. `None` when a sum does not fit or a position has no reserves.
    #[must_use]
    pub fn open_value(&self) -> Option<Lamports> {
        let mut total: u64 = 0;
        for (mint, held) in self.book.open() {
            let priced = self.priced(*mint)?;
            let value = fill::mark(priced, held.tokens)?;
            total = total.checked_add(value.get())?;
        }
        Some(Lamports::new(total))
    }
}

impl Simulator {
    /// Fill `decision`, made at `decided` and landing at `landed`, against the
    /// reserves last observed. The caller has shown the simulator every
    /// observation received at or before `landed`, and none after it.
    ///
    /// # Errors
    /// The [`Refusal`] when the reserves of the pair were never observed or the
    /// wallet refuses the fill.
    pub fn fill(
        &mut self,
        decision: Decision,
        decided: Receipt,
        landed: Receipt,
    ) -> Result<Leg, Refusal> {
        let priced = self.priced(mint_of(decision)).ok_or(Refusal::NoReserves)?;
        let read = read_of(priced).ok_or(Refusal::Unfillable)?;
        let charge = self.cost.per_leg().ok_or(Refusal::Unfillable)?;
        let (book, flows) = match decision {
            Decision::Enter { mint, size } => {
                self.book.buy(mint, size, priced, self.model, charge)?
            }
            Decision::Trim { mint, size } | Decision::Exit { mint, size, .. } => {
                self.book.sell(mint, size, priced, self.model, charge)?
            }
        };
        let leg = Leg {
            at: self.now,
            decided,
            landed,
            read,
            act: Act::Decided(decision),
            flows,
            cost: charge,
        };
        self.book = book;
        self.log.push(leg);
        Ok(leg)
    }
}

impl Interpreter for Simulator {
    type Outcome = Result<Leg, Refusal>;

    /// Fill the Decision at once, at the reserves last observed: the instant
    /// fill, whatever the simulator's latency.
    fn interpret(&mut self, decision: Decision) -> Self::Outcome {
        self.fill(decision, self.now, self.now)
    }
}

impl Simulator {
    /// Sell the whole open notional of every position still open, at the last
    /// reserves observed, and log each sale as a [`Act::Settled`] leg. A
    /// replay calls this once, when its stream has ended.
    ///
    /// # Errors
    /// The pair and the refusal of the first sale the book refuses. Sales before
    /// it stay in the log.
    pub fn settle(&mut self) -> Result<usize, (Mint, Refusal)> {
        let open: Vec<(Mint, Lamports)> = self
            .book
            .open()
            .map(|(mint, held)| (*mint, held.notional))
            .collect();
        for (mint, size) in &open {
            let charge: LegCost = self.cost.per_leg().ok_or((*mint, Refusal::Unfillable))?;
            let priced = self.priced(*mint).ok_or((*mint, Refusal::NoReserves))?;
            let read = read_of(priced).ok_or((*mint, Refusal::Unfillable))?;
            let (book, flows) = self
                .book
                .sell(*mint, *size, priced, self.model, charge)
                .map_err(|refusal| (*mint, refusal))?;
            self.book = book;
            self.log.push(Leg {
                at: self.now,
                decided: self.now,
                landed: self.now,
                read,
                act: Act::Settled {
                    mint: *mint,
                    size: *size,
                },
                flows,
                cost: charge,
            });
        }
        Ok(open.len())
    }
}
