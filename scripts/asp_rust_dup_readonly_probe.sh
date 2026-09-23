#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.3 clause C5: every file of a workspace with
# a known duplicate pair is fingerprinted before and after the check runs.
# The check reports the duplicate and edits nothing. Emits observations
# only; the runner's `then` predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_dup_check.sh
source "${SCRIPT_DIR}/lib_rust_dup_check.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

DUP_BIN="$(rust_dup_build)" || exit 1
rust_dup_write_crate "${WORK}/crate-a" "$(rust_dup_one_copy_lib_rs)"
rust_dup_write_crate "${WORK}/crate-b" "$(rust_dup_other_copy_lib_rs)"

# Fingerprint only the fixture's own files, in a stable order - never a
# `target/` build byproduct.
fingerprint() {
    (cd "${WORK}" && find crate-a crate-b -type f | sort | xargs sha256sum)
}

before="$(fingerprint)"
"${DUP_BIN}" "${WORK}" >"${WORK}/dup.stdout" 2>/dev/null || true
after="$(fingerprint)"

finding_line_count="$(grep -c . "${WORK}/dup.stdout" || true)"
changed_file_count=0
if [ "${before}" != "${after}" ]; then
    changed_file_count="$(diff <(echo "${before}") <(echo "${after}") | grep -c '^[<>]' || true)"
fi

printf '{"finding_line_count":%s,"changed_file_count":%s}\n' \
    "${finding_line_count}" "${changed_file_count}"
