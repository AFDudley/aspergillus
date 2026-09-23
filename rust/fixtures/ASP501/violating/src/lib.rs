// Two functions whose whole bodies differ - a distinct first statement and a
// distinct trailing statement each - but which share an identical run of
// three consecutive statements in the middle (the accumulate-and-double
// block). A whole-body clone hash cannot see this copied spine, because the
// surrounding code makes the whole-body hashes differ; the statement-spine
// sliding window does. ASP501 fires at each copy's window start.

pub fn compute_left(input: &[u32]) -> u32 {
    let label = 10;
    let mut total = 0;
    for item in input {
        total += item;
    }
    total = total * 2;
    total + label
}

pub fn compute_right(values: &[u32]) -> u32 {
    let name = other_fn();
    let mut total = 0;
    for item in values {
        total += item;
    }
    total = total * 2;
    finalize(total, name)
}

fn other_fn() -> u32 {
    7
}

fn finalize(total: u32, name: u32) -> u32 {
    total + name
}
