#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.4 clause C3: the check runs over the
# real-lobaria fixture (rust/fixtures/lobaria-<sha>/, a verbatim copy of
# the named commit's own files — see its PROVENANCE.md) and reports
# `Receipt` at all three real lobaria locations the request names. Emits
# observations only; the runner's `then` predicates decide pass/fail.
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

# The real, verbatim line each file declares `Receipt` on (see
# PROVENANCE.md) — known in advance because the fixture's `.rs` files are
# unedited copies of the named lobaria commit.
EXPECTED=(
    "statechart/src/edge.rs:26: ASP502"
    "pump-strategy/src/units.rs:188: ASP502"
    "hold-time-curve/src/input.rs:22: ASP502"
)

receipt_declarations_reported=0
receipt_expected_paths_missing=0
for line in "${EXPECTED[@]}"; do
    if grep -qxF "${line}" "${OUT}"; then
        receipt_declarations_reported=$((receipt_declarations_reported + 1))
    else
        receipt_expected_paths_missing=$((receipt_expected_paths_missing + 1))
    fi
done

printf '{"receipt_declarations_reported":%s,"receipt_expected_paths_missing":%s}\n' \
    "${receipt_declarations_reported}" "${receipt_expected_paths_missing}"
