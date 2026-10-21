#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.4 clause C4: the check runs over the
# real-lobaria fixture and never names `Refused`, `Carried`, `Hit` or
# `Finding` — four real lobaria names that repeat across files without
# sharing a shape (see rust/fixtures/lobaria-<sha>/PROVENANCE.md). Emits
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

# The real, verbatim line each file declares one of the four excluded
# names on (see PROVENANCE.md) — known in advance because the fixture's
# `.rs` files are unedited copies of the named lobaria commit.
EXCLUDED=(
    "statechart/src/chart.rs:86: ASP502"
    "chart/src/generate.rs:33: ASP502"
    "shell/src/drive.rs:63: ASP502"
    "chart/src/contract.rs:63: ASP502"
    "backtest/src/simulate.rs:79: ASP502"
    "chart/src/vocabulary_io.rs:57: ASP502"
    "chart/src/vocabulary_io.rs:66: ASP502"
)

findings_naming_refused_carried_hit_finding=0
for line in "${EXCLUDED[@]}"; do
    if grep -qxF "${line}" "${OUT}"; then
        findings_naming_refused_carried_hit_finding=$((findings_naming_refused_carried_hit_finding + 1))
    fi
done

total_findings="$(grep -cE ': ASP502$' "${OUT}" || true)"

printf '{"findings_naming_refused_carried_hit_finding":%s,"total_findings":%s}\n' \
    "${findings_naming_refused_carried_hit_finding}" "${total_findings}"
