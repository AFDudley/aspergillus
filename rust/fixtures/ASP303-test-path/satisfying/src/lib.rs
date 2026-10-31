// The production library is clean: no discarded `Result`. The SAME ASP303
// shape as the violating side lives under tests/continuation.rs, where the
// gate exempts it as test infrastructure. So this fixture is silent for
// ASP303 and the run exits 0.
pub fn noop() {}
