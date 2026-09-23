// A `#[test]` function with no assertion form at all is exempt from
// ASP202, matching the Python rule's `test_`-prefix exemption.
#[test]
fn checks_transfer() {
    let a = 1;
    let b = a + 1;
    let c = b + 1;
    let d = c + 1;
    let e = d + 1;
}
