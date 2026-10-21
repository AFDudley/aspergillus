#!/usr/bin/env bash
# Shared setup for the two lobaria-shape `--exclude` oracles (c4, c5):
# locates the repo, builds the duplicate-type check binary, and points at
# the committed synthetic fixture `rust/fixtures/lobaria-exclude-shape/`
# (see its PROVENANCE.md). Judges nothing itself.
set -uo pipefail

export PATH="${HOME}/.cargo/bin:${PATH}"

rust_exclude_lobaria_repo_root() {
    cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

REPO_ROOT="$(rust_exclude_lobaria_repo_root)"
LOBARIA_SHAPE_FIXTURE="${REPO_ROOT}/rust/fixtures/lobaria-exclude-shape"

# Builds the duplicate-type check binary (debug profile) and prints its
# path on stdout.
rust_exclude_lobaria_build() {
    cargo build --manifest-path "${REPO_ROOT}/rust/Cargo.toml" --offline -q \
        --bin aspergillus-rust-dup-type-check 1>&2 || return 1
    echo "${REPO_ROOT}/rust/target/debug/aspergillus-rust-dup-type-check"
}

# The 1-based line `pub struct NAME` or `pub enum NAME` starts on in
# `$1`, read fresh from the committed fixture rather than hardcoded, so a
# future edit to the fixture cannot silently desync this oracle from it.
rust_exclude_lobaria_decl_line() {
    local file="$1" name="$2"
    grep -n -E "^pub (struct|enum) ${name}( |\\(|<|;|$)" "${file}" | head -1 | cut -d: -f1
}

# Counts how many lines of `$1` (the checker's raw stdout) match
# `path:LINE: ASP502` for the file `$2` and 1-based line `$3`.
rust_exclude_lobaria_line_present() {
    local output="$1" path="$2" line="$3"
    grep -c -F "${path}:${line}: ASP502" <<<"${output}"
}
