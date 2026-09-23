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

use aspergillus_rust_gate::core_declaration::{
    default_core_config_path, resolve_core_declaration, CoreDeclaration,
};
use aspergillus_rust_gate::workspace::{build_excludes, rust_source_files, take_excludes};
use aspergillus_rust_gate::{clippy, exit_status, loops, purity, source_findings, Finding};

fn main() -> ExitCode {
    let raw_args: Vec<String> = std::env::args().skip(1).collect();
    let (rules_dir_opt, args) = match take_rules(raw_args) {
        Ok(parsed) => parsed,
        Err(why) => {
            eprintln!("aspergillus-rust-gate: {why}");
            return ExitCode::from(2);
        }
    };
    let (core_config_opt, args) = match take_core_config(args) {
        Ok(parsed) => parsed,
        Err(why) => {
            eprintln!("aspergillus-rust-gate: {why}");
            return ExitCode::from(2);
        }
    };
    let (exclude_patterns, remaining) = match take_excludes(args) {
        Ok(parsed) => parsed,
        Err(why) => {
            eprintln!("aspergillus-rust-gate: {why}");
            return ExitCode::from(2);
        }
    };
    if remaining.len() > 1 {
        eprintln!(
            "usage: aspergillus-rust-gate [WORKSPACE_DIR] [--exclude GLOB]... [--rules DIR] [--core-config FILE]   (default: .)"
        );
        return ExitCode::from(2);
    }
    let excludes = match build_excludes(&exclude_patterns) {
        Ok(excludes) => excludes,
        Err(why) => {
            eprintln!("aspergillus-rust-gate: {why}");
            return ExitCode::from(2);
        }
    };
    let workspace_dir = PathBuf::from(remaining.first().map_or(".", String::as_str));

    // Resolve the consumer's functional-core path declaration: the
    // `--core-config` argument when given, otherwise
    // `<WORKSPACE_DIR>/aspergillus.toml`. ASP205/ASP206 are always part of
    // the run, so the gate REQUIRES a declaration: a missing, unreadable or
    // unparseable one is a hard input error (exit 2), never a silent
    // "report nothing" — a judge must not fail open. A workspace with no
    // pure core says so explicitly with `core_paths = []` (which parses to
    // an empty core: ASP205 never fires, ASP206 treats every non-test file
    // as shell).
    let core_declaration: CoreDeclaration =
        match resolve_core_declaration(&workspace_dir, core_config_opt.as_deref()) {
            Ok(Some(declaration)) => declaration,
            Ok(None) => {
                eprintln!(
                    "aspergillus-rust-gate: input error: no functional-core declaration found \
                     (looked for {} and no --core-config); ASP205/ASP206 need one — declare \
                     `core_paths = []` for a workspace with no pure core",
                    default_core_config_path(&workspace_dir).display()
                );
                return ExitCode::from(2);
            }
            Err(why) => {
                eprintln!("aspergillus-rust-gate: input error: {why}");
                return ExitCode::from(2);
            }
        };
    eprintln!(
        "aspergillus-rust-gate: read core declaration from {} ({} path pattern(s))",
        core_declaration.source_path.display(),
        core_declaration.path_count
    );

    // Resolve the rule directory at run time: the `--rules` argument when
    // given, otherwise `CARGO_MANIFEST_DIR/ast-grep-rules` (cargo sets that
    // variable for `cargo run`). When neither is available, fail with an
    // input error naming both. The gate never falls back to a compiled-in
    // path.
    let rules_dir: Option<PathBuf> = rules_dir_opt.map(PathBuf::from).or_else(|| {
        std::env::var("CARGO_MANIFEST_DIR")
            .ok()
            .map(|dir| PathBuf::from(dir).join("ast-grep-rules"))
    });
    let rules = match rules_dir {
        Some(dir) => match load_rules(&dir) {
            Ok(rules) => rules,
            Err(why) => {
                eprintln!("aspergillus-rust-gate: input error: {why}");
                return ExitCode::from(2);
            }
        },
        None => {
            eprintln!("aspergillus-rust-gate: input error: no --rules argument and no CARGO_MANIFEST_DIR environment variable available");
            return ExitCode::from(2);
        }
    };

    let (mut findings, scanned) =
        match scan_workspace(&rules, &workspace_dir, &excludes, &core_declaration) {
            Ok(result) => result,
            Err(why) => {
                eprintln!("aspergillus-rust-gate: input error: {why}");
                return ExitCode::from(2);
            }
        };

    match clippy::clippy_findings(&workspace_dir) {
        Ok(hits) => findings.extend(hits.into_iter().filter(|f| !excludes.is_match(&f.path))),
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
/// Extract the optional `--core-config <file>` argument from `args`,
/// returning the declaration file's path (when present) and the
/// remaining arguments in their original order. A `--core-config` without
/// a value is an input error.
fn take_core_config(args: Vec<String>) -> Result<(Option<PathBuf>, Vec<String>), String> {
    let mut core_config: Option<PathBuf> = None;
    let mut rest: Vec<String> = Vec::new();
    let mut i = 0;
    while i < args.len() {
        if args[i] == "--core-config" {
            let value = args
                .get(i + 1)
                .cloned()
                .ok_or_else(|| "--core-config needs a FILE argument".to_string())?;
            core_config = Some(PathBuf::from(value));
            i += 2;
        } else {
            rest.push(args[i].clone());
            i += 1;
        }
    }
    Ok((core_config, rest))
}

/// Extract the optional `--rules <dir>` argument from `args`, returning
/// the rule directory (when present) and the remaining arguments in their
/// original order. A `--rules` without a value is an input error.
fn take_rules(args: Vec<String>) -> Result<(Option<String>, Vec<String>), String> {
    let mut rules_dir: Option<String> = None;
    let mut rest: Vec<String> = Vec::new();
    let mut i = 0;
    while i < args.len() {
        if args[i] == "--rules" {
            let value = args
                .get(i + 1)
                .cloned()
                .ok_or_else(|| "--rules needs a DIR argument".to_string())?;
            rules_dir = Some(value);
            i += 2;
        } else {
            rest.push(args[i].clone());
            i += 1;
        }
    }
    Ok((rules_dir, rest))
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

/// Every ast-grep finding across the workspace's Rust source files, and
/// how many files were scanned.
///
/// ASP205 and ASP206 (`purity::impure_function_findings`,
/// `purity::mixed_io_logic_findings`) only run over a file inside the
/// declared functional core: I/O in the imperative shell is legal. ASP202
/// (`purity::assertion_density_findings`) is not core-scoped — Rust has no
/// dynamic-parameter escape hatch, so its floor applies workspace-wide.
fn scan_workspace(
    rules: &[RuleConfig<SupportLang>],
    workspace_dir: &Path,
    excludes: &globset::GlobSet,
    core_declaration: &CoreDeclaration,
) -> Result<(Vec<Finding>, usize), String> {
    let files = rust_source_files(workspace_dir, excludes);
    let mut findings = Vec::new();
    for path in &files {
        let source =
            std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
        let relative = path.strip_prefix(workspace_dir).unwrap_or(path);
        let shown = relative.to_string_lossy().into_owned();
        findings.extend(source_findings(rules, &source).into_iter().map(
            |(line, rule_id, blocking)| Finding {
                path: shown.clone(),
                line,
                rule_id,
                blocking,
            },
        ));
        // ASP204 (unbounded loops) is not core-scoped: a `loop {}` or
        // `while true {}` with no reachable break has no determinable bound
        // anywhere in the tree, core or shell.
        for (line, rule_id, blocking) in loops::unbounded_loop_findings(&source) {
            findings.push(Finding {
                path: shown.clone(),
                line,
                rule_id: rule_id.to_string(),
                blocking,
            });
        }
        let is_core = core_declaration.is_core(relative);
        // ASP202 (assertion density) is scoped to the imperative shell: a
        // pure, fully-typed core function earns its correctness statically,
        // so the runtime-assert floor applies only outside the declared
        // core. It also exempts test code — both `#[test]`/`#[cfg(test)]`
        // functions (via the per-function `is_test` signal) and any file
        // under a crate-level `tests/` directory (an integration test and
        // its helpers are test infrastructure, not shell debt), matching
        // ASP206's `is_test_path` exemption.
        if !is_core && !is_test_path(relative) {
            for (line, rule_id, blocking) in purity::assertion_density_findings(&source) {
                findings.push(Finding {
                    path: shown.clone(),
                    line,
                    rule_id: rule_id.to_string(),
                    blocking,
                });
            }
        }
        // ASP205 (impure function) fires inside the declared functional
        // core: I/O in the core is the finding.
        if is_core {
            for (line, rule_id, blocking) in purity::impure_function_findings(&source) {
                findings.push(Finding {
                    path: shown.clone(),
                    line,
                    rule_id: rule_id.to_string(),
                    blocking,
                });
            }
        }
        // ASP206 (mixed I/O + logic) fires in the imperative SHELL — a
        // non-core, non-test-path file: a thin shell holds no logic, so a
        // shell function mixing I/O with logic is the finding. An empty
        // core (`core_paths = []`) makes every non-test file shell.
        if !is_core && !is_test_path(relative) {
            for (line, rule_id, blocking) in purity::mixed_io_logic_findings(&source) {
                findings.push(Finding {
                    path: shown.clone(),
                    line,
                    rule_id: rule_id.to_string(),
                    blocking,
                });
            }
        }
    }
    Ok((findings, files.len()))
}

/// Whether `relative` is a test-only source path: a Cargo integration-test
/// or any file under a `tests/` directory. ASP206 exempts these, as the
/// Python sibling exempts `test_` code — a test's I/O-and-logic mix is the
/// test, not shell debt to lift into the core.
fn is_test_path(relative: &Path) -> bool {
    relative.components().any(|c| c.as_os_str() == "tests")
}
