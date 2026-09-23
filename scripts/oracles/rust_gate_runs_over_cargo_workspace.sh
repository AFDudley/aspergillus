#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.1 clause C1: a throwaway Cargo workspace runs
# the Aspergillus Rust checks over its own crate with cargo, and the run
# reads the workspace's source files. Emits observations only; the runner's
# `then` predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_gate.sh
source "${SCRIPT_DIR}/lib_rust_gate.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

rust_gate_write_fixture "${WORK}/fixture" "$(rust_gate_clean_lib_rs)"

STDERR_LOG="${WORK}/gate.stderr"
cargo run --manifest-path "${GATE_MANIFEST}" --offline -q -- "${WORK}/fixture" \
    >"${WORK}/gate.stdout" 2>"${STDERR_LOG}"

scanned="$(grep -oE 'scanned [0-9]+ source file' "${STDERR_LOG}" | grep -oE '[0-9]+' || echo 0)"
linked="$(grep -cE '^ast-grep-(core|config|language) = ' "${GATE_MANIFEST}")"

printf '{"source_files_scanned":%s,"ast_grep_crates_linked":%s,"driven_by_cargo":true}\n' \
    "${scanned}" "${linked}"
