#!/usr/bin/env bash
# Acceptance oracle for asp-ce6.3 clause C8: the existing Python duplicate
# report still runs on a Python file that holds two copies of one function,
# and still names that duplicate group. Proves the new Rust check did not
# disturb `aspergillus check-duplicates`. Emits observations only; the
# runner's `then` predicates decide pass/fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

cat >"${WORK}/duplicated.py" <<'EOF'
def compute_one(first, second):
    total = first + second
    scaled = total * 2
    result = scaled + 1
    return result


def compute_two(left, right):
    total = left + right
    scaled = total * 2
    result = scaled + 1
    return result
EOF

json_out="$(cd "${REPO_ROOT}" && uv run --directory python aspergillus check-duplicates "${WORK}/duplicated.py" --min-lines 3 --json)"

python_group_count="$(python3 -c "
import json, sys
groups = json.loads(sys.argv[1])
print(len(groups))
" "${json_out}" 2>/dev/null || echo 0)"

printf '{"python_group_count":%s}\n' "${python_group_count}"
