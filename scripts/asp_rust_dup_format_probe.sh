#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.3 clause C4: on a workspace with a known
# duplicate pair, every printed finding line reads as a file path, a
# colon, a line number, a colon, a space, and an ASP code with three
# digits. Emits observations only; the runner's `then` predicates decide
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

finding_line_count=0
malformed_line_count=0
while IFS= read -r line; do
    [ -z "${line}" ] && continue
    finding_line_count=$((finding_line_count + 1))
    if [[ "${line}" =~ ^[^:[:space:]]+:[0-9]+:\ ASP[0-9][0-9][0-9]$ ]]; then
        :
    else
        malformed_line_count=$((malformed_line_count + 1))
    fi
done <"${WORK}/dup.stdout"

printf '{"finding_line_count":%s,"malformed_line_count":%s}\n' \
    "${finding_line_count}" "${malformed_line_count}"
