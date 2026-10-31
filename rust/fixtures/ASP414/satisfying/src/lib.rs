// ASP414 satisfied: dispatch goes through the `State` enum's variants, not
// string literals shadowing them, so the compiler checks exhaustiveness.

pub enum State {
    Active,
    Idle,
    Done,
}

pub fn route(state: State) -> u8 {
    match state {
        State::Active => 1,
        State::Idle => 2,
        State::Done => 0,
    }
}
