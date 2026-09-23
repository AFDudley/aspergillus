//! Shared Cargo-workspace file walk (imperative shell).
//!
//! Both binaries - the ast-grep/clippy gate and the duplicate-function
//! check - scan the same set of files, so the walk lives here once rather
//! than copied into each `bin/`.

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
