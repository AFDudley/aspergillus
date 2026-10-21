//! The Aspergillus Rust gate's clippy shell.
//!
//! Runs `cargo clippy` as a subprocess over a workspace and turns its JSON
//! diagnostics into `Finding`s. The mapping from a clippy lint to an ASP
//! id, the blocking severity the gate assigns it, and the subprocess call
//! itself all live here — the imperative shell, kept apart from the pure
//! core above.
//!
//! The forced lints are passed at `warn`, not `deny`, for a DETERMINISTIC,
//! COMPLETE diagnostic stream. Two cargo behaviours drive that choice.
//! First, a `deny`d lint is emitted as an `error`, which makes the crate
//! FAIL to build: cargo then never checks the crates that depend on it, so
//! their diagnostics are dropped and a cold run reports FEWER findings than
//! a warm one (the asp-b33 undercount). At `warn` every crate compiles, so
//! every crate — and every crate downstream of it — is checked and reports.
//! Second, cargo CACHES a unit's warnings and REPLAYS them (verbatim, in
//! the JSON stream) on a later run when the unit is unchanged; it does NOT
//! replay a build error. So at `warn` a warm or already-checked target dir
//! re-emits exactly the same diagnostics a cold one does, and the gate's
//! counts are identical across cold, warm and repeated runs. The gate no
//! longer trusts clippy's emitted level for blocking: it assigns each
//! forced lint its OWN severity (see [`FORCED_LINTS`]).

use std::path::Path;
use std::process::Command;

use crate::Finding;

/// The clippy lints the gate forces on, whether a hit BLOCKS the run, and
/// the ASP id each reports as. Every forced lint is enabled at `warn` on
/// the command line (so no crate fails to build and cargo can cache and
/// replay the diagnostic — see the module docs); the `blocking` column is
/// the gate's OWN severity for the rule, independent of the `warning` level
/// clippy then emits. All five clippy-backed rules block.
const FORCED_LINTS: &[(&str, bool, &str)] = &[
    ("clippy::too_many_lines", true, "ASP201"),
    ("clippy::unwrap_used", true, "ASP301"),
    ("clippy::expect_used", true, "ASP301"),
    ("clippy::panic", true, "ASP301"),
    ("clippy::redundant_closure", true, "ASP403"),
    // ASP303: a fallible `Result` swallowed into a success sentinel. Both
    // the `let _ = <Result>` discard (clippy::let_underscore_must_use) and
    // a bare must-use `Result` expression statement (rustc's
    // unused_must_use) drop the error before a caller can observe it.
    // Blocking so the discard fails the run, not merely warns.
    ("clippy::let_underscore_must_use", true, "ASP303"),
    ("unused_must_use", true, "ASP303"),
    // ASP413 (FsmEnumDispatchExhaustive): a `_` wildcard arm over an
    // enum-typed match defeats the compiler's exhaustiveness check — adding
    // a variant later silently falls through instead of failing to compile.
    // Blocking so enum dispatch must list its variants.
    ("clippy::wildcard_enum_match_arm", true, "ASP413"),
];

/// Run `cargo clippy` over `workspace_dir` with the forced lints above, and
/// return the findings it reports, mapped from clippy's lint codes to ASP
/// ids. An `Err` means `cargo clippy` itself could not run (e.g. the
/// directory holds no `Cargo.toml`); a clippy diagnostic is always
/// reported as a `Finding`, never as an `Err`.
///
/// Every forced lint is passed at `-W` (warn): a warned lint never fails a
/// crate's build, so cargo checks the whole workspace and caches+replays
/// each unit's diagnostics, making the finding set identical on a cold,
/// warm or repeated target dir (see the module docs).
pub fn clippy_findings(workspace_dir: &Path) -> Result<Vec<Finding>, String> {
    let mut args = vec![
        "clippy".to_string(),
        "--all-targets".to_string(),
        "--message-format=json".to_string(),
        "--".to_string(),
    ];
    for (lint, _, _) in FORCED_LINTS {
        args.push("-W".to_string());
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

/// The ASP id and gate-assigned blocking severity for a clippy lint code,
/// or `None` when the gate does not force that lint. The severity is the
/// gate's own (the [`FORCED_LINTS`] `blocking` column), NOT the `warning`
/// level clippy emits under `-W`.
fn lint_to_finding(code: &str) -> Option<(&'static str, bool)> {
    FORCED_LINTS
        .iter()
        .find(|(lint, _, _)| *lint == code)
        .map(|(_, blocking, asp)| (*asp, *blocking))
}

/// Parse cargo's `--message-format=json` stream (one JSON object per
/// stdout line) into findings for the lints this gate forces on. Any other
/// diagnostic — a compiler warning, a clippy lint this gate does not
/// force — is not this gate's concern and is skipped; it is never reported
/// under an ASP id it does not own. A forced lint's blocking severity is
/// the gate's own, not the `warning` level clippy emits it at under `-W`.
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
        let Some((rule_id, blocking)) = lint_to_finding(code) else {
            continue;
        };
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
    fn a_warned_forced_lint_still_blocks_under_its_gate_severity() {
        // Under `-W` clippy emits the lint at `warning`, yet the gate
        // assigns ASP301 its own blocking severity — the finding still
        // blocks, decoupled from clippy's emitted level.
        let line = r#"{"reason":"compiler-message","message":{"code":{"code":"clippy::unwrap_used"},"level":"warning","spans":[{"is_primary":true,"file_name":"src/lib.rs","line_start":3}]}}"#;
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
    fn both_must_use_discards_map_to_asp303() {
        // The clippy `let _ =` discard and rustc's bare-statement
        // unused_must_use both surface as ASP303, both blocking, even though
        // `-W` emits them at `warning` level.
        let clippy_discard = r#"{"reason":"compiler-message","message":{"code":{"code":"clippy::let_underscore_must_use"},"level":"warning","spans":[{"is_primary":true,"file_name":"src/lib.rs","line_start":7}]}}"#;
        let bare_discard = r#"{"reason":"compiler-message","message":{"code":{"code":"unused_must_use"},"level":"warning","spans":[{"is_primary":true,"file_name":"src/lib.rs","line_start":11}]}}"#;
        assert_eq!(
            parse_messages(&format!("{clippy_discard}\n{bare_discard}")),
            vec![
                Finding {
                    path: "src/lib.rs".to_string(),
                    line: 7,
                    rule_id: "ASP303".to_string(),
                    blocking: true,
                },
                Finding {
                    path: "src/lib.rs".to_string(),
                    line: 11,
                    rule_id: "ASP303".to_string(),
                    blocking: true,
                },
            ]
        );
    }

    #[test]
    fn an_unmapped_lint_is_skipped() {
        let line = r#"{"reason":"compiler-message","message":{"code":{"code":"clippy::needless_return"},"level":"warning","spans":[{"is_primary":true,"file_name":"src/lib.rs","line_start":3}]}}"#;
        assert_eq!(parse_messages(line), Vec::new());
    }
}
