//! The Aspergillus Rust gate's functional core.
//!
//! This module holds the pure computation: given already-loaded ast-grep
//! rules and an already-read source string, which findings does the source
//! carry? No file, no process, and no exit code appears here — those live
//! in the binary at `src/bin/aspergillus_rust_gate.rs` and in
//! `src/clippy.rs`.

use ast_grep_config::{RuleConfig, Severity};
use ast_grep_language::{LanguageExt, SupportLang};

pub mod clippy;
pub mod core_declaration;
pub mod duplicate_types;
pub mod duplicates;
pub mod loops;
pub mod purity;
pub mod tupling;
pub mod worker_wrapper;
pub mod workspace;

/// One finding: a rule id at one 1-based line of one file, and whether the
/// rule that raised it is blocking.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Finding {
    /// The file, relative to the scanned workspace root.
    pub path: String,
    /// The 1-based line.
    pub line: usize,
    /// The rule id, e.g. `ASP203`.
    pub rule_id: String,
    /// Whether a finding in this rule fails the run.
    pub blocking: bool,
}

impl Finding {
    /// The gate's output line: `path:line: ASPnnn`.
    pub fn render(&self) -> String {
        format!("{}:{}: {}", self.path, self.line, self.rule_id)
    }
}

/// An ast-grep `severity: error` finding fails the run; every other
/// severity (`hint`, `info`, `warning`) reports but does not.
fn ast_grep_blocking(severity: &Severity) -> bool {
    matches!(severity, Severity::Error)
}

/// Every ast-grep rule's findings in one file's already-read Rust source,
/// ordered by line then rule id.
pub fn source_findings(
    rules: &[RuleConfig<SupportLang>],
    source: &str,
) -> Vec<(usize, String, bool)> {
    let root = SupportLang::Rust.ast_grep(source);
    let mut found = Vec::new();
    for rule in rules {
        for node in root.root().find_all(&rule.matcher) {
            let line = node.start_pos().line().saturating_add(1);
            found.push((line, rule.id.clone(), ast_grep_blocking(&rule.severity)));
        }
    }
    found.sort_by(|a, b| a.0.cmp(&b.0).then_with(|| a.1.cmp(&b.1)));
    found
}

/// The exit status the gate returns for a set of findings: 0 with no
/// blocking finding, 1 with at least one.
pub fn exit_status(findings: &[Finding]) -> u8 {
    u8::from(findings.iter().any(|f| f.blocking))
}

#[cfg(test)]
mod tests {
    use super::*;
    use ast_grep_config::{from_yaml_string, GlobalRules};

    fn load(yaml: &str) -> Vec<RuleConfig<SupportLang>> {
        from_yaml_string::<SupportLang>(yaml, &GlobalRules::default()).expect("rule parses")
    }

    #[test]
    fn a_static_mut_declaration_is_a_blocking_finding() {
        let rules = load(
            "id: ASP203\nlanguage: rust\nseverity: error\nrule:\n  kind: static_item\n  has:\n    kind: mutable_specifier\n",
        );
        let source = "static mut COUNT: u32 = 0;\n";
        let found = source_findings(&rules, source);
        assert_eq!(found, vec![(1, "ASP203".to_string(), true)]);
    }

    #[test]
    fn an_immutable_static_is_not_a_finding() {
        let rules = load(
            "id: ASP203\nlanguage: rust\nseverity: error\nrule:\n  kind: static_item\n  has:\n    kind: mutable_specifier\n",
        );
        let source = "static COUNT: u32 = 0;\n";
        assert_eq!(source_findings(&rules, source), Vec::new());
    }

    #[test]
    fn a_warning_severity_rule_reports_but_does_not_block() {
        // A generic check that non-error severities report without blocking;
        // uses a throwaway rule id (ASP204 is now a gate check, not ast-grep).
        let rules =
            load("id: ASP999\nlanguage: rust\nseverity: warning\nrule:\n  kind: loop_expression\n");
        let source = "fn f() {\n    loop {\n        break;\n    }\n}\n";
        assert_eq!(
            source_findings(&rules, source),
            vec![(2, "ASP999".to_string(), false)]
        );
    }
}
