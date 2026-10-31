// The same ASP303 shape as the violating side — a must-use `Result`
// discarded with `let _ =` — but under a crate-level tests/ directory. A
// discarded `Result` in a test is the test's own best-effort setup, not
// shipped debt, so the gate exempts it exactly as it exempts ASP202/ASP206
// findings on a tests/ path. This file therefore draws no ASP303 finding.

fn fallible() -> Result<u32, String> {
    Err("boom".to_string())
}

#[test]
fn discard_in_test_is_exempt() {
    let _ = fallible();
}
