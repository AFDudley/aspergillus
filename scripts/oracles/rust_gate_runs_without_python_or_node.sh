#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.1 clause C5: with python, python3, node, npm
# and npx all absent from PATH, the checks still run over a sample crate and
# still report its findings. Emits observations only; the runner's `then`
# predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_gate.sh
source "${SCRIPT_DIR}/lib_rust_gate.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

# Build with the real PATH first: building the gate needs cargo/rustc, not
# python or node, but building is not the behavior under test here.
GATE_BIN="$(rust_gate_build)" || exit 1
rust_gate_write_fixture "${WORK}/fixture" "$(rust_gate_dirty_lib_rs)"

# A PATH with every directory that carries python/python3/node/npm/npx
# removed, keeping every other directory (so cargo, rustc and clippy-driver,
# none of which are Python or Node, stay reachable).
stripped_path=""
IFS=':' read -ra dirs <<<"${PATH}"
for d in "${dirs[@]}"; do
    if [ -d "${d}" ] && ls "${d}" 2>/dev/null | grep -qE '^(python3?|node|npm|npx)$'; then
        continue
    fi
    stripped_path="${stripped_path:+${stripped_path}:}${d}"
done

python_found_on_path=false
node_found_on_path=false
if PATH="${stripped_path}" command -v python3 >/dev/null 2>&1 || PATH="${stripped_path}" command -v python >/dev/null 2>&1; then
    python_found_on_path=true
fi
if PATH="${stripped_path}" command -v node >/dev/null 2>&1 || PATH="${stripped_path}" command -v npm >/dev/null 2>&1 || PATH="${stripped_path}" command -v npx >/dev/null 2>&1; then
    node_found_on_path=true
fi

PATH="${stripped_path}" "${GATE_BIN}" "${WORK}/fixture" >"${WORK}/gate.stdout" 2>/dev/null || true
findings="$(wc -l <"${WORK}/gate.stdout" | tr -d '[:space:]')"

printf '{"python_found_on_path":%s,"node_found_on_path":%s,"findings":%s}\n' \
    "${python_found_on_path}" "${node_found_on_path}" "${findings}"
