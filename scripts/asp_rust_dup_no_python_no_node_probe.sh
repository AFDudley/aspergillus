#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.3 clause C7: with `python`, `python3`,
# `node` and `npm` replaced by stand-ins that fail and record each call,
# the check still reports a known duplicate pair, and the stand-ins record
# no call. Emits observations only; the runner's `then` predicates decide
# pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_dup_check.sh
source "${SCRIPT_DIR}/lib_rust_dup_check.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

# Build with the real PATH first: building the check needs cargo/rustc,
# not python or node, but building is not the behavior under test here.
DUP_BIN="$(rust_dup_build)" || exit 1
rust_dup_write_crate "${WORK}/crate-a" "$(rust_dup_one_copy_lib_rs)"
rust_dup_write_crate "${WORK}/crate-b" "$(rust_dup_other_copy_lib_rs)"

STUB_LOG="${WORK}/stub_calls.log"
STUB_DIR="${WORK}/stub_bin"
mkdir -p "${STUB_DIR}"
for stub in python python3 node npm; do
    cat >"${STUB_DIR}/${stub}" <<EOF
#!/usr/bin/env bash
echo "${stub} \$*" >>"${STUB_LOG}"
exit 1
EOF
    chmod +x "${STUB_DIR}/${stub}"
done
: >"${STUB_LOG}"

# The stand-in directory goes first on PATH, so it shadows any real
# python/python3/node/npm the host has installed.
PATH="${STUB_DIR}:${PATH}" "${DUP_BIN}" "${WORK}" >"${WORK}/dup.stdout" 2>/dev/null || true

finding_line_count="$(grep -c . "${WORK}/dup.stdout" || true)"
stub_invocation_count="$(grep -c . "${STUB_LOG}" || true)"

printf '{"finding_line_count":%s,"stub_invocation_count":%s}\n' \
    "${finding_line_count}" "${stub_invocation_count}"
