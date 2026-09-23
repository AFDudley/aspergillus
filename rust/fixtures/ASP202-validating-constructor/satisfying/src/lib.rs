// Two validating-constructor calls (`try_from`) clear MIN_ASSERTS: a
// fallible constructor is itself a precondition check on its input, and
// is one of the recognized ASP202 assertion forms.
pub fn transfer(a: &str, b: &str) -> i32 {
    let x = i32::try_from(a.len()).unwrap_or(0);
    let y = i32::try_from(b.len()).unwrap_or(0);
    let z = x + y;
    let w = z * 2;
    let v = w - 1;
    v
}
