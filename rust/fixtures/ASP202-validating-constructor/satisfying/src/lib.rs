// An I/O function with two validating-constructor calls (`try_from`)
// clears MIN_ASSERTS: a fallible constructor is a precondition check.
pub fn transfer(path: &str, a: &str, b: &str) -> i32 {
    let x = i32::try_from(a.len()).unwrap_or(0);
    let y = i32::try_from(b.len()).unwrap_or(0);
    let w = (x + y) * 2;
    std::fs::write(path, w.to_string()).unwrap();
    w
}
