//! ASP410: in-process construction masquerading as an e2e test.
//!
//! `python/src/aspergillus/rules/catalog/in_process_e2e.py`
//! (`InProcessE2E`) flags a test that constructs the system-under-test
//! IN-PROCESS and drives its loop, then implicitly claims to be an e2e — a
//! fake gate. A genuine e2e drives the SHIPPED artifact across a real
//! subprocess / installed-CLI / network boundary, so it never exercises
//! the SUT in its own address space.
//!
//! Rust's refined intent reads the same seam through cargo's own e2e
//! convention. A genuine Rust e2e in `tests/` spawns the built binary —
//! `Command::new(env!("CARGO_BIN_EXE_<name>"))` (or `assert_cmd`'s
//! `Command`) — crossing the process boundary. The finding: a `#[test]`
//! function that is e2e-scoped (its file's name or its own name contains
//! `e2e`) under a `tests/` directory, yet spawns NO process — no
//! `Command`, no `CARGO_BIN_EXE_*`. Such a test drives the library
//! in-process while presenting as an end-to-end test.
//!
//! Conservative: only `#[test]`-family functions are considered (a helper
//! is not a test), only under a `tests/` path, and only when the e2e claim
//! is explicit in the file or function name. A test that DOES spawn a
//! process is a real e2e and stays silent.

use ast_grep_core::{Doc, Node};
use ast_grep_language::{LanguageExt, SupportLang};

/// Every e2e-scoped `#[test]` function that never crosses a process
/// boundary, in one file under a `tests/` directory. `relative_path` is
/// the file's workspace-relative path (the gate's `shown`). Blocking.
pub fn in_process_e2e_findings(
    source: &str,
    relative_path: &str,
) -> Vec<(usize, &'static str, bool)> {
    if !under_tests(relative_path) {
        return Vec::new();
    }
    let file_is_e2e = file_stem_mentions_e2e(relative_path);
    let root = SupportLang::Rust.ast_grep(source);
    let mut findings = Vec::new();
    for node in root.root().dfs() {
        if node.kind() != "function_item" || !has_test_attribute(&node) {
            continue;
        }
        let name = node
            .field("name")
            .map(|n| n.text().to_ascii_lowercase())
            .unwrap_or_default();
        if !(file_is_e2e || name.contains("e2e")) {
            continue;
        }
        let spawns = node
            .field("body")
            .is_some_and(|body| body_spawns_process(&body));
        if !spawns {
            findings.push((node.start_pos().line().saturating_add(1), "ASP410", true));
        }
    }
    findings.sort_by(|a, b| a.0.cmp(&b.0));
    findings
}

/// Whether the path has a `tests` component (a Cargo integration-test
/// tree). Splits on either separator so a lossily-rendered Windows path
/// still resolves.
fn under_tests(relative_path: &str) -> bool {
    relative_path
        .split(['/', '\\'])
        .any(|component| component == "tests")
}

/// Whether the file's stem mentions `e2e` (case-insensitive) — the file
/// presents itself as an end-to-end suite.
fn file_stem_mentions_e2e(relative_path: &str) -> bool {
    relative_path
        .rsplit(['/', '\\'])
        .next()
        .unwrap_or(relative_path)
        .to_ascii_lowercase()
        .contains("e2e")
}

/// Whether a function body crosses a process boundary: it names `Command`
/// (`std::process::Command` or `assert_cmd::Command`) or references a
/// `CARGO_BIN_EXE_*` binary path. A docstring/comment mentioning them is
/// invisible — only real identifier and string-literal nodes count.
fn body_spawns_process<D: Doc>(body: &Node<'_, D>) -> bool {
    for node in body.dfs() {
        match node.kind().as_ref() {
            "identifier" | "type_identifier" | "field_identifier" => {
                if node.text().as_ref() == "Command" {
                    return true;
                }
            }
            "string_literal" | "raw_string_literal" => {
                if node.text().contains("CARGO_BIN_EXE") {
                    return true;
                }
            }
            _ => {}
        }
    }
    false
}

/// Whether the item is preceded by a `#[test]`/`#[tokio::test]`-family
/// attribute (a test entry point), not merely a `#[cfg(test)]` gate.
fn has_test_attribute<D: Doc>(item: &Node<'_, D>) -> bool {
    let mut prev = item.prev();
    while let Some(sibling) = prev {
        match sibling.kind().as_ref() {
            "attribute_item" => {
                if attribute_is_test_entry(sibling.text().as_ref()) {
                    return true;
                }
            }
            "line_comment" | "block_comment" => {}
            _ => break,
        }
        prev = sibling.prev();
    }
    false
}

/// Whether an attribute is a test *entry point* (`#[test]`,
/// `#[tokio::test]`, `#[async_std::test]`, ..) — its whitespace-stripped
/// form ends in `test]`. A `#[cfg(test)]` gate ends in `test)]` and is not
/// a test entry point.
fn attribute_is_test_entry(text: &str) -> bool {
    text.chars()
        .filter(|c| !c.is_whitespace())
        .collect::<String>()
        .ends_with("test]")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lines(source: &str, path: &str) -> Vec<usize> {
        in_process_e2e_findings(source, path)
            .into_iter()
            .map(|(line, _, _)| line)
            .collect()
    }

    #[test]
    fn flags_e2e_file_test_without_process_boundary() {
        let src = "#[test]\nfn drives_the_flow() {\n    let mut app = App::new(cfg);\n    app.tick();\n    assert!(app.done());\n}\n";
        assert_eq!(lines(src, "tests/e2e.rs"), vec![2]);
    }

    #[test]
    fn flags_e2e_named_test_in_generic_file() {
        let src =
            "#[test]\nfn e2e_flow() {\n    let mut app = App::new(cfg);\n    app.run_once();\n}\n";
        assert_eq!(lines(src, "tests/smoke.rs"), vec![2]);
    }

    #[test]
    fn accepts_test_that_spawns_the_built_binary() {
        let src = "#[test]\nfn drives_the_flow() {\n    let out = Command::new(env!(\"CARGO_BIN_EXE_app\")).output().unwrap();\n    assert!(out.status.success());\n}\n";
        assert!(lines(src, "tests/e2e.rs").is_empty());
    }

    #[test]
    fn ignores_non_test_helper() {
        let src = "fn setup() -> App {\n    App::new(cfg)\n}\n";
        assert!(lines(src, "tests/e2e.rs").is_empty());
    }

    #[test]
    fn ignores_file_outside_tests_dir() {
        let src =
            "#[test]\nfn e2e_flow() {\n    let mut app = App::new(cfg);\n    app.tick();\n}\n";
        assert!(lines(src, "src/e2e.rs").is_empty());
    }

    #[test]
    fn ignores_non_e2e_test_in_tests_dir() {
        let src = "#[test]\nfn unit_check() {\n    let app = App::new(cfg);\n    assert_eq!(app.count(), 0);\n}\n";
        assert!(lines(src, "tests/unit.rs").is_empty());
    }
}
