// ASP410 fires: an `e2e`-named integration test that constructs the SUT
// in-process and drives its loop, crossing NO process boundary — a fake
// gate presenting as an end-to-end test.

use asp410_violating::App;

#[test]
fn drives_the_flow() {
    let mut app = App::new();
    app.tick();
    assert!(app.done());
}
