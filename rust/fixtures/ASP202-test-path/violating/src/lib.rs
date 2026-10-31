// The same I/O helper as the satisfying side, but at src/lib.rs (not under a
// tests/ directory): an I/O-performing shell function past 5 lines with no
// assertion form is an ASP202 finding.
pub fn chunk_directory(name: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(name);
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("c0.pcap"), b"").unwrap();
    dir
}
