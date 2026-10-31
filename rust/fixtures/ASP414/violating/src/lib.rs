// ASP414: dispatch on string literals that shadow a same-file enum's
// variant names — stringly-typed dispatch that bypasses exhaustiveness
// checking. Match on the `State` enum itself instead.

pub enum State {
    Active,
    Idle,
    Done,
}

pub fn route(raw: &str) -> u8 {
    match raw {
        "Active" => 1,
        "Idle" => 2,
        _ => 0,
    }
}
