// ASP303 satisfying: the failure is made explicit on every path — either
// propagated with `?` or handled by matching the `Err` arm. Nothing is
// swallowed into a success sentinel.

fn fallible() -> Result<u32, String> {
    Ok(1)
}

/// Propagates the failure with the question-mark operator.
pub fn propagate() -> Result<u32, String> {
    let v = fallible()?;
    Ok(v)
}

/// Handles the failure by matching the `Err` arm and folding the source
/// error into a surfaced domain error — observed, never swallowed. (No
/// I/O, so this shell function draws no unrelated ASP202/ASP206 finding;
/// the fixture isolates ASP303.)
pub fn handle() -> Result<u32, String> {
    match fallible() {
        Ok(v) => Ok(v),
        Err(e) => Err(format!("fallible failed: {e}")),
    }
}
