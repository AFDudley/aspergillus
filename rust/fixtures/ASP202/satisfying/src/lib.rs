// An I/O-performing function past the threshold with two assertion forms
// clears MIN_ASSERTS: no ASP202 finding.
pub fn transfer(path: &str, balance: i64, amount: i64, fee: i64) -> i64 {
    assert!(balance >= 0);
    assert!(amount >= 0);
    let after_fee = amount + fee;
    let total = balance - after_fee - fee;
    std::fs::write(path, total.to_string()).unwrap();
    total
}
