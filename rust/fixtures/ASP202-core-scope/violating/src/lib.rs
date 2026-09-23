// An I/O function with the low-assertion shape at `src/lib.rs` — outside
// the declared core path `src/core_mod/**` — so it gets an ASP202 finding.
pub fn shell_transfer(path: &str, a: i32, b: i32, c: i32) -> i32 {
    let x = a + b;
    let y = x + c;
    let z = y - a;
    let w = z * 2;
    std::fs::write(path, w.to_string()).unwrap();
    w
}
