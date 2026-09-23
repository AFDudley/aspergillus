//! Reads a consumer's functional-core path declaration (imperative shell).
//!
//! ASP205 and ASP206 stay silent about I/O in the imperative shell and
//! only report it inside a path the consumer declares as the functional
//! core (mirroring the TypeScript `./layouts/*` element patterns). This
//! module is the shell around that declaration: given a path, it reads
//! and parses the file. No purity decision lives here.

use std::path::{Path, PathBuf};

use globset::{Glob, GlobSet, GlobSetBuilder};

/// A compiled functional-core path declaration: which workspace-relative
/// glob patterns count as the functional core, and where the declaration
/// was read from.
pub struct CoreDeclaration {
    pub globset: GlobSet,
    pub source_path: PathBuf,
    pub path_count: usize,
}

impl CoreDeclaration {
    /// Whether `relative_path` (workspace-relative) falls inside the
    /// declared functional core.
    pub fn is_core(&self, relative_path: &Path) -> bool {
        self.globset.is_match(relative_path)
    }
}

/// The file a consumer's functional-core declaration lives in by default,
/// when no `--core-config` argument names one: `<workspace_dir>/aspergillus.toml`.
pub fn default_core_config_path(workspace_dir: &Path) -> PathBuf {
    workspace_dir.join("aspergillus.toml")
}

/// Reads and compiles the `core_paths` array at `path` (TOML: a
/// `core_paths = ["glob", ...]` key at the document's top level). Each
/// entry is a workspace-relative, gitignore/fnmatch-style glob, the same
/// dialect `--exclude` accepts (e.g. `statechart/**`).
pub fn read_core_declaration(path: &Path) -> Result<CoreDeclaration, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let value: toml::Value =
        toml::from_str(&text).map_err(|e| format!("{}: {e}", path.display()))?;
    let patterns = value
        .get("core_paths")
        .and_then(toml::Value::as_array)
        .ok_or_else(|| format!("{}: missing a 'core_paths' array", path.display()))?;
    let mut builder = GlobSetBuilder::new();
    for pattern in patterns {
        let text = pattern
            .as_str()
            .ok_or_else(|| format!("{}: a 'core_paths' entry must be a string", path.display()))?;
        let glob = Glob::new(text).map_err(|e| format!("{}: {text}: {e}", path.display()))?;
        builder.add(glob);
    }
    let globset = builder
        .build()
        .map_err(|e| format!("{}: {e}", path.display()))?;
    Ok(CoreDeclaration {
        globset,
        source_path: path.to_path_buf(),
        path_count: patterns.len(),
    })
}

/// The declaration at `--core-config`'s value when given, otherwise the
/// default location if it exists, otherwise `None`. A malformed
/// declaration that DOES exist is an `Err`: a typo in a consumer's
/// `core_paths` must not silently disable the rules it was meant to
/// scope. The gate treats `None` (no declaration at all) as a hard input
/// error too — ASP205/ASP206 require a declaration, and a workspace with
/// no pure core states that explicitly with `core_paths = []`.
pub fn resolve_core_declaration(
    workspace_dir: &Path,
    core_config_arg: Option<&Path>,
) -> Result<Option<CoreDeclaration>, String> {
    match core_config_arg {
        Some(path) => read_core_declaration(path).map(Some),
        None => {
            let default_path = default_core_config_path(workspace_dir);
            if default_path.is_file() {
                read_core_declaration(&default_path).map(Some)
            } else {
                Ok(None)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_path_inside_a_declared_core_glob_is_core() {
        let mut builder = GlobSetBuilder::new();
        builder.add(Glob::new("statechart/**").unwrap());
        let declaration = CoreDeclaration {
            globset: builder.build().unwrap(),
            source_path: PathBuf::from("aspergillus.toml"),
            path_count: 1,
        };
        assert!(declaration.is_core(Path::new("statechart/src/chart.rs")));
        assert!(!declaration.is_core(Path::new("shell/src/machine.rs")));
    }

    #[test]
    fn an_empty_core_paths_declaration_parses_to_an_empty_core() {
        let dir = std::env::temp_dir().join("aspergillus-core-declaration-test-empty");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("aspergillus.toml"), "core_paths = []\n").unwrap();
        let declaration = resolve_core_declaration(&dir, None).unwrap().unwrap();
        assert_eq!(declaration.path_count, 0);
        // Every path is shell: no path is core, so ASP205 never fires and
        // ASP206 treats every non-test file as shell.
        assert!(!declaration.is_core(Path::new("src/lib.rs")));
        assert!(!declaration.is_core(Path::new("anything/at/all.rs")));
    }

    #[test]
    fn a_missing_default_config_resolves_to_no_declaration() {
        let dir = std::env::temp_dir().join("aspergillus-core-declaration-test-missing");
        std::fs::create_dir_all(&dir).unwrap();
        let result = resolve_core_declaration(&dir, None).unwrap();
        assert!(result.is_none());
    }

    #[test]
    fn a_present_default_config_is_read_without_a_cli_argument() {
        let dir = std::env::temp_dir().join("aspergillus-core-declaration-test-present");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("aspergillus.toml"), "core_paths = [\"src/**\"]\n").unwrap();
        let declaration = resolve_core_declaration(&dir, None).unwrap().unwrap();
        assert_eq!(declaration.path_count, 1);
        assert!(declaration.is_core(Path::new("src/lib.rs")));
    }
}
