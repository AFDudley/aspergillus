pub fn transfer(balance: i64, amount: i64, fee: i64) -> i64 {
    assert!(balance >= 0);
    assert!(amount >= 0);
    let after_fee = amount + fee;
    let remaining = balance - after_fee;
    let rounded = remaining / 100 * 100;
    let total = rounded - fee;
    total
}
