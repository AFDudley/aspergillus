// The downstream crate. It USES `leaf::value` (so it builds only after `leaf`)
// and carries its own ASP303 discard. When `leaf` fails to build under `deny`,
// this crate is never checked and its discard is dropped from the count — the
// nondeterminism the warn-level fix removes.
fn fallible() -> Result<u32, String> {
    Err("app boom".to_string())
}

pub fn run() -> u32 {
    let _ = fallible();
    asp303_determinism_leaf::value()
}
