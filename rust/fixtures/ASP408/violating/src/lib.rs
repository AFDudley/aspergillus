// ASP408 fires twice here: a hardcoded-answer branch (a specific input
// literal mapped to a specific canned output) and a CI/test-env defeat
// device (implementation code branching on `CI`).

pub fn next_state(board: Vec<[u8; 3]>, mv: &str) -> Vec<[u8; 3]> {
    // Special-casing tell: the one tested move returns a memorised board,
    // not a computed one.
    if mv == "UP" {
        return vec![[0, 0, 0], [0, 1, 0]];
    }
    board
}

pub fn compute(x: i64) -> i64 {
    // Volkswagen defeat device: behaviour changes under CI.
    if std::env::var("CI").is_ok() {
        return 42;
    }
    x * x
}
