#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.4 clause C6 (metamorphic, monotonicity):
# the check runs twice over the real-lobaria fixture. The second run adds
# `Nanos` to an `--allowlist` file. The second report must omit every
# `Nanos` finding and keep every other finding of the first report
# unchanged. This is a metamorphic (monotonicity) oracle: the verdict is the
# JSON `series` on stdout, NOT the exit code. `series` is
# [[allowlist_size, nanos_findings_suppressed], ...]; it is non-decreasing iff
# allowlisting the pair suppresses exactly it and keeps every other finding.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_dup_type_check.sh
source "${SCRIPT_DIR}/lib_rust_dup_type_check.sh"

SHA="${1:-${LOBARIA_REFERENCE_SHA}}"
FIXTURE="$(rust_dup_type_lobaria_fixture "${SHA}")"

DUP_BIN="$(rust_dup_type_build)" || exit 1
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

FIRST="${WORK}/first.txt"
"${DUP_BIN}" "${FIXTURE}" >"${FIRST}" 2>/dev/null || true

ALLOWLIST="${WORK}/allowlist.txt"
printf 'Nanos\n' >"${ALLOWLIST}"
SECOND="${WORK}/second.txt"
"${DUP_BIN}" "${FIXTURE}" --allowlist "${ALLOWLIST}" >"${SECOND}" 2>/dev/null || true

NANOS_PATTERN='^(statechart/src/units\.rs:251|pump-strategy/src/units\.rs:167|hold-time-curve/src/input\.rs:28): ASP502$'

nanos_lines_in_first="$(grep -cE "${NANOS_PATTERN}" "${FIRST}" || true)"
nanos_lines_in_second="$(grep -cE "${NANOS_PATTERN}" "${SECOND}" || true)"

grep -vE "${NANOS_PATTERN}" "${FIRST}" >"${WORK}/non_nanos_first.txt" || true

other_findings_preserved=true
while IFS= read -r line; do
    [ -z "${line}" ] && continue
    grep -qxF "${line}" "${SECOND}" || other_findings_preserved=false
done <"${WORK}/non_nanos_first.txt"

second_adds_nothing_new=true
while IFS= read -r line; do
    [ -z "${line}" ] && continue
    grep -qxF "${line}" "${FIRST}" || second_adds_nothing_new=false
done <"${SECOND}"

ok=false
if [ "${nanos_lines_in_first}" -eq 3 ] \
    && [ "${nanos_lines_in_second}" -eq 0 ] \
    && [ "${other_findings_preserved}" = "true" ] \
    && [ "${second_adds_nothing_new}" = "true" ]; then
    ok=true
fi

# x = allowlist size, y = Nanos findings suppressed at that size. A correct
# allowlist that suppresses the 3 Nanos findings while preserving every other
# finding makes y rise 0 -> 3 (non-decreasing => monotonicity PASS); any
# violation makes the series fall 3 -> 0 (=> monotonicity FAIL).
if [ "${ok}" = "true" ]; then
    series='[[0, 0], [1, 3]]'
else
    series='[[0, 3], [1, 0]]'
fi

printf '{"series":%s,"nanos_lines_in_first":%s,"nanos_lines_in_second":%s,"other_findings_preserved":%s,"second_adds_nothing_new":%s}\n' \
    "${series}" "${nanos_lines_in_first}" "${nanos_lines_in_second}" "${other_findings_preserved}" "${second_adds_nothing_new}"
