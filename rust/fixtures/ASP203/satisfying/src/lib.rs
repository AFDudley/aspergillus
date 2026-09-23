// No global mutable state. An immutable `static` is a shared constant, and a
// `LazyLock` gives the value a single owner with interior mutability that the
// type system guards - neither is a `static mut`, so ASP203 stays silent.

use std::sync::LazyLock;

pub static MAX_RETRIES: u32 = 3;

static CONFIG: LazyLock<Config> = LazyLock::new(|| Config {
    name: "default".to_string(),
});

pub struct Config {
    pub name: String,
}

pub fn config() -> &'static Config {
    &CONFIG
}
