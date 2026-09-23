//! The Aspergillus Rust gate's clippy shell.
//!
//! Runs `cargo clippy` as a subprocess over a workspace and turns its JSON
//! diagnostics into `Finding`s. The mapping from a clippy lint to an ASP
//! id, the lint level the gate forces, and the subprocess call itself all
//! live here — the imperative shell, kept apart from the pure core above.

use std::path::Path;
use std::process::Command;

use crate::Finding;

/// The clippy lints the gate forces on, the level it forces them to, and
/// the ASP id each reports as. Every lint the gate forces is at `deny`, so
/// every one reports as `error` (blocking).
const FORCED_LINTS: &[(&str, &str, &str)] = &[
    ("clippy::too_many_lines", "deny", "ASP201"),
    ("clippy::unwrap_used", "deny", "ASP301"),
    ("clippy::expect_used", "deny", "ASP301"),
    ("clippy::panic", "deny", "ASP301"),
    ("clippy::redundant_closure", "deny", "ASP403"),
];

/// Run `cargo clippy` over `workspace_dir` with the forced lints above, and
/// return the findings it reports, mapped from clippy's lint codes to ASP
/// ids. An `Err` means `cargo clippy` itself could not run (e.g. the
/// directory holds no `Cargo.toml`); a clippy diagnostic is always
/// reported as a `Finding`, never as an `Err`.
pub fn clippy_findings(workspace_dir: &Path) -> Result<Vec<Finding>, String> {
    let mut args = vec![
        "clippy".to_string(),
        "--all-targets".to_string(),
        "--message-format=json".to_string(),
        "--".to_string(),
    ];
    for (lint, level, _) in FORCED_LINTS {
        args.push(format!("-{}", cap_flag(level)));
        args.push((*lint).to_string());
    }
    let output = Command::new("cargo")
        .args(&args)
        .current_dir(workspace_dir)
        .output()
        .map_err(|e| format!("cargo clippy: {e}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    Ok(parse_messages(&stdout))
}

fn cap_flag(level: &str) -> &'static str {
    if level == "deny" {
        "D"
    } else {
        "W"
    }
}

fn lint_to_asp(code: &str) -> Option<&'static str> {
    FORCED_LINTS
        .iter()
        .find(|(lint, _, _)| *lint == code)
        .map(|(_, _, asp)| *asp)
}

/// Parse cargo's `--message-format=json` stream (one JSON object per
/// stdout line) into findings for the lints this gate forces on. Any other
/// diagnostic — a compiler warning, a clippy lint this gate does not
/// force — is not this gate's concern and is skipped; it is never reported
/// under an ASP id it does not own.
fn parse_messages(stdout: &str) -> Vec<Finding> {
    let mut findings = Vec::new();
    for line in stdout.lines() {
        let Ok(value) = serde_json::from_str::<serde_json::Value>(line) else {
            continue;
        };
        if value.get("reason").and_then(|r| r.as_str()) != Some("compiler-message") {
            continue;
        }
        let Some(message) = value.get("message") else {
            continue;
        };
        let Some(code) = message
            .get("code")
            .and_then(|c| c.get("code"))
            .and_then(|c| c.as_str())
        else {
            continue;
        };
        let Some(rule_id) = lint_to_asp(code) else {
            continue;
        };
        let blocking = message.get("level").and_then(|l| l.as_str()) == Some("error");
        let Some(spans) = message.get("spans").and_then(|s| s.as_array()) else {
            continue;
        };
        let Some(span) = spans
            .iter()
            .find(|s| s.get("is_primary").and_then(|p| p.as_bool()) == Some(true))
        else {
            continue;
        };
        let Some(file_name) = span.get("file_name").and_then(|f| f.as_str()) else {
            continue;
        };
        let Some(line_start) = span.get("line_start").and_then(|l| l.as_u64()) else {
            continue;
        };
        findings.push(Finding {
            path: file_name.to_string(),
            line: line_start as usize,
            rule_id: rule_id.to_string(),
            blocking,
        });
    }
    findings
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_forced_lint_maps_to_its_asp_id_and_blocking_level() {
        let line = r#"{"reason":"compiler-message","message":{"code":{"code":"clippy::unwrap_used"},"level":"error","spans":[{"is_primary":true,"file_name":"src/lib.rs","line_start":3}]}}"#;
        let findings = parse_messages(line);
        assert_eq!(
            findings,
            vec![Finding {
                path: "src/lib.rs".to_string(),
                line: 3,
                rule_id: "ASP301".to_string(),
                blocking: true,
            }]
        );
    }

    #[test]
    fn an_unmapped_lint_is_skipped() {
        let line = r#"{"reason":"compiler-message","message":{"code":{"code":"clippy::needless_return"},"level":"warning","spans":[{"is_primary":true,"file_name":"src/lib.rs","line_start":3}]}}"#;
        assert_eq!(parse_messages(line), Vec::new());
    }
}
