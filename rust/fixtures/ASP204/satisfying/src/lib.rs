// Every loop here carries a determinable bound, so ASP204 stays silent:
// an iterator (`for` over a range), a counter (`while c < n`), a
// counter-driven `break`, an iterator-driven `break`, and a `return`.

pub fn over_a_range(max: u32) -> u32 {
    // Iterator bound: `for` over a range.
    let mut total = 0;
    for x in 0..max {
        total += x;
    }
    total
}

pub fn count_to(limit: u32) -> u32 {
    // Counter bound: the re-tested `while` condition.
    let mut count = 0;
    while count < limit {
        count += 1;
    }
    count
}

pub fn poll_until_ready(mut check: impl FnMut() -> bool) -> u32 {
    // Counter-driven `break`: the deliberate exit the author wrote.
    let mut attempts = 0;
    loop {
        if attempts >= 10 || check() {
            break;
        }
        attempts += 1;
    }
    attempts
}

pub fn drain(mut next: impl FnMut() -> Option<u32>) -> u32 {
    // Iterator-driven `break`: the loop ends when the source is exhausted.
    let mut total = 0;
    loop {
        match next() {
            Some(v) => total += v,
            None => break,
        }
    }
    total
}

pub fn first_match(items: &[u32], want: u32) -> Option<usize> {
    // `return` bound: a deliberate function-level exit terminates the loop.
    let mut i = 0;
    loop {
        if i >= items.len() {
            return None;
        }
        if items[i] == want {
            return Some(i);
        }
        i += 1;
    }
}
