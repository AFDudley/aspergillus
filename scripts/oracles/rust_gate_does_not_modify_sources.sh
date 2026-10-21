#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.1 clause C9: after the checks run over a
# sample crate that has findings, not one of the crate's files has changed.
# Emits observations only; the runner's `then` predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_gate.sh
source "${SCRIPT_DIR}/lib_rust_gate.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

GATE_BIN="$(rust_gate_build)" || exit 1
rust_gate_write_fixture "${WORK}/fixture" "$(rust_gate_dirty_lib_rs)"

# Hash only the files the fixture ships (its Cargo.toml and its source),
# never `target/` or a generated `Cargo.lock` — those are normal cargo
# build byproducts of running clippy at all, not a rewrite of the
# consumer's own code, which is what "report only" means here.
before_hash="$(cd "${WORK}/fixture" && sha256sum Cargo.toml src/lib.rs)"

"${GATE_BIN}" "${WORK}/fixture" >"${WORK}/gate.stdout" 2>/dev/null || true
findings="$(wc -l <"${WORK}/gate.stdout" | tr -d '[:space:]')"

after_hash="$(cd "${WORK}/fixture" && sha256sum Cargo.toml src/lib.rs)"

files_changed_by_run=0
if [ "${before_hash}" != "${after_hash}" ]; then
    files_changed_by_run=1
fi

printf '{"findings":%s,"files_changed_by_run":%s}\n' "${findings}" "${files_changed_by_run}"
