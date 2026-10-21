// Infinite headers with no deliberate exit — no `break`, no `return`. Their
// iteration count cannot be determined from the source, so ASP204 fires on
// each.

pub fn spin_forever() {
    // The `while true` case: a constant-true header with no exit.
    while true {
        do_work();
    }
}

pub fn churn() {
    // A bare `loop` with no counter, no iterator, and no exit — the reader
    // cannot bound it.
    loop {
        do_work();
    }
}

fn do_work() {}
