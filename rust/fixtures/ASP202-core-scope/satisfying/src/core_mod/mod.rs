// The same low-assertion I/O shape, but under the declared core path
// `src/core_mod/**`: ASP202 is scoped to the imperative shell, so a core
// file gets no ASP202 finding (its I/O is an ASP205 concern instead).
pub fn core_transfer(path: &str, a: i32, b: i32, c: i32) -> i32 {
    let x = a + b;
    let y = x + c;
    let z = y - a;
    let w = z * 2;
    std::fs::write(path, w.to_string()).unwrap();
    w
}
