// ASP409 fires here: implementation code shells out to its OWN package
// rather than importing the function and calling it. Two shapes:
// `cargo run -p <self>` (this crate is `asp409-violating`) and spawning
// this crate's own `CARGO_BIN_EXE_*` binary.

use std::process::Command;

pub fn rerun_self() {
    let _ = Command::new("cargo")
        .arg("run")
        .arg("-p")
        .arg("asp409-violating")
        .status();
}

pub fn run_own_binary() -> std::io::Result<std::process::Output> {
    Command::new(option_env!("CARGO_BIN_EXE_asp409-violating").unwrap_or("asp409-violating"))
        .output()
}
