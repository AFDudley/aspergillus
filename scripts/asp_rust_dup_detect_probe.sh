#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.3 clause C2: a Rust file holds two functions
# with the same body shape but different names and different variable
# names - the check reports them as one duplicate pair. A second file
# holds two functions that differ only by one literal value - the check
# reports no pair for those. Emits observations only; the runner's `then`
# predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_dup_check.sh
source "${SCRIPT_DIR}/lib_rust_dup_check.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

DUP_BIN="$(rust_dup_build)" || exit 1

mkdir -p "${WORK}/fixture/src"
cat >"${WORK}/fixture/Cargo.toml" <<'EOF'
[package]
name = "fixture"
version = "0.1.0"
edition = "2021"
EOF

# Same shape, different name and variables: one duplicate pair.
{
    rust_dup_one_copy_lib_rs
    echo
    rust_dup_other_copy_lib_rs
} >"${WORK}/fixture/src/matching_pair.rs"

# Same shape except one literal (2 vs 3): not a duplicate pair.
{
    rust_dup_shaped_fn "literal_low" "a" "b" "2"
    echo
    rust_dup_shaped_fn "literal_high" "c" "d" "3"
} >"${WORK}/fixture/src/differing_literal_pair.rs"

"${DUP_BIN}" "${WORK}/fixture" >"${WORK}/dup.stdout" 2>/dev/null || true

matching_pair_findings="$(grep -c 'matching_pair.rs' "${WORK}/dup.stdout" || true)"
differing_literal_findings="$(grep -c 'differing_literal_pair.rs' "${WORK}/dup.stdout" || true)"
reported_pair_count=0
if [ "${matching_pair_findings}" -ge 2 ]; then
    reported_pair_count=$((reported_pair_count + 1))
fi

printf '{"reported_pair_count":%s,"differing_literal_findings":%s}\n' \
    "${reported_pair_count}" "${differing_literal_findings}"
