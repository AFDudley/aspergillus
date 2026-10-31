pub fn allow(cond: bool, fallback: bool) -> bool {
    if cond {
        true
    } else {
        fallback
    }
}
