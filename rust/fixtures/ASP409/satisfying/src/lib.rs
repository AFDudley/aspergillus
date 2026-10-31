// No shell-to-self. This crate is `asp409-satisfying`; none of these
// re-invoke it. They spawn an EXTERNAL tool (`git`), drive cargo for a
// whole-workspace task (`cargo metadata`, `cargo build` with no `-p`), or
// run a DIFFERENT workspace crate as a black-box harness
// (`cargo run -p backtest`) — a legitimate process-boundary measurement,
// not a self-invocation.

use std::process::Command;

pub fn git_status() -> std::io::Result<std::process::Output> {
    Command::new("git").arg("status").output()
}

pub fn workspace_metadata() -> std::io::Result<std::process::Output> {
    Command::new("cargo").arg("metadata").output()
}

pub fn build_all() -> std::io::Result<std::process::Output> {
    Command::new("cargo").arg("build").output()
}

pub fn run_sibling_binary() -> std::io::Result<std::process::Output> {
    Command::new("cargo")
        .args(["run", "-p", "backtest", "--"])
        .output()
}
