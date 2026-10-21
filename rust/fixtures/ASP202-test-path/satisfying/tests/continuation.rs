// A crate-level integration-test helper: it performs I/O and carries no
// assertion form, but it lives under a tests/ directory, so ASP202 exempts it
// (test infrastructure, not imperative-shell debt) even without a #[test]
// attribute on the helper itself.
fn chunk_directory(name: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(name);
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("c0.pcap"), b"").unwrap();
    dir
}

#[test]
fn builds_a_directory() {
    let _ = chunk_directory("asp202-test-path-fixture");
}
