#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.1 clause C3: a sample crate that breaks a
# blocking rule (ASP203, severity error) makes the run end in failure.
# Emits observations only; the runner's `then` predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_gate.sh
source "${SCRIPT_DIR}/lib_rust_gate.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

GATE_BIN="$(rust_gate_build)" || exit 1
rust_gate_write_fixture "${WORK}/fixture" "$(rust_gate_dirty_lib_rs)"

"${GATE_BIN}" "${WORK}/fixture" >"${WORK}/gate.stdout" 2>/dev/null
gate_exit_code=$?

# ASP203 (a `static mut`) and ASP301 (clippy `unwrap_used`, forced to
# `deny`) are the gate's blocking rules; every other reported rule id is
# non-blocking. Count the blocking findings the dirty fixture produced.
blocking_findings="$(grep -cE ': (ASP203|ASP301)$' "${WORK}/gate.stdout" || true)"

printf '{"blocking_findings":%s,"gate_exit_code":%s}\n' "${blocking_findings}" "${gate_exit_code}"
