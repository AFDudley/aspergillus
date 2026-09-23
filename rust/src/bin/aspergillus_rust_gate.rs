//! The Aspergillus Rust gate's CLI: the imperative shell.
//!
//! Loads the ast-grep rules shipped in this crate's own `ast-grep-rules/`
//! directory, scans a Cargo workspace's `*.rs` files with them, runs the
//! reference clippy lints over the same workspace, prints every finding as
//! `path:line: ASPnnn`, and exits non-zero when a blocking finding exists.

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use ast_grep_config::{from_yaml_string, GlobalRules, RuleConfig};
use ast_grep_language::SupportLang;
use walkdir::WalkDir;

use aspergillus_rust_gate::{clippy, exit_status, purity, source_findings, Finding};

/// The rule directory shipped alongside this crate, resolved at compile
/// time so it travels with the crate whether a consumer copies `rust/`
/// wholesale or depends on it by path.
const RULES_DIR: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/ast-grep-rules");

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.len() > 1 {
        eprintln!("usage: aspergillus-rust-gate [WORKSPACE_DIR]   (default: .)");
        return ExitCode::from(2);
    }
    let workspace_dir = PathBuf::from(args.first().map_or(".", String::as_str));

    let rules = match load_rules(Path::new(RULES_DIR)) {
        Ok(rules) => rules,
        Err(why) => {
            eprintln!("aspergillus-rust-gate: input error: {why}");
            return ExitCode::from(2);
        }
    };

    let (mut findings, scanned) = match scan_workspace(&rules, &workspace_dir) {
        Ok(result) => result,
        Err(why) => {
            eprintln!("aspergillus-rust-gate: input error: {why}");
            return ExitCode::from(2);
        }
    };

    match clippy::clippy_findings(&workspace_dir) {
        Ok(hits) => findings.extend(hits),
        Err(why) => {
            eprintln!("aspergillus-rust-gate: clippy error: {why}");
            return ExitCode::from(2);
        }
    }

    findings.sort_by(|a, b| {
        a.path
            .cmp(&b.path)
            .then(a.line.cmp(&b.line))
            .then(a.rule_id.cmp(&b.rule_id))
    });
    findings.dedup();

    for finding in &findings {
        println!("{}", finding.render());
    }
    eprintln!(
        "aspergillus-rust-gate: scanned {scanned} source file(s), {} finding(s)",
        findings.len()
    );
    ExitCode::from(exit_status(&findings))
}

/// The ast-grep rules declared by the shipped rule directory's YAML files.
fn load_rules(dir: &Path) -> Result<Vec<RuleConfig<SupportLang>>, String> {
    let globals = GlobalRules::default();
    let mut files: Vec<PathBuf> = std::fs::read_dir(dir)
        .map_err(|e| format!("{}: {e}", dir.display()))?
        .filter_map(|entry| entry.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|x| x == "yml" || x == "yaml"))
        .collect();
    files.sort();
    let mut rules = Vec::new();
    for path in files {
        let text =
            std::fs::read_to_string(&path).map_err(|e| format!("{}: {e}", path.display()))?;
        let parsed = from_yaml_string::<SupportLang>(&text, &globals)
            .map_err(|e| format!("{}: {e}", path.display()))?;
        rules.extend(parsed);
    }
    Ok(rules)
}

/// Every `*.rs` file under `workspace_dir`, skipping `target/` and any
/// hidden directory, in path order.
fn rust_files(workspace_dir: &Path) -> Vec<PathBuf> {
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

/// Every ast-grep finding across the workspace's Rust source files, and
/// how many files were scanned.
fn scan_workspace(
    rules: &[RuleConfig<SupportLang>],
    workspace_dir: &Path,
) -> Result<(Vec<Finding>, usize), String> {
    let files = rust_files(workspace_dir);
    let mut findings = Vec::new();
    for path in &files {
        let source =
            std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
        let shown = path
            .strip_prefix(workspace_dir)
            .unwrap_or(path)
            .to_string_lossy()
            .into_owned();
        findings.extend(source_findings(rules, &source).into_iter().map(
            |(line, rule_id, blocking)| Finding {
                path: shown.clone(),
                line,
                rule_id,
                blocking,
            },
        ));
        for (line, rule_id, blocking) in purity::assertion_density_findings(&source)
            .into_iter()
            .chain(purity::impure_function_findings(&source))
            .chain(purity::mixed_io_logic_findings(&source))
        {
            findings.push(Finding {
                path: shown.clone(),
                line,
                rule_id: rule_id.to_string(),
                blocking,
            });
        }
    }
    Ok((findings, files.len()))
}
