#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.4 clause C9: with `python3` and `node`
# truly absent from PATH — not merely shadowed — the check still reports
# findings over the real-lobaria fixture. Builds first with the real PATH
# (building needs cargo/rustc, not python or node; that is not the
# behavior under test here). Emits observations only; the runner's `then`
# predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_dup_type_check.sh
source "${SCRIPT_DIR}/lib_rust_dup_type_check.sh"

SHA="${1:-${LOBARIA_REFERENCE_SHA}}"
FIXTURE="$(rust_dup_type_lobaria_fixture "${SHA}")"

DUP_BIN="$(rust_dup_type_build)" || exit 1

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

NO_PY_NODE_PATH="$(rust_dup_type_path_without "${WORK}" python python3 node npm)"

python3_on_path=true
PATH="${NO_PY_NODE_PATH}" command -v python3 >/dev/null 2>&1 || python3_on_path=false
node_on_path=true
PATH="${NO_PY_NODE_PATH}" command -v node >/dev/null 2>&1 || node_on_path=false

OUT="${WORK}/dup_type.stdout"
PATH="${NO_PY_NODE_PATH}" "${DUP_BIN}" "${FIXTURE}" >"${OUT}" 2>/dev/null || true
findings_reported="$(grep -cE ': ASP502$' "${OUT}" || true)"

printf '{"python3_on_path":%s,"node_on_path":%s,"findings_reported":%s}\n' \
    "${python3_on_path}" "${node_on_path}" "${findings_reported}"
