#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.4 clause C1: a throwaway workspace holds
# two crates that each declare the same concept, and a second throwaway
# workspace holds ONE crate declaring the same concept twice across two
# files. The check reports the first pair and not the second. Emits
# observations only; the runner's `then` predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_dup_type_check.sh
source "${SCRIPT_DIR}/lib_rust_dup_type_check.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

DUP_BIN="$(rust_dup_type_build)" || exit 1

# Workspace A: two DIFFERENT crates each declare `Nanos` as a one-field
# tuple struct — the same shape, differing only in the field's own type
# and visibility (mirrors the real lobaria Nanos declarations).
WS_A="${WORK}/ws-a"
rust_dup_type_write_crate "${WS_A}/crate-a" 'pub struct Nanos(i64);
'
rust_dup_type_write_crate "${WS_A}/crate-b" 'pub struct Nanos(pub u64);
'
"${DUP_BIN}" "${WS_A}" >"${WORK}/a.stdout" 2>/dev/null || true
cross_crate_pair_reported=false
grep -q ': ASP502$' "${WORK}/a.stdout" && cross_crate_pair_reported=true

# Workspace B: ONE crate declares `Nanos` twice, across two files.
WS_B="${WORK}/ws-b/crate-only"
mkdir -p "${WS_B}/src"
cat >"${WS_B}/Cargo.toml" <<EOF
[package]
name = "crate-only"
version = "0.1.0"
edition = "2021"
EOF
printf 'pub struct Nanos(i64);\n' >"${WS_B}/src/a.rs"
printf 'pub struct Nanos(pub u64);\n' >"${WS_B}/src/b.rs"
"${DUP_BIN}" "${WORK}/ws-b" >"${WORK}/b.stdout" 2>/dev/null || true
same_crate_pair_reported=false
grep -q ': ASP502$' "${WORK}/b.stdout" && same_crate_pair_reported=true

printf '{"cross_crate_pair_reported":%s,"same_crate_pair_reported":%s}\n' \
    "${cross_crate_pair_reported}" "${same_crate_pair_reported}"
