// Two `return Err(..)` guard clauses clear MIN_ASSERTS: a guard clause
// is one of the recognized ASP202 assertion forms.
pub fn transfer(a: i32, b: i32) -> Result<i32, String> {
    if a < 0 {
        return Err("a".to_string());
    }
    if b < 0 {
        return Err("b".to_string());
    }
    let z = a + b;
    let w = z * 2;
    Ok(w)
}
