#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.4 clause C8: cargo builds the check from a
# clean build directory, and the built binary's dependency tree carries
# all three ast-grep crates the request names. Emits observations only;
# the runner's `then` predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_dup_type_check.sh
source "${SCRIPT_DIR}/lib_rust_dup_type_check.sh"

CLEAN_TARGET="$(mktemp -d)"
trap 'rm -rf "${CLEAN_TARGET}"' EXIT

cargo build \
    --manifest-path "${DUP_TYPE_MANIFEST}" \
    --offline \
    --target-dir "${CLEAN_TARGET}" \
    --bin aspergillus-rust-dup-type-check \
    >"${CLEAN_TARGET}/build.log" 2>&1
cargo_build_exit=$?

tree_output="$(cargo tree \
    --manifest-path "${DUP_TYPE_MANIFEST}" \
    --offline \
    --prefix none 2>/dev/null || true)"

ast_grep_dependencies_present=0
for crate_name in ast-grep-core ast-grep-config ast-grep-language; do
    if echo "${tree_output}" | grep -qE "^${crate_name} "; then
        ast_grep_dependencies_present=$((ast_grep_dependencies_present + 1))
    fi
done

printf '{"cargo_build_exit":%s,"ast_grep_dependencies_present":%s}\n' \
    "${cargo_build_exit}" "${ast_grep_dependencies_present}"
