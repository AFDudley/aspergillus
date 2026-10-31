// ASP304: a failure that discards the captured evidence. The `map_err`
// closure binds its source-error argument to the wildcard `_`, throwing away
// the underlying error before surfacing a one-bit summary.

use std::io;

fn read_thing() -> Result<u32, io::Error> {
    Ok(1)
}

/// The `map_err(|_| ...)` wildcard drops the `io::Error` evidence.
pub fn load() -> Result<u32, String> {
    read_thing().map_err(|_| "could not read thing".to_string())
}
