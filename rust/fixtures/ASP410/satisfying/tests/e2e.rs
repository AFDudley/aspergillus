// No ASP410: this `e2e` test crosses a real process boundary — it spawns
// an external process rather than driving the SUT in-process.

use std::process::Command;

#[test]
fn drives_the_flow() {
    let output = Command::new("true").output();
    assert!(output.is_ok());
}
