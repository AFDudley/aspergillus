#!/usr/bin/env bash
# Acceptance oracle for asp-f4c clause C5: over the same committed
# lobaria-shaped fixture, `aspergillus-rust-dup-type-check` run with NO
# `--exclude` flag reports the fixture-path declarations and both Owed
# and Hole — the new flag removes nothing by default. Emits observations
# only; the runner's `then` predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_exclude_lobaria_shape.sh
source "${SCRIPT_DIR}/lib_rust_exclude_lobaria_shape.sh"

BIN="$(rust_exclude_lobaria_build)" || exit 1
OUTPUT="$("${BIN}" "${LOBARIA_SHAPE_FIXTURE}" 2>/dev/null || true)"

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

owed_present="$(concept_present "Owed" "statechart/src/chart.rs:Owed" "scripts/oracles/fixtures/dup/owed_hole.rs:Owed")"
hole_present="$(concept_present "Hole" "statechart/src/chart.rs:Hole" "scripts/oracles/fixtures/dup/owed_hole.rs:Hole")"
findings_naming_owed_or_hole=0
[ "${owed_present}" = "true" ] && findings_naming_owed_or_hole=$((findings_naming_owed_or_hole + 1))
[ "${hole_present}" = "true" ] && findings_naming_owed_or_hole=$((findings_naming_owed_or_hole + 1))

findings_under_excluded_path="$(grep -c 'scripts/oracles/fixtures/' <<<"${OUTPUT}" || true)"

printf '{"findings_under_excluded_path":%d,"findings_naming_owed_or_hole":%d}\n' \
    "${findings_under_excluded_path}" "${findings_naming_owed_or_hole}"
