// ASP411 satisfied: every match arm carries a distinct body, so no two
// states are redundant and nothing should be merged.

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
