#!/usr/bin/env bash
# Acceptance oracle for pebble asp-fd1.2 (ASP412 FsmEdgeDuration): runs the
# REAL `fixit lint` CLI, using this repo's own [tool.fixit] config, against a
# fixture containing the disallowed edge-duration shape (an enum-dispatch
# transition body directly calling an LLM/subprocess entrypoint instead of
# writing a durable marker and returning). Emits one stdout_json object; it
# judges nothing itself (see docs/ORACLES.md) -- the derived spec's `then`
# predicates own the verdict.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE_DIR="$(mktemp -d "${REPO_ROOT}/python/.asp412_fixture.XXXXXX")"
trap 'rm -rf "${FIXTURE_DIR}"' EXIT

FIXTURE_FILE="${FIXTURE_DIR}/edge_violation.py"
cat >"${FIXTURE_FILE}" <<'PYEOF'
from enum import Enum


class Status(Enum):
    NEEDS_SPEC = 1
    READY = 2


def integrate_edge(status: Status, ctx):
    if status == Status.NEEDS_SPEC:
        result = Transport().complete(prompt="derive spec")
        ctx.mark_integrated(result)
    elif status == Status.READY:
        ctx.mark_integrated(None)
PYEOF

RELATIVE_FIXTURE="$(realpath --relative-to="${REPO_ROOT}/python" "${FIXTURE_FILE}")"

set +e
LINT_OUTPUT="$(uv run --directory "${REPO_ROOT}/python" fixit lint "${RELATIVE_FIXTURE}" 2>&1)"
FIXIT_EXIT_CODE=$?
set -e

VIOLATION_REPORTED="False"
if printf '%s' "${LINT_OUTPUT}" | grep -q "FsmEdgeDuration"; then
  VIOLATION_REPORTED="True"
fi

FIXIT_EXIT_CODE="${FIXIT_EXIT_CODE}" VIOLATION_REPORTED="${VIOLATION_REPORTED}" python3 -c '
import json
import os

print(
    json.dumps(
        {
            "violation_reported": os.environ["VIOLATION_REPORTED"] == "True",
            "fixit_exit_code": int(os.environ["FIXIT_EXIT_CODE"]),
        }
    )
)
'
