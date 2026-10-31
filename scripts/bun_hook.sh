#!/usr/bin/env bash
# Pre-commit entry for the eslint and prettier hooks in .pre-commit-config.yaml.
# Usage: scripts/bun_hook.sh <tool> [args...]
#
# The hooks run a tool from the root node_modules/.bin. A fresh checkout has
# no node_modules: a subtree-sync scratch tree, a CI clone, or a new worktree.
# So this script installs node_modules from the committed bun.lock first.
# When node_modules already matches bun.lock, bun install changes nothing.
# The hooks set require_serial, so only one bun install runs at a time.
set -euo pipefail

tool="$1"
shift
bun install --frozen-lockfile --ignore-scripts
exec bun "node_modules/.bin/$tool" "$@"
