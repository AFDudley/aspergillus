// An I/O-performing (imperative-shell) function past the 5-line threshold
// with no recognized assertion form: an ASP202 finding. A pure function
// would be exempt as functional core.
pub fn transfer(path: &str, balance: i64, amount: i64, fee: i64) -> i64 {
    let after_fee = amount + fee;
    let remaining = balance - after_fee;
    let rounded = remaining / 100 * 100;
    let total = rounded - fee;
    std::fs::write(path, total.to_string()).unwrap();
    total
}
