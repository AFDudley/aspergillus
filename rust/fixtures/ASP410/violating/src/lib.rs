//! The system-under-test, exercised in-process by the fake e2e in
//! `tests/e2e.rs`.

#[derive(Default)]
pub struct App;

impl App {
    pub fn new() -> Self {
        App
    }

    pub fn tick(&mut self) {}

    pub fn done(&self) -> bool {
        true
    }
}
