// Same low-assertion shape as `violating/src/lib.rs`, but under
// `src/core_mod/`, the crate's declared functional-core path
// (`--core 'src/core_mod/**'`), so ASP202 stays silent here.
pub fn core_transfer(a: i32, b: i32, c: i32) -> i32 {
    let x = a + b;
    let y = x + c;
    let z = y - a;
    let w = z * 2;
    let v = w - b;
    v
}
