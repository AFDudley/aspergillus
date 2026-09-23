#!/usr/bin/env bash
# Acceptance oracle for asp-f4c clause C1: each of the three Rust check
# binaries accepts a repeated `--exclude <glob>` flag and runs to
# completion (exit code 0 or 1 — a report, not an argument-parse error).
# Emits observations only; the runner's `then` predicates decide
# pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_exclude.sh
source "${SCRIPT_DIR}/lib_rust_exclude.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

mapfile -t BINS < <(rust_exclude_build_all) || exit 1
GATE="${BINS[0]}"
DUPCHECK="${BINS[1]}"
DUPTYPE="${BINS[2]}"

rust_exclude_write_layered_fixture "${WORK}/fixture"

accepted=0
for bin in "${GATE}" "${DUPCHECK}" "${DUPTYPE}"; do
    "${bin}" "${WORK}/fixture" --exclude 'alpha/**' --exclude 'beta/**' >/dev/null 2>&1
    status=$?
    # Exit 0 (clean) or 1 (findings reported) both mean the binary ran to
    # completion; exit 2 is this binary's own argument-parse-error code.
    if [ "${status}" -eq 0 ] || [ "${status}" -eq 1 ]; then
        accepted=$((accepted + 1))
    fi
done

printf '{"binaries_accepting_repeated_exclude":%d}\n' "${accepted}"
