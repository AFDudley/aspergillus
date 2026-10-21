// ASP303: a failure swallowed into a success sentinel — a fallible `Result`
// discarded silently instead of propagated. Each function below drops the
// error so a caller cannot tell failure from success.

use std::fs;

/// A fallible operation whose `Result` is `#[must_use]`.
fn fallible() -> Result<u32, String> {
    Err("boom".to_string())
}

/// `let _ =` discards a must-use `Result` — the error is swallowed
/// (clippy::let_underscore_must_use).
pub fn let_underscore_discard() {
    let _ = fallible();
}

/// A bare `Result` statement discards the must-use value (unused_must_use).
pub fn bare_discard() {
    fallible();
}

/// A `Result` reduced to `Option` via `.ok()` and dropped as a statement.
/// This swallows the error too, but the forced must-use lints cannot see it
/// (`Option` is not `#[must_use]`), and the only lobaria instances of this
/// shape are idiomatic best-effort cleanup — so no rule is shipped for it.
/// Kept as documentation of the shape and the known coverage gap.
pub fn ok_discard() {
    fs::remove_file("nope").ok();
}
