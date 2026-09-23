pub fn poll_until_ready(mut check: impl FnMut() -> bool) -> u32 {
    let mut attempts = 0;
    loop {
        if check() {
            return attempts;
        }
        attempts += 1;
    }
}
