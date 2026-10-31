#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.1 clause C4: a sample crate that breaks no
# rule makes the run end in success and report nothing. Emits observations
# only; the runner's `then` predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_gate.sh
source "${SCRIPT_DIR}/lib_rust_gate.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

GATE_BIN="$(rust_gate_build)" || exit 1
rust_gate_write_fixture "${WORK}/fixture" "$(rust_gate_clean_lib_rs)"

"${GATE_BIN}" "${WORK}/fixture" >"${WORK}/gate.stdout" 2>/dev/null
gate_exit_code=$?

findings="$(wc -l <"${WORK}/gate.stdout" | tr -d '[:space:]')"

printf '{"findings":%s,"gate_exit_code":%s}\n' "${findings}" "${gate_exit_code}"
