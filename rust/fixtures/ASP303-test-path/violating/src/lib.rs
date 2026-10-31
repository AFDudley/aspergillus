// ASP303 in PRODUCTION code: a must-use `Result` discarded with `let _ =`,
// at src/lib.rs (not under a tests/ directory and not in a #[test]/#[cfg(test)]
// scope). The failure is swallowed into a success sentinel, so the gate fires
// ASP303 (clippy::let_underscore_must_use) and the run exits 1 — the clippy-
// backed rule holds production code to the propagate-or-handle standard.
fn fallible() -> Result<u32, String> {
    Err("boom".to_string())
}

pub fn discard_in_production() {
    let _ = fallible();
}
