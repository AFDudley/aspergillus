#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.3 clause C3: a Cargo workspace holds only
# functions with different bodies, so the check reports nothing. Emits
# observations only; the runner's `then` predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_dup_check.sh
source "${SCRIPT_DIR}/lib_rust_dup_check.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

DUP_BIN="$(rust_dup_build)" || exit 1
rust_dup_write_crate "${WORK}/fixture" "$(rust_dup_clean_lib_rs)"

"${DUP_BIN}" "${WORK}/fixture" >"${WORK}/dup.stdout" 2>/dev/null || true

finding_line_count="$(grep -c . "${WORK}/dup.stdout" || true)"

printf '{"finding_line_count":%s}\n' "${finding_line_count}"
