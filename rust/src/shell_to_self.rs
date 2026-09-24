//! ASP409: shell-to-self — a crate invoking its own package via subprocess.
//!
//! `python/src/aspergillus/rules/catalog/shell_to_self.py` (`ShellToSelf`)
//! flags implementation code that spawns its own package
//! (`subprocess.run([sys.executable, "-m", own_package, ..])`) instead of
//! importing the function and calling it: a subprocess boundary to your
//! own code is a stringly-typed seam (argv in, exit code out) that drifts
//! and can be pointed elsewhere.
//!
//! Rust's refined intent targets the two cargo-native self-invocation
//! shapes. Shape A: `Command::new("cargo")` whose builder chain is
//! `cargo run -p <self>` — a `run` verb with a `-p`/`--package` selector
//! naming THIS crate's own package (the owning `Cargo.toml`'s
//! `[package].name`), re-driving your own package through a stringly
//! cargo boundary. A `cargo build -p ..` (a compile step) and a
//! `cargo run -p <sibling>` (a legitimate black-box harness over a
//! different workspace crate) are deliberately NOT flagged. Shape B:
//! `Command::new(<CARGO_BIN_EXE_*>)` — spawning your own compiled binary
//! by its cargo-provided path from inside implementation code.
//!
//! Scope: implementation code only. A `build.rs` (which legitimately
//! drives cargo) and any `tests/`/`#[cfg(test)]` scope (where a
//! `CARGO_BIN_EXE_*` spawn IS the correct end-to-end boundary to the
//! shipped artifact — see ASP410) are exempt; the gate does not call this
//! analyzer for `build.rs` or a `tests/` path, and a `#[cfg(test)]` scope
//! is skipped here.

use ast_grep_core::{Doc, Node};
use ast_grep_language::{LanguageExt, SupportLang};

/// Every shell-to-self subprocess spawn in one file's Rust source,
/// outside any `#[cfg(test)]` scope. `own_package` is the name declared
/// by the file's owning `Cargo.toml` (`[package].name`), or `None` when
/// it cannot be resolved — in which case the `cargo run -p <self>` shape
/// cannot be confirmed and does not fire. Blocking.
pub fn shell_to_self_findings(
    source: &str,
    own_package: Option<&str>,
) -> Vec<(usize, &'static str, bool)> {
    let root = SupportLang::Rust.ast_grep(source);
    let mut findings = Vec::new();
    for node in root.root().dfs() {
        if node.kind() != "call_expression" || !is_command_new(&node) {
            continue;
        }
        if in_test_scope(&node) {
            continue;
        }
        let Some(first) = first_argument(&node) else {
            continue;
        };
        // Shape B: spawning this crate's own compiled binary by its
        // cargo-provided `CARGO_BIN_EXE_*` path — you hold the binary and
        // shell it instead of calling the function.
        let hit = if first.text().contains("CARGO_BIN_EXE") {
            true
        } else {
            // Shape A: `cargo run -p <self>` — re-executing your own
            // package through a stringly cargo boundary. `cargo build -p`
            // (a compile step) and `cargo run -p <sibling>` (a black-box
            // harness over a different crate) are NOT self-invocation.
            first.kind() == "string_literal"
                && string_content(&first) == "cargo"
                && chain_runs_own_package(&node, own_package)
        };
        if hit {
            findings.push((node.start_pos().line().saturating_add(1), "ASP409", true));
        }
    }
    findings.sort_by(|a, b| a.0.cmp(&b.0));
    findings
}

/// Whether the call's callee is `Command::new` (bare or path-qualified,
/// e.g. `std::process::Command::new`), and not a same-suffix impostor like
/// `MyCommand::new`.
fn is_command_new<D: Doc>(call: &Node<'_, D>) -> bool {
    call.field("function").is_some_and(|func| {
        let text = func.text();
        text.as_ref() == "Command::new" || text.ends_with("::Command::new")
    })
}

/// The first positional argument expression of a call, skipping the
/// surrounding parentheses and separators.
fn first_argument<'r, D: Doc>(call: &Node<'r, D>) -> Option<Node<'r, D>> {
    let args = call.field("arguments")?;
    for child in args.children() {
        if !matches!(child.kind().as_ref(), "(" | ")" | ",") {
            return Some(child);
        }
    }
    None
}

/// Whether the builder chain enclosing a `Command::new("cargo")` is a
/// `cargo run -p <own_package>` — a `run` verb together with a
/// `-p <self>`/`--package <self>` selector naming this crate's own
/// package. Args may be threaded through `.arg("run").arg("-p").arg(name)`
/// or `.args(["run", "-p", name])`; both appear as ordered string
/// literals in the enclosing statement's subtree. Returns `false` when
/// the owning package name is unknown (the self match cannot be made).
fn chain_runs_own_package<D: Doc>(command_new: &Node<'_, D>, own_package: Option<&str>) -> bool {
    let Some(own_package) = own_package else {
        return false;
    };
    let Some(scope) = enclosing_statement(command_new) else {
        return false;
    };
    let tokens: Vec<String> = scope
        .dfs()
        .filter(|n| n.kind() == "string_literal")
        .map(|n| string_content(&n))
        .collect();
    if !tokens.iter().any(|t| t == "run") {
        return false;
    }
    tokens.iter().enumerate().any(|(index, token)| {
        (token == "-p" || token == "--package")
            && tokens
                .get(index + 1)
                .is_some_and(|name| normalize_package(name) == normalize_package(own_package))
    })
}

