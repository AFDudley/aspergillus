#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.1 clause C12: the existing Python rule tests
# and the existing TypeScript rule tests both still run to completion with
# zero failures, so adding the Rust gate changes neither. Emits observations
# only; the runner's `then` predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

python_out="$(cd "${REPO_ROOT}" && uv run --directory python pytest tests -q 2>&1)"
python_failed="$(grep -oE '[0-9]+ failed' <<<"${python_out}" | grep -oE '[0-9]+' | head -1)"
python_passed="$(grep -oE '[0-9]+ passed' <<<"${python_out}" | grep -oE '[0-9]+' | head -1)"
python_failed="${python_failed:-0}"
python_passed="${python_passed:-0}"
python_tests_run=$((python_passed + python_failed))

BUN="$(command -v bun || echo "${HOME}/.bun/bin/bun")"
ts_out="$(cd "${REPO_ROOT}" && "${BUN}" test typescript/rules typescript/layouts typescript/errors 2>&1)"
ts_failed="$(grep -oE '[0-9]+ fail' <<<"${ts_out}" | grep -oE '[0-9]+' | head -1)"
ts_passed="$(grep -oE '[0-9]+ pass' <<<"${ts_out}" | grep -oE '[0-9]+' | head -1)"
ts_failed="${ts_failed:-0}"
ts_passed="${ts_passed:-0}"
ts_tests_run=$((ts_passed + ts_failed))

printf '{"python_rule_test_failures":%s,"typescript_rule_test_failures":%s,"python_rule_tests_run":%s,"typescript_rule_tests_run":%s}\n' \
    "${python_failed}" "${ts_failed}" "${python_tests_run}" "${ts_tests_run}"
