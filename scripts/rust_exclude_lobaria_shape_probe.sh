#!/usr/bin/env bash
# Acceptance oracle for asp-f4c clause C4: over the committed
# lobaria-shaped fixture, `aspergillus-rust-dup-type-check` run with
# `--exclude 'scripts/oracles/fixtures/**'` (the arguments this script
# receives) reports exactly the five production duplicate concepts and
# drops the fixture-path declarations plus the two concepts whose only
# other declaration sat among them. Emits observations only; the
# runner's `then` predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_exclude_lobaria_shape.sh
source "${SCRIPT_DIR}/lib_rust_exclude_lobaria_shape.sh"

BIN="$(rust_exclude_lobaria_build)" || exit 1
OUTPUT="$("${BIN}" "${LOBARIA_SHAPE_FIXTURE}" "$@" 2>/dev/null || true)"

# "A finding" here counts once per CONCEPT the report names — matching
# the request's own phrasing ("prints the ... Owed finding", singular,
# for a concept the check actually renders as one line per crate it
# spans). A concept counts as present when at least one of its known
# declaration sites appears in the raw `path:line: ASP502` output.
concept_present() {
    local name="$1"
    shift
    local site
    for site in "$@"; do
        local file="${site%%:*}" decl_name="${site#*:}"
        local line
        line="$(rust_exclude_lobaria_decl_line "${LOBARIA_SHAPE_FIXTURE}/${file}" "${decl_name}")"
        [ -n "${line}" ] || continue
        if [ "$(rust_exclude_lobaria_line_present "${OUTPUT}" "${file}" "${line}")" -gt 0 ]; then
            echo "true"
            return
        fi
    done
    echo "false"
}

EXPECTED_NAMES=(Bps SignedLamports TrajectoryRow Cut Run)
findings_naming_expected_concepts=0
for name in "${EXPECTED_NAMES[@]}"; do
    present="$(concept_present "${name}" "statechart/src/units.rs:${name}" "pump-strategy/src/units.rs:${name}")"
    [ "${present}" = "true" ] && findings_naming_expected_concepts=$((findings_naming_expected_concepts + 1))
done

owed_present="$(concept_present "Owed" "statechart/src/chart.rs:Owed" "scripts/oracles/fixtures/dup/owed_hole.rs:Owed")"
hole_present="$(concept_present "Hole" "statechart/src/chart.rs:Hole" "scripts/oracles/fixtures/dup/owed_hole.rs:Hole")"
findings_naming_owed_or_hole=0
[ "${owed_present}" = "true" ] && findings_naming_owed_or_hole=$((findings_naming_owed_or_hole + 1))
[ "${hole_present}" = "true" ] && findings_naming_owed_or_hole=$((findings_naming_owed_or_hole + 1))

findings_under_excluded_path="$(grep -c 'scripts/oracles/fixtures/' <<<"${OUTPUT}" || true)"

# The report's total finding count, in the same one-per-concept terms as
# `findings_naming_expected_concepts` above: every concept this run
# reports at all, out of every concept the fixture declares (the five
# expected ones plus Owed and Hole) — so a leaked Owed/Hole finding
# inflates this count rather than being invisible to it.
findings_total=$((findings_naming_expected_concepts + findings_naming_owed_or_hole))

printf '{"findings_total":%d,"findings_naming_expected_concepts":%d,"findings_under_excluded_path":%d,"findings_naming_owed_or_hole":%d}\n' \
    "${findings_total}" "${findings_naming_expected_concepts}" "${findings_under_excluded_path}" "${findings_naming_owed_or_hole}"
