// Two `ok_or` calls clear MIN_ASSERTS: `ok_or` turns an `Option` into a
// checked `Result` and is one of the recognized ASP202 assertion forms.
pub fn transfer(a: Option<i32>, b: Option<i32>) -> Result<i32, String> {
    let x = a.ok_or("a".to_string())?;
    let y = b.ok_or("b".to_string())?;
    let z = x + y;
    let w = z * 2;
    Ok(w)
}
