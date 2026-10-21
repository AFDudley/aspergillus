#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.4 clause C7: a throwaway copy of the
# real-lobaria fixture is made, the check runs over the copy and prints
# findings, and afterward no file of the copy was added, deleted or
# modified. Emits observations only; the runner's `then` predicates
# decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_dup_type_check.sh
source "${SCRIPT_DIR}/lib_rust_dup_type_check.sh"

SHA="${1:-${LOBARIA_REFERENCE_SHA}}"
DUP_BIN="$(rust_dup_type_build)" || exit 1

COPY="$(rust_dup_type_lobaria_copy "${SHA}")"
trap 'rm -rf "$(dirname "${COPY}")"' EXIT

BEFORE="$(mktemp)"
AFTER="$(mktemp)"
trap 'rm -f "${BEFORE}" "${AFTER}"' EXIT
(cd "${COPY}" && find . -type f -exec sha256sum {} +) | sort >"${BEFORE}"

OUT="$(mktemp)"
"${DUP_BIN}" "${COPY}" >"${OUT}" 2>/dev/null || true
findings_reported="$(grep -cE ': ASP502$' "${OUT}" || true)"

(cd "${COPY}" && find . -type f -exec sha256sum {} +) | sort >"${AFTER}"

files_modified_count="$(diff "${BEFORE}" "${AFTER}" | grep -cE '^[<>]' || true)"

printf '{"files_modified_count":%s,"findings_reported":%s}\n' \
    "${files_modified_count}" "${findings_reported}"
