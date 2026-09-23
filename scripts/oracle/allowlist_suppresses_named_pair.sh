#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.4 clause C6 (metamorphic, monotonicity):
# the check runs twice over the real-lobaria fixture. The second run adds
# `Nanos` to an `--allowlist` file. The second report must omit every
# `Nanos` finding and keep every other finding of the first report
# unchanged. Exits non-zero if the relation does not hold — this oracle
# type carries no separate `then` clause, so its own exit code is the
# verdict. Also prints one observation object.
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

printf '{"nanos_lines_in_first":%s,"nanos_lines_in_second":%s,"other_findings_preserved":%s}\n' \
    "${nanos_lines_in_first}" "${nanos_lines_in_second}" "${other_findings_preserved}"

if [ "${nanos_lines_in_first}" -eq 3 ] \
    && [ "${nanos_lines_in_second}" -eq 0 ] \
    && [ "${other_findings_preserved}" = "true" ] \
    && [ "${second_adds_nothing_new}" = "true" ]; then
    exit 0
fi
exit 1
