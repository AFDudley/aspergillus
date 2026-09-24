// ASP411: match arms whose bodies structurally duplicate an earlier arm's
// and that can actually collapse into a single `A | B => body` arm — the
// bindings either agree on type or there are none. Reported at the later
// duplicate arm.

pub enum Signal {
    Start,
    Resume,
    Stop,
}

// A no-binding identical-arm pair: `Signal::Start` and `Signal::Resume`
// capture nothing, so `Signal::Start | Signal::Resume => …` compiles. The
// second arm is redundant.
pub fn handle(signal: Signal, count: i32) -> i32 {
    match signal {
        Signal::Start => count + advance(count),
        Signal::Resume => count + advance(count),
        Signal::Stop => count,
    }
}

pub enum Packet {
    Data(u32),
    Coding(u32),
}

// A same-variant-path pair: both arms capture `n` through `Packet::Data`, so
// the merge `(Packet::Data(n), true) | (Packet::Data(n), false) => …` binds
// `n` to one type and compiles. The second arm is redundant.
pub fn parity(packet: Packet, active: bool) -> u32 {
    match (packet, active) {
        (Packet::Data(n), true) => n.count_ones() + 1,
        (Packet::Data(n), false) => n.count_ones() + 1,
        (Packet::Coding(n), _) => n.count_ones(),
    }
}

fn advance(count: i32) -> i32 {
    count * 2
}
