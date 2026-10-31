// The upstream crate. It carries one ASP303 discard AND exports an item the
// downstream `app` crate uses, so `app` cannot compile until `leaf` does.
// Under `deny` this crate's error aborted the build and `app` went unchecked;
// under `warn` it compiles and both crates' discards are reported.
fn fallible() -> Result<u32, String> {
    Err("leaf boom".to_string())
}

pub fn touch() {
    let _ = fallible();
}

/// Consumed by `app`, forcing a real build-order dependency `app -> leaf`.
pub fn value() -> u32 {
    7
}
