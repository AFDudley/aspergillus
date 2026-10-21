#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.4 clause C10: the file list this work
# changed, compared with the repository state before the work started,
# names no Python rule file and no TypeScript rule file. Emits
# observations only; the runner's `then` predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_rust_dup_type_check.sh
source "${SCRIPT_DIR}/lib_rust_dup_type_check.sh"

# The commit this pebble's work started from (its recorded base-sha), an
# ancestor of every commit this branch has made since.
BASE_SHA="b2a73b51c118c934c93724445e4dd0d710886600"

CHANGED="$(git -C "${REPO_ROOT}" diff --name-only "${BASE_SHA}...HEAD" 2>/dev/null || true)"

python_rule_files_changed="$(echo "${CHANGED}" | grep -cE '^python/.*rules' || true)"
typescript_rule_files_changed="$(echo "${CHANGED}" | grep -cE '^typescript/.*rules' || true)"

printf '{"python_rule_files_changed":%s,"typescript_rule_files_changed":%s}\n' \
    "${python_rule_files_changed}" "${typescript_rule_files_changed}"
