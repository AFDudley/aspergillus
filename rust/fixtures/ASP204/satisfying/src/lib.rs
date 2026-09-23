pub fn poll_until_ready(mut check: impl FnMut() -> bool, max_attempts: u32) -> Option<u32> {
    for attempt in 0..max_attempts {
        if check() {
            return Some(attempt);
        }
    }
    None
}
