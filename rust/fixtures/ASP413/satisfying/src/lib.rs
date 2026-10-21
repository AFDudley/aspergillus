// ASP413 satisfied: the `match` lists every `State` variant explicitly with
// no `_ =>` wildcard, so a new variant makes the compiler error here rather
// than falling through silently.

pub enum State {
    Active,
    Idle,
    Done,
}

pub fn describe(state: State) -> u8 {
    match state {
        State::Active => 1,
        State::Idle => 0,
        State::Done => 0,
    }
}
