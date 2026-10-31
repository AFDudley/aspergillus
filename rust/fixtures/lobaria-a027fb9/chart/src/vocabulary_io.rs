//! The vocabulary gate: which retired words a source file contains, and the
//! files, the glossary, and the printing around it.
//!
//! Concept: This module names every retired word that a source file still
//! contains, and moves the bytes of the repository into that pure check.
//!
//! The retired words are the backticked words in the first column of the
//! glossary's Retired table (`docs/glossary.md`, the single source of the
//! retired vocabulary). A source file is read by [`crate::rust_reader`]; a
//! finding is one retired word at one line. The working directory is the
//! repository root, as for the chart gate. The graded files are every `*.rs`
//! tracked by git, excluding `.worktrees/`, `.scratch/` and `target/`.
//! Documentation is not graded: the glossary and the process name the
//! retired words in order to retire them. An unreadable glossary or file is
//! an error, never a pass. The gate returns findings, never a bare verdict,
//! so a failure names its referent (`docs/process.md`, "Every gate is
//! executable").

use std::path::PathBuf;
use std::process::Command;

use crate::rust_reader::{self, ReadRefused};

/// Types the shell is permitted to use; the core-types gate grades them, so
/// this gate does not.
const SHELL_TYPES: [&str; 3] = ["String", "u64", "i64"];

/// The glossary that holds the Retired table.
pub const GLOSSARY: &str = "docs/glossary.md";

const EXCLUDED_PREFIXES: [&str; 3] = [".worktrees/", ".scratch/", "target/"];

/// Why the glossary yields no retired words.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum GlossaryRefused {
    /// The glossary has no `## Retired` section.
    NoRetiredSection,
    /// The Retired section has no backticked word to retire.
    NoWords,
}

impl std::fmt::Display for GlossaryRefused {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            GlossaryRefused::NoRetiredSection => {
                write!(f, "docs/glossary.md has no '## Retired' section")
            }
            GlossaryRefused::NoWords => {
                write!(f, "docs/glossary.md Retired table yielded no words")
            }
        }
    }
}

/// One retired word at one line of one file.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Finding {
    /// 1-based line.
    pub line: usize,
    /// The retired word.
    pub word: String,
}

/// One finding, with the file it is in.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Hit {
    /// The file, relative to the repository root.
    pub path: PathBuf,
    /// The finding.
    pub finding: Finding,
}

/// The backticked tokens of one table cell, in order.
fn backticked(cell: &str) -> Vec<&str> {
    let mut tokens = Vec::new();
    let mut rest = cell;
    while let Some((_, after_open)) = rest.split_once('`') {
        match after_open.split_once('`') {
            Some(("", _)) => rest = after_open,
            Some((token, after_close)) => {
                tokens.push(token);
                rest = after_close;
            }
            None => break,
        }
    }
    tokens
}

/// The retired words of the glossary's Retired table, in order.
///
/// A retired word is a backticked token in the first column of a table row
/// under the `## Retired` heading. The header row and the shell-permitted
/// type names are not words.
pub fn retired_words(glossary: &str) -> Result<Vec<String>, GlossaryRefused> {
    let (_, section) = glossary
        .split_once("## Retired")
        .ok_or(GlossaryRefused::NoRetiredSection)?;
    let words: Vec<String> = section
        .lines()
        .filter(|line| line.starts_with('|') && !line.starts_with("|---"))
        .filter_map(|line| line.split('|').nth(1))
        .filter(|first| !first.trim().starts_with("retired word"))
        .flat_map(backticked)
        .filter(|token| !SHELL_TYPES.contains(token))
        .map(str::to_owned)
        .collect();
    if words.is_empty() {
        return Err(GlossaryRefused::NoWords);
    }
    Ok(words)
}

/// Every retired word in the source, in source order.
pub fn findings(retired: &[String], source: &str) -> Result<Vec<Finding>, ReadRefused> {
    Ok(rust_reader::words(source)?
        .into_iter()
        .filter(|w| retired.contains(&w.text))
        .map(|w| Finding {
            line: w.line,
            word: w.text,
        })
        .collect())
}

/// The count of findings per retired word, in order of first occurrence.
pub fn tally<'a>(words: impl Iterator<Item = &'a str>) -> Vec<(String, usize)> {
    let mut counts: Vec<(String, usize)> = Vec::new();
    for word in words {
        match counts.iter_mut().find(|(w, _)| w == word) {
            Some((_, n)) => *n = n.saturating_add(1),
            None => counts.push((word.to_owned(), 1)),
        }
    }
    counts
}

/// The summary line the gate prints on stderr: the total, the number of
/// distinct words, and each word's count, largest first (ties keep the order
/// of first occurrence).
pub fn summary(total: usize, counts: &[(String, usize)]) -> String {
    let mut ordered: Vec<&(String, usize)> = counts.iter().collect();
    ordered.sort_by(|a, b| b.1.cmp(&a.1));
    let detail = ordered
        .iter()
        .map(|(word, n)| format!("{word}={n}"))
        .collect::<Vec<_>>()
        .join(", ");
    let head = format!(
        "vocabulary gate: {total} finding(s) across {} retired word(s)",
        counts.len()
    );
    if detail.is_empty() {
        head
    } else {
        format!("{head}: {detail}")
    }
}

/// The retired words in `docs/glossary.md`.
pub fn glossary_words() -> Result<Vec<String>, String> {
    let text = std::fs::read_to_string(GLOSSARY).map_err(|e| format!("{GLOSSARY}: {e}"))?;
    retired_words(&text).map_err(|e| e.to_string())
}

/// Every tracked Rust source file this gate grades, in git's order.
pub fn graded_files() -> Result<Vec<PathBuf>, String> {
    let out = Command::new("git")
        .args(["ls-files", "*.rs"])
        .output()
        .map_err(|e| format!("git ls-files: {e}"))?;
    if !out.status.success() {
        return Err(format!(
            "git ls-files failed: {}",
            String::from_utf8_lossy(&out.stderr)
        ));
    }
    Ok(String::from_utf8_lossy(&out.stdout)
        .lines()
        .filter(|rel| !rel.is_empty() && !EXCLUDED_PREFIXES.iter().any(|p| rel.starts_with(p)))
        .map(PathBuf::from)
        .collect())
}

/// Every finding in the files, in file order then source order.
pub fn scan(retired: &[String], files: &[PathBuf]) -> Result<Vec<Hit>, String> {
    let mut hits = Vec::new();
    for path in files {
        let bytes = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
        let source = String::from_utf8_lossy(&bytes);
        let found = findings(retired, &source)
            .map_err(|r| format!("{}: line {}: {}", path.display(), r.line, r.why))?;
        hits.extend(found.into_iter().map(|finding| Hit {
            path: path.clone(),
            finding,
        }));
    }
    Ok(hits)
}
