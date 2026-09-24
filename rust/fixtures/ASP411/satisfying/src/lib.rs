// ASP411 satisfied: no two arms are redundant. Either the bodies differ, or
// the token-identical bodies capture their payload through different enum
// variant paths — so the values may have different types and the arms cannot
// collapse into one `A | B => body` (E0409).

pub enum Signal {
    Start,
    Resume,
    Stop,
}

pub fn handle(signal: Signal, count: i32) -> i32 {
    match signal {
        Signal::Start => count + advance(count),
        Signal::Resume => count - advance(count),
        Signal::Stop => count,
    }
}

fn advance(count: i32) -> i32 {
    count * 2
}

// The lobaria shape: two tuple variants of different inner types, each with
// its own inherent `header`. `shred` binds a DataShred in one arm and a
// CodingShred in the other, so `Shred::Data(shred) | Shred::Coding(shred)`
// would fail to compile (E0409). The arms are typed per-variant dispatch,
// not a redundant state.

pub struct DataShred {
    pub index: u32,
}

impl DataShred {
    pub const fn header(&self) -> u32 {
        self.index
    }
}

pub struct CodingShred {
    pub position: u16,
}

impl CodingShred {
    pub const fn header(&self) -> u32 {
        self.position as u32
    }
}

pub enum Shred {
    Data(DataShred),
    Coding(CodingShred),
}

impl Shred {
    pub const fn header(&self) -> u32 {
        match self {
            Self::Data(shred) => shred.header(),
            Self::Coding(shred) => shred.header(),
        }
    }
}
