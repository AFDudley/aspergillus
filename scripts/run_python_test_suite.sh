#!/usr/bin/env bash
# Acceptance oracle: runs the project's whole Python test suite (the exact
# command a developer or CI gate runs) and surfaces its exit code. Emits
# nothing but the test runner's own output -- the derived spec observes
# `exit_code` directly, so this script judges nothing itself.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

uv run --directory "${REPO_ROOT}/python" pytest tests -q
exit $?
