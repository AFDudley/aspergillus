//! Shared Cargo-workspace file walk (imperative shell).
//!
//! Every binary - the ast-grep/clippy gate, the duplicate-function check,
//! and the duplicate-type check - scans the same set of files, so the
//! walk lives here once rather than copied into each `bin/`.

use std::path::{Path, PathBuf};

use walkdir::WalkDir;

/// Every `*.rs` file under `workspace_dir`, skipping `target/` and any
/// hidden directory, in path order - so a workspace of many crates is
/// read whole, not one crate only.
pub fn rust_source_files(workspace_dir: &Path) -> Vec<PathBuf> {
    let mut files: Vec<PathBuf> = WalkDir::new(workspace_dir)
        .into_iter()
        .filter_entry(|entry| {
            let name = entry.file_name().to_string_lossy();
            entry.depth() == 0 || (name != "target" && !name.starts_with('.'))
        })
        .filter_map(std::result::Result::ok)
        .filter(|entry| entry.file_type().is_file())
        .map(walkdir::DirEntry::into_path)
        .filter(|p| p.extension().is_some_and(|x| x == "rs"))
        .collect();
    files.sort();
    files
}

/// Every crate root under `workspace_dir`: the workspace-relative path of
/// each directory holding a `Cargo.toml`, skipping `target/` and any
/// hidden directory. The workspace root itself, if it holds a
/// `Cargo.toml` (a virtual manifest or a single-crate workspace), reports
/// as the empty string — so the duplicate-type check can tell which
/// crate each scanned file belongs to.
pub fn crate_roots(workspace_dir: &Path) -> Vec<String> {
    let mut roots: Vec<String> = WalkDir::new(workspace_dir)
        .into_iter()
        .filter_entry(|entry| {
            let name = entry.file_name().to_string_lossy();
            entry.depth() == 0 || (name != "target" && !name.starts_with('.'))
        })
        .filter_map(std::result::Result::ok)
        .filter(|entry| entry.file_type().is_file() && entry.file_name() == "Cargo.toml")
        .map(|entry| {
            entry
                .path()
                .parent()
                .unwrap_or(workspace_dir)
                .strip_prefix(workspace_dir)
                .unwrap_or_else(|_| Path::new(""))
                .to_string_lossy()
                .into_owned()
        })
        .collect();
    roots.sort();
    roots
}
