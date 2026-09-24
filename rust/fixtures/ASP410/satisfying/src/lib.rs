//! The library core; the genuine e2e in `tests/e2e.rs` drives a real
//! process, not this in-process.

#[derive(Default)]
pub struct App;

impl App {
    pub fn new() -> Self {
        App
    }

    pub fn tick(&mut self) {}
}
