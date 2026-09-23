// Same low-assertion shape as `satisfying/src/core_mod/mod.rs`, but at
// `src/lib.rs` — not under the crate's declared core path — so it still
// gets an ASP202 finding under `--core 'src/core_mod/**'`.
pub fn shell_transfer(a: i32, b: i32, c: i32) -> i32 {
    let x = a + b;
    let y = x + c;
    let z = y - a;
    let w = z * 2;
    let v = w - b;
    v
}
