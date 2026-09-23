//! Shared Cargo-workspace file walk (imperative shell).
//!
//! Every binary - the ast-grep/clippy gate, the duplicate-function check,
//! and the duplicate-type check - scans the same set of files, so the
//! walk lives here once rather than copied into each `bin/`.

use std::path::{Path, PathBuf};

use globset::{Glob, GlobSet, GlobSetBuilder};
use walkdir::WalkDir;

/// Builds a matcher for a repeatable `--exclude <glob>` option: each
/// pattern is a workspace-relative, gitignore/fnmatch-style glob (so
/// `scripts/oracles/fixtures/**` names a whole subtree). An empty pattern
/// list matches nothing, so passing no `--exclude` flag excludes nothing.
pub fn build_excludes(patterns: &[String]) -> Result<GlobSet, String> {
    let mut builder = GlobSetBuilder::new();
    for pattern in patterns {
        let glob = Glob::new(pattern).map_err(|e| format!("--exclude {pattern}: {e}"))?;
        builder.add(glob);
    }
    builder.build().map_err(|e| format!("--exclude: {e}"))
}

/// Extracts every `--exclude <glob>` pair from `args`, in encounter order,
/// leaving every other argument in its original relative order. A binary
/// calls this once, before its own argument parsing, so the same
/// repeatable option works the same way across every binary.
pub fn take_excludes(args: Vec<String>) -> Result<(Vec<String>, Vec<String>), String> {
    let mut excludes = Vec::new();
    let mut remaining = Vec::new();
    let mut iter = args.into_iter();
    while let Some(arg) = iter.next() {
        if arg == "--exclude" {
            let value = iter.next().ok_or("--exclude needs a GLOB argument")?;
            excludes.push(value);
        } else {
            remaining.push(arg);
        }
    }
    Ok((excludes, remaining))
}

/// Every `*.rs` file under `workspace_dir`, skipping `target/`, any hidden
/// directory, and any file whose workspace-relative path matches `excludes`,
/// in path order - so a workspace of many crates is read whole, not one
/// crate only, and a consumer's own rule-violating fixture subtree never
/// enters the scan.
pub fn rust_source_files(workspace_dir: &Path, excludes: &GlobSet) -> Vec<PathBuf> {
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
        .filter(|p| !excludes.is_match(p.strip_prefix(workspace_dir).unwrap_or(p)))
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
