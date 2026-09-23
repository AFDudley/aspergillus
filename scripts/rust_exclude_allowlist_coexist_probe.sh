#!/usr/bin/env bash
# Acceptance oracle for asp-f4c clause C6: `aspergillus-rust-dup-type-check`
# run with BOTH `--allowlist` (naming `AllowMe`) and `--exclude 'alpha/**'`
# suppresses `AllowMe` findings by name, suppresses `alpha/`-path
# findings by path, and still reports the remaining `Marker` duplicate.
# Emits observations only; the runner's `then` predicates decide
# pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_exclude.sh
source "${SCRIPT_DIR}/lib_rust_exclude.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

mapfile -t BINS < <(rust_exclude_build_all) || exit 1
DUPTYPE="${BINS[2]}"

rust_exclude_write_layered_fixture "${WORK}/fixture"
printf 'AllowMe\n' >"${WORK}/allow.txt"

output="$("${DUPTYPE}" "${WORK}/fixture" --allowlist "${WORK}/allow.txt" --exclude 'alpha/**' 2>/dev/null || true)"

allow_me_line="$(grep -n '^pub enum AllowMe' "${WORK}/fixture/kept-a/src/lib.rs" | head -1 | cut -d: -f1)"
findings_naming_allowlisted_type=0
if [ -n "${allow_me_line}" ] && grep -q -F "kept-a/src/lib.rs:${allow_me_line}: ASP502" <<<"${output}"; then
    findings_naming_allowlisted_type=1
fi

findings_under_excluded_path="$(grep -cE '^alpha/' <<<"${output}" || true)"
remaining_findings="$(grep -cE '^(kept-a|kept-b|beta/dup)/' <<<"${output}" || true)"

printf '{"findings_naming_allowlisted_type":%d,"findings_under_excluded_path":%d,"remaining_findings":%d}\n' \
    "${findings_naming_allowlisted_type}" "${findings_under_excluded_path}" "${remaining_findings}"
