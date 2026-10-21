#!/usr/bin/env bash
# Acceptance oracle for asp-f4c clause C2: run each of the three Rust
# check binaries with `--exclude 'alpha/**'` over the shared layered
# fixture. `alpha/dup/` declares the same duplicated `Marker` type,
# function body, and `static mut` as `kept-a/` and `kept-b/` (which are
# never excluded); the concept still spans two OTHER crates once `alpha`
# drops out, so every binary must still report it, and must report
# nothing from `alpha/`. Emits observations only; the runner's `then`
# predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_exclude.sh
source "${SCRIPT_DIR}/lib_rust_exclude.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

mapfile -t BINS < <(rust_exclude_build_all) || exit 1
GATE="${BINS[0]}"
DUPCHECK="${BINS[1]}"
DUPTYPE="${BINS[2]}"

rust_exclude_write_layered_fixture "${WORK}/fixture"

reporting_unexcluded=0
reporting_excluded=0
for bin in "${GATE}" "${DUPCHECK}" "${DUPTYPE}"; do
    output="$("${bin}" "${WORK}/fixture" --exclude 'alpha/**' 2>/dev/null || true)"
    if grep -qE '^(kept-a|kept-b|beta/dup)/' <<<"${output}"; then
        reporting_unexcluded=$((reporting_unexcluded + 1))
    fi
    if grep -qE '^alpha/' <<<"${output}"; then
        reporting_excluded=$((reporting_excluded + 1))
    fi
done

printf '{"binaries_reporting_unexcluded_declaration":%d,"binaries_reporting_excluded_declaration":%d}\n' \
    "${reporting_unexcluded}" "${reporting_excluded}"
