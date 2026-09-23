//! The Aspergillus Rust duplicate-type check's CLI: the imperative shell.
//!
//! Walks a Cargo workspace's `*.rs` files across every crate, finds every
//! struct or enum CONCEPT — the same declared name carrying the same
//! shape (see `duplicate_types.rs` for the shape definition) — declared
//! in more than one crate, and prints each occurrence as
//! `path:line: ASP502`. A concept confined to one crate is not reported.
//! Report-only: it never rewrites a scanned file. Exits non-zero when it
//! reports a finding.
//!
//! Usage: `cargo run --manifest-path rust/Cargo.toml --bin
//! aspergillus-rust-dup-type-check -- [WORKSPACE_DIR] [--allowlist FILE]
//! [--exclude GLOB]...` (default workspace: `.`).

use std::collections::HashSet;
use std::path::PathBuf;
use std::process::ExitCode;

use aspergillus_rust_gate::duplicate_types::{
    apply_allowlist, crate_id_for_path, duplicate_groups, findings_for_groups, type_occurrences,
};
use aspergillus_rust_gate::workspace::{
    build_excludes, crate_roots, rust_source_files, take_excludes,
};

fn main() -> ExitCode {
    let raw_args: Vec<String> = std::env::args().skip(1).collect();
    let (exclude_patterns, remaining) = match take_excludes(raw_args) {
        Ok(parsed) => parsed,
        Err(why) => {
            eprintln!("aspergillus-rust-dup-type-check: {why}");
            return ExitCode::from(2);
        }
    };
    let excludes = match build_excludes(&exclude_patterns) {
        Ok(excludes) => excludes,
        Err(why) => {
            eprintln!("aspergillus-rust-dup-type-check: {why}");
            return ExitCode::from(2);
        }
    };

    let (workspace_dir, allowlist_path) = match parse_args(remaining) {
        Ok(parsed) => parsed,
        Err(why) => {
            eprintln!("aspergillus-rust-dup-type-check: {why}");
            eprintln!(
                "usage: aspergillus-rust-dup-type-check [WORKSPACE_DIR] [--allowlist FILE] [--exclude GLOB]..."
            );
            return ExitCode::from(2);
        }
    };

    let allowed = match &allowlist_path {
        Some(path) => match load_allowlist(path) {
            Ok(allowed) => allowed,
            Err(why) => {
                eprintln!("aspergillus-rust-dup-type-check: input error: {why}");
                return ExitCode::from(2);
            }
        },
        None => HashSet::new(),
    };

    let roots = crate_roots(&workspace_dir);
    let files = rust_source_files(&workspace_dir, &excludes);
    let mut occurrences = Vec::new();
    for path in &files {
        let source = match std::fs::read_to_string(path) {
            Ok(source) => source,
            Err(why) => {
                eprintln!(
                    "aspergillus-rust-dup-type-check: input error: {}: {why}",
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
        let crate_id = crate_id_for_path(std::path::Path::new(&shown), &roots);
        occurrences.extend(type_occurrences(&shown, &crate_id, &source));
    }

    let groups = apply_allowlist(duplicate_groups(&occurrences), &allowed);
    let findings = findings_for_groups(&groups);

    for finding in &findings {
        println!("{}", finding.render());
    }
    eprintln!(
        "aspergillus-rust-dup-type-check: scanned {} source file(s), {} duplicate concept(s), {} finding(s)",
        files.len(),
        groups.len(),
        findings.len()
    );
    ExitCode::from(u8::from(!findings.is_empty()))
}

/// Parses `[WORKSPACE_DIR] [--allowlist FILE]` in either argument order.
fn parse_args(args: Vec<String>) -> Result<(PathBuf, Option<PathBuf>), String> {
    let mut workspace_dir: Option<PathBuf> = None;
    let mut allowlist: Option<PathBuf> = None;
    let mut iter = args.into_iter();
    while let Some(arg) = iter.next() {
        if arg == "--allowlist" {
            let value = iter.next().ok_or("--allowlist needs a FILE argument")?;
            allowlist = Some(PathBuf::from(value));
        } else if workspace_dir.is_none() {
            workspace_dir = Some(PathBuf::from(arg));
        } else {
            return Err(format!("unexpected argument: {arg}"));
        }
    }
    Ok((
        workspace_dir.unwrap_or_else(|| PathBuf::from(".")),
        allowlist,
    ))
}

/// Loads an allowlist file: one accepted type NAME per line, with `#`
/// starting a trailing comment and blank lines ignored — the same format
/// `aspergillus check-duplicates --allowlist` uses for Python
/// (`python/src/aspergillus/duplicates.py::parse_allowlist`).
fn load_allowlist(path: &std::path::Path) -> Result<HashSet<String>, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    Ok(text
        .lines()
        .filter_map(|line| {
            let stripped = line.split('#').next().unwrap_or("").trim();
            (!stripped.is_empty()).then(|| stripped.to_string())
        })
        .collect())
}
