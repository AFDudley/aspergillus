// An I/O function with two `ok_or_else` calls clears MIN_ASSERTS:
// `ok_or_else` turns an `Option` into a checked `Result`.
pub fn transfer(path: &str, a: Option<i32>, b: Option<i32>) -> Result<i32, String> {
    let x = a.ok_or_else(|| "a".to_string())?;
    let y = b.ok_or_else(|| "b".to_string())?;
    let w = (x + y) * 2;
    std::fs::write(path, w.to_string()).map_err(|e| e.to_string())?;
    Ok(w)
}
