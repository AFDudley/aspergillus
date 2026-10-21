#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.1 clause C2: every reported finding line
# reads as `path:line: ASPnnn` and no reported line reads any other way.
# Emits observations only; the runner's `then` predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_gate.sh
source "${SCRIPT_DIR}/lib_rust_gate.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

GATE_BIN="$(rust_gate_build)" || exit 1
rust_gate_write_fixture "${WORK}/fixture" "$(rust_gate_dirty_lib_rs)"

"${GATE_BIN}" "${WORK}/fixture" >"${WORK}/gate.stdout" 2>/dev/null || true

matching=0
not_matching=0
while IFS= read -r line; do
    [ -z "${line}" ] && continue
    if [[ "${line}" =~ ^[^:[:space:]]+:[0-9]+:\ ASP[0-9]+$ ]]; then
        matching=$((matching + 1))
    else
        not_matching=$((not_matching + 1))
    fi
done <"${WORK}/gate.stdout"

printf '{"finding_lines_matching_format":%s,"finding_lines_not_matching_format":%s}\n' \
    "${matching}" "${not_matching}"
