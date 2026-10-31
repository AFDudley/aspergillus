#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.4 clause C5: every line the check prints
# over the real-lobaria fixture is `path:line: ASPnnn` — a file path, a
# colon, a line number, a colon, a space, and a three-digit ASP code.
# Emits observations only; the runner's `then` predicates decide
# pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_dup_type_check.sh
source "${SCRIPT_DIR}/lib_rust_dup_type_check.sh"

SHA="${1:-${LOBARIA_REFERENCE_SHA}}"
FIXTURE="$(rust_dup_type_lobaria_fixture "${SHA}")"

DUP_BIN="$(rust_dup_type_build)" || exit 1
OUT="$(mktemp)"
trap 'rm -f "${OUT}"' EXIT
"${DUP_BIN}" "${FIXTURE}" >"${OUT}" 2>/dev/null || true

reported_lines="$(grep -c . "${OUT}" || true)"
lines_not_matching_pattern="$(grep -cvE '^.+:[0-9]+: ASP[0-9]{3}$' "${OUT}" || true)"

printf '{"reported_lines":%s,"lines_not_matching_pattern":%s}\n' \
    "${reported_lines}" "${lines_not_matching_pattern}"
