// Two `?` operators clear MIN_ASSERTS: the `?` operator is one of the
// recognized ASP202 assertion forms.
pub fn transfer(a: &str, b: &str) -> Result<i32, std::num::ParseIntError> {
    let x = a.parse::<i32>()?;
    let y = b.parse::<i32>()?;
    let z = x + y;
    let w = z * 2;
    let v = w - 1;
    Ok(v)
}
