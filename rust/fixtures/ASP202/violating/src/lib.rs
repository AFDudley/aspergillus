pub fn transfer(balance: i64, amount: i64, fee: i64) -> i64 {
    let after_fee = amount + fee;
    let remaining = balance - after_fee;
    let rounded = remaining / 100 * 100;
    let adjusted = rounded + 1;
    let total = adjusted - fee;
    total
}