/// A package name compared insensitive to the `-`/`_` distinction, which
/// cargo treats as equivalent.
fn normalize_package(name: &str) -> String {
    name.replace('-', "_")
}

/// The nearest enclosing statement (`let` binding or expression
/// statement) whose subtree holds the whole builder chain, or `None` when
/// the call is a bare fragment.
fn enclosing_statement<'r, D: Doc>(node: &Node<'r, D>) -> Option<Node<'r, D>> {
    let mut cursor = node.parent();
    while let Some(ancestor) = cursor {
        match ancestor.kind().as_ref() {
            "expression_statement" | "let_declaration" => return Some(ancestor),
            "block" | "source_file" | "function_item" => return None,
            _ => cursor = ancestor.parent(),
        }
    }
    None
}

/// The text between a string literal's quotes, or the empty string.
fn string_content<D: Doc>(literal: &Node<'_, D>) -> String {
    literal
        .children()
        .find(|c| c.kind() == "string_content")
        .map(|c| c.text().into_owned())
        .unwrap_or_default()
}

/// Whether `node` sits inside a `#[cfg(test)]`/`#[test]` scope, where a
/// `CARGO_BIN_EXE_*` spawn is the correct e2e boundary, not self-shelling.
fn in_test_scope<D: Doc>(node: &Node<'_, D>) -> bool {
    let mut cursor = node.parent();
    while let Some(ancestor) = cursor {
        if matches!(ancestor.kind().as_ref(), "function_item" | "mod_item")
            && has_test_attribute(&ancestor)
        {
            return true;
        }
        cursor = ancestor.parent();
    }
    false
}

fn has_test_attribute<D: Doc>(item: &Node<'_, D>) -> bool {
    let mut prev = item.prev();
    while let Some(sibling) = prev {
        match sibling.kind().as_ref() {
            "attribute_item" => {
                if sibling
                    .text()
                    .chars()
                    .filter(|c| !c.is_whitespace())
                    .collect::<String>()
                    .contains("test")
                {
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

#[cfg(test)]
mod tests {
    use super::*;

    fn lines(source: &str, own: Option<&str>) -> Vec<usize> {
        shell_to_self_findings(source, own)
            .into_iter()
            .map(|(line, _, _)| line)
            .collect()
    }

    #[test]
    fn flags_cargo_run_dash_p_self() {
        let src = "fn drive() {\n    let status = Command::new(\"cargo\").arg(\"run\").arg(\"-p\").arg(\"myapp\").status();\n}\n";
        assert_eq!(lines(src, Some("myapp")), vec![2]);
    }

    #[test]
    fn flags_cargo_run_self_via_args_slice_with_dash_normalization() {
        // `--package my-app` names the crate whose Cargo.toml is
        // `name = "my_app"`; the `-`/`_` distinction is cargo-equivalent.
        let src = "fn drive() {\n    Command::new(\"cargo\").args([\"run\", \"--release\", \"--package\", \"my-app\"]).output();\n}\n";
        assert_eq!(lines(src, Some("my_app")), vec![2]);
    }

    #[test]
    fn flags_cargo_bin_exe_spawn() {
        let src = "fn drive() {\n    let out = Command::new(env!(\"CARGO_BIN_EXE_myapp\")).output();\n}\n";
        assert_eq!(lines(src, Some("myapp")), vec![2]);
    }

    #[test]
    fn ignores_cargo_run_sibling_package() {
        // A black-box harness that runs a DIFFERENT workspace crate is not
        // self-invocation.
        let src = "fn drive() {\n    Command::new(\"cargo\").arg(\"run\").arg(\"-p\").arg(\"backtest\").output();\n}\n";
        assert!(lines(src, Some("backtest-oracle")).is_empty());
    }

    #[test]
    fn ignores_cargo_build_self_compile_step() {
        // Building your own package (even `-p self`) is a compile step,
        // not a logic invocation.
        let src = "fn drive() {\n    Command::new(\"cargo\").args([\"build\", \"--release\", \"-p\", \"myapp\"]).status();\n}\n";
        assert!(lines(src, Some("myapp")).is_empty());
    }

    #[test]
    fn ignores_self_run_when_owner_unknown() {
        let src = "fn drive() {\n    Command::new(\"cargo\").arg(\"run\").arg(\"-p\").arg(\"myapp\").status();\n}\n";
        assert!(lines(src, None).is_empty());
    }

    #[test]
    fn ignores_external_tool() {
        let src = "fn drive() {\n    Command::new(\"git\").arg(\"status\").status().unwrap();\n}\n";
        assert!(lines(src, Some("myapp")).is_empty());
    }

    #[test]
    fn ignores_same_suffix_impostor() {
        let src = "fn drive() {\n    MyCommand::new(\"cargo\").arg(\"run\").arg(\"-p\").arg(\"myapp\").run();\n}\n";
        assert!(lines(src, Some("myapp")).is_empty());
    }

    #[test]
    fn exempts_cfg_test_scope() {
        let src = "#[cfg(test)]\nmod tests {\n    fn e2e() {\n        Command::new(env!(\"CARGO_BIN_EXE_myapp\")).output().unwrap();\n    }\n}\n";
        assert!(lines(src, Some("myapp")).is_empty());
    }
}
