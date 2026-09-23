#!/usr/bin/env bash
# Acceptance oracle for asp-f4c clause C3: `aspergillus-rust-dup-type-check`
# run with TWO `--exclude` flags (`alpha/**` and `beta/**`) reports
# nothing from either folder, and still reports the `Marker` duplicate
# that spans the two never-excluded crates `kept-a`/`kept-b`. Emits
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

output="$("${DUPTYPE}" "${WORK}/fixture" --exclude 'alpha/**' --exclude 'beta/**' 2>/dev/null || true)"

findings_under_first_glob="$(grep -cE '^alpha/' <<<"${output}" || true)"
findings_under_second_glob="$(grep -cE '^beta/' <<<"${output}" || true)"
findings_outside_both_globs="$(grep -cE '^(kept-a|kept-b)/' <<<"${output}" || true)"

printf '{"findings_under_first_glob":%d,"findings_under_second_glob":%d,"findings_outside_both_globs":%d}\n' \
    "${findings_under_first_glob}" "${findings_under_second_glob}" "${findings_outside_both_globs}"
