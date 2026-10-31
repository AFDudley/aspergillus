#!/usr/bin/env bash
# Acceptance oracle for asp-f4c clause C8: running any of the three Rust
# check binaries with `--exclude` over the shared layered fixture never
# rewrites a scanned (or excluded) source file. Records a checksum of
# every fixture file before the run, runs `aspergillus-rust-dup-type-check`
# with `--exclude 'alpha/**'`, and re-checksums afterward. Emits
# observations only; the runner's `then` predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_exclude.sh
source "${SCRIPT_DIR}/lib_rust_exclude.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

mapfile -t BINS < <(rust_exclude_build_all) || exit 1
DUPTYPE="${BINS[2]}"

rust_exclude_write_layered_fixture "${WORK}/fixture"

before="$(find "${WORK}/fixture" -type f -exec sha256sum {} + | sort)"
output="$("${DUPTYPE}" "${WORK}/fixture" --exclude 'alpha/**' 2>/dev/null || true)"
after="$(find "${WORK}/fixture" -type f -exec sha256sum {} + | sort)"

files_changed_during_run=0
if [ "${before}" != "${after}" ]; then
    files_changed_during_run=1
fi
findings_printed="$(grep -cE ': ASP502$' <<<"${output}" || true)"

printf '{"files_changed_during_run":%d,"findings_printed":%d}\n' \
    "${files_changed_during_run}" "${findings_printed}"
