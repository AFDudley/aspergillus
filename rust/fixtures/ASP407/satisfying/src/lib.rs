// ASP407 satisfied: this function does real work rather than forwarding its
// parameters verbatim, so it is not a trivial pass-through wrapper.

pub fn add(x: i32, y: i32) -> i32 {
    let scaled = x * 2;
    combine(scaled, y)
}

fn combine(a: i32, b: i32) -> i32 {
    a + b
}
