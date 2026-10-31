// ASP413: a `match` on a same-crate enum value with a `_ =>` wildcard arm
// defeats the compiler's exhaustiveness checking — adding a new `State`
// variant will silently fall through the wildcard instead of erroring.
// Enforced by `clippy::wildcard_enum_match_arm` forced to deny.

pub enum State {
    Active,
    Idle,
    Done,
}

pub fn describe(state: State) -> u8 {
    match state {
        State::Active => 1,
        _ => 0,
    }
}
