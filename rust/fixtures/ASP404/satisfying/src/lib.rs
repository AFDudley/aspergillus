pub fn allow(cond: bool, fallback: bool) -> bool {
    cond || fallback
}
