//! The Aspergillus Rust duplicate-function check's CLI: the imperative
//! shell.
//!
//! Walks a Cargo workspace's `*.rs` files across every crate, finds every
//! pair of Rust functions whose type-2 normalized bodies are identical -
//! the same equivalence `aspergillus check-duplicates` uses for Python
//! (`python/src/aspergillus/duplicates.py`) - and prints each one as
//! `path:line: ASP501`. Report-only: it never rewrites a scanned file.
//! Exits non-zero when it reports a finding.
//!
//! Usage: `cargo run --manifest-path rust/Cargo.toml --bin
//! aspergillus-rust-dup-check -- [WORKSPACE_DIR]` (default: `.`).

use std::path::PathBuf;
use std::process::ExitCode;

use aspergillus_rust_gate::duplicates::{
    duplicate_groups, findings_for_groups, function_occurrences,
};
use aspergillus_rust_gate::workspace::rust_source_files;

/// Matches the Python reference's `check-duplicates --min-lines` default:
/// a function spanning fewer lines is excluded from clone detection.
const DEFAULT_MIN_LINES: usize = 5;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.len() > 1 {
        eprintln!("usage: aspergillus-rust-dup-check [WORKSPACE_DIR]   (default: .)");
        return ExitCode::from(2);
    }
    let workspace_dir = PathBuf::from(args.first().map_or(".", String::as_str));

    let files = rust_source_files(&workspace_dir);
    let mut occurrences = Vec::new();
    for path in &files {
        let source = match std::fs::read_to_string(path) {
            Ok(source) => source,
            Err(why) => {
                eprintln!(
                    "aspergillus-rust-dup-check: input error: {}: {why}",
                    path.display()
                );
                return ExitCode::from(2);
            }
        };
        let shown = path
            .strip_prefix(&workspace_dir)
            .unwrap_or(path)
            .to_string_lossy()
            .into_owned();
        occurrences.extend(function_occurrences(&shown, &source, DEFAULT_MIN_LINES));
    }

    let groups = duplicate_groups(&occurrences);
    let findings = findings_for_groups(&groups);

    for finding in &findings {
        println!("{}", finding.render());
    }
    eprintln!(
        "aspergillus-rust-dup-check: scanned {} source file(s), {} duplicate group(s), {} finding(s)",
        files.len(),
        groups.len(),
        findings.len()
    );
    ExitCode::from(u8::from(!findings.is_empty()))
}
