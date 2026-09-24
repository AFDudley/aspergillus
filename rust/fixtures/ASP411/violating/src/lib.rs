// ASP411: two match arms carry structurally identical bodies — redundant
// states that should collapse into a single `Signal::Start | Signal::Resume`
// arm. Reported at the later duplicate arm.

pub enum Signal {
    Start,
    Resume,
    Stop,
}

pub fn handle(signal: Signal, count: i32) -> i32 {
    match signal {
        Signal::Start => count + advance(count),
        Signal::Resume => count + advance(count),
        Signal::Stop => count,
    }
}

fn advance(count: i32) -> i32 {
    count * 2
}
