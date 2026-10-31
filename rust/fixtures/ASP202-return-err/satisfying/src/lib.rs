// An I/O function with two `return Err(..)` guard clauses clears
// MIN_ASSERTS: a guard clause is a recognized ASP202 assertion form.
pub fn transfer(path: &str, a: i32, b: i32) -> Result<i32, String> {
    if a < 0 {
        return Err("a".to_string());
    }
    if b < 0 {
        return Err("b".to_string());
    }
    let w = (a + b) * 2;
    std::fs::write(path, w.to_string()).map_err(|e| e.to_string())?;
    Ok(w)
}
