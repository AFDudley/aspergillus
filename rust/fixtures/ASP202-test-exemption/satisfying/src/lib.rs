// A `#[test]` function is exempt from ASP202 even when it performs I/O
// and carries no assertion form, matching the Python rule's `test_`
// exemption.
#[test]
fn checks_transfer() {
    let a = 1;
    let b = a + 1;
    let c = b + 1;
    let d = c + 1;
    std::fs::write("/tmp/asp202_test_fixture", d.to_string()).unwrap();
}
