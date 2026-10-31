#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.1 clause C8: a sample crate that only the
# shipped clippy settings object to is reported by the checks, showing
# clippy runs alongside the ast-grep rule files. Emits observations only;
# the runner's `then` predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_gate.sh
source "${SCRIPT_DIR}/lib_rust_gate.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

GATE_BIN="$(rust_gate_build)" || exit 1
rust_gate_write_fixture "${WORK}/fixture" "$(rust_gate_clippy_only_lib_rs)"

"${GATE_BIN}" "${WORK}/fixture" >"${WORK}/gate.stdout" 2>/dev/null || true

clippy_findings="$(grep -cE ': ASP301$' "${WORK}/gate.stdout" || true)"

printf '{"clippy_findings":%s}\n' "${clippy_findings}"
