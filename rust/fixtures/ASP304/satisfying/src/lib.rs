// ASP304 satisfying: the source error is preserved on every failure path —
// either bound and surfaced by the `map_err` closure, or carried forward by a
// `From` conversion via `?`. No evidence is discarded.

use std::io;

fn read_thing() -> Result<u32, io::Error> {
    Ok(1)
}

/// The closure binds the source error `e` and folds it into the message.
pub fn load_keep() -> Result<u32, String> {
    read_thing().map_err(|e| format!("could not read thing: {e}"))
}

#[derive(Debug)]
pub struct LoadError(io::Error);

impl From<io::Error> for LoadError {
    fn from(source: io::Error) -> Self {
        LoadError(source)
    }
}

/// `?` carries the source error forward through the `From` conversion.
pub fn load_from() -> Result<u32, LoadError> {
    let v = read_thing()?;
    Ok(v)
}
