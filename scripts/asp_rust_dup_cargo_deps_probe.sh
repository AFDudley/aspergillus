#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.3 clause C6: cargo builds the duplicate-
# function check from this repository, and its dependency graph carries
# the three named ast-grep libraries (ast-grep-core, ast-grep-config,
# ast-grep-language). Emits observations only; the runner's `then`
# predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_dup_check.sh
source "${SCRIPT_DIR}/lib_rust_dup_check.sh"

cargo build --manifest-path "${DUP_MANIFEST}" --offline -q --bin aspergillus-rust-dup-check
cargo_build_exit=$?

astgrep_crates_in_graph="$(
    cargo tree --manifest-path "${DUP_MANIFEST}" --offline -e normal --prefix none \
        --package aspergillus-rust-gate 2>/dev/null \
        | awk '{print $1}' \
        | grep -E '^ast-grep-(core|config|language)$' \
        | sort -u \
        | grep -c . || true
)"

printf '{"cargo_build_exit":%s,"astgrep_crates_in_graph":%s}\n' \
    "${cargo_build_exit}" "${astgrep_crates_in_graph}"
