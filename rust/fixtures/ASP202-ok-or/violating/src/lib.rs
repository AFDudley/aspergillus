// A function past the 5-line threshold with no recognized assertion
// form: an ASP202 finding.
pub fn transfer(a: i32, b: i32, c: i32) -> i32 {
    let x = a + b;
    let y = x + c;
    let z = y - a;
    let w = z * 2;
    let v = w - b;
    v
}
