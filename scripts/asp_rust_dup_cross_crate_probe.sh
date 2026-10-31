#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.3 clause C1: a throwaway Cargo workspace
# holds two crates, each with one copy of the same function. The check
# reads the whole workspace, not one crate only, so the report names both
# crates. Emits observations only; the runner's `then` predicates decide
# pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_dup_check.sh
source "${SCRIPT_DIR}/lib_rust_dup_check.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

DUP_BIN="$(rust_dup_build)" || exit 1
rust_dup_write_crate "${WORK}/crate-a" "$(rust_dup_one_copy_lib_rs)"
rust_dup_write_crate "${WORK}/crate-b" "$(rust_dup_other_copy_lib_rs)"

"${DUP_BIN}" "${WORK}" >"${WORK}/dup.stdout" 2>/dev/null || true

distinct_crates_in_report="$(
    awk -F/ '{print $1}' "${WORK}/dup.stdout" | sort -u | grep -c .
)"

printf '{"distinct_crates_in_report":%s}\n' "${distinct_crates_in_report}"
