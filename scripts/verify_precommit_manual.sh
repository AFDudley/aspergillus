#!/usr/bin/env bash
# Acceptance oracle for asp-3c8: proves the manual-stage pre-commit gate
# passes on a clean checkout, and that the eslint/prettier hooks still
# catch a real error. Builds a detached worktree from the current branch
# tip so the check runs against the committed state, not the live tree.
set -euo pipefail

mode="${1:-}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src_sha="$(git -C "$repo_root" rev-parse HEAD)"

scratch_dir="$repo_root/.scratch"
mkdir -p "$scratch_dir"
workdir="$(mktemp -d "$scratch_dir/verify-precommit.XXXXXX")"

cleanup() {
  git -C "$repo_root" worktree remove --force "$workdir" >/dev/null 2>&1 || true
  rm -rf "$workdir"
}
trap cleanup EXIT

git -C "$repo_root" worktree add --detach --quiet "$workdir" "$src_sha"

cd "$workdir"
npm install --no-audit --no-fund >/dev/null 2>&1

# Reads the `files:` regex pre-commit uses to select files for a given
# local hook id, straight from .pre-commit-config.yaml. Keeps the oracle's
# file count tied to the same filter the real hook applies.
hook_files_regex() {
  local hook_id="$1"
  awk -v id="$hook_id" '
    $0 ~ "id: *" id "$" { found=1 }
    found && /files:/ {
      sub(/^ *files: */, "");
      print;
      exit
    }
  ' .pre-commit-config.yaml
}

count_matching_tracked_files() {
  local regex="$1"
  git ls-files | grep -cE "$regex" || true
}

case "$mode" in
  --full-run)
    set +e
    pre-commit run --all-files --hook-stage manual >/dev/null 2>&1
    pre_commit_exit_code=$?
    set -e
    jq -n --argjson code "$pre_commit_exit_code" '{pre_commit_exit_code: $code}'
    ;;

  --prettier-clean)
    before_status="$(git status --porcelain)"
    set +e
    pre-commit run --all-files --hook-stage manual prettier >/dev/null 2>&1
    prettier_exit_code=$?
    set -e
    after_status="$(git status --porcelain)"
    modified_tracked_files=0
    if [ "$before_status" != "$after_status" ]; then
      modified_tracked_files="$(git diff --name-only | wc -l | tr -d ' ')"
    fi
    jq -n \
      --argjson code "$prettier_exit_code" \
      --argjson modified "$modified_tracked_files" \
      '{prettier_exit_code: $code, modified_tracked_files: $modified}'
    ;;

  --eslint-catches-error)
    regex="$(hook_files_regex eslint)"
    clean_files_checked="$(count_matching_tracked_files "$regex")"
    probe=typescript/cli/src/_asp3c8_lint_probe.ts
    cat > "$probe" <<'EOF'
export function asp3c8LintProbe(): number {
  const unusedVar = 42;
  return 1;
}
EOF
    git add "$probe"
    set +e
    pre-commit run --all-files --hook-stage manual eslint >/dev/null 2>&1
    eslint_exit_code_with_error=$?
    set -e
    jq -n \
      --argjson checked "$clean_files_checked" \
      --argjson code "$eslint_exit_code_with_error" \
      '{clean_files_checked: $checked, eslint_exit_code_with_error: $code}'
    ;;

  --prettier-catches-misformat)
    regex="$(hook_files_regex prettier)"
    clean_files_checked="$(count_matching_tracked_files "$regex")"
    probe=typescript/cli/src/_asp3c8_fmt_probe.ts
    cat > "$probe" <<'EOF'
export function   asp3c8FmtProbe( ) {
    return    1;
}
EOF
    git add "$probe"
    set +e
    pre-commit run --all-files --hook-stage manual prettier >/dev/null 2>&1
    prettier_exit_code_with_misformat=$?
    set -e
    jq -n \
      --argjson checked "$clean_files_checked" \
      --argjson code "$prettier_exit_code_with_misformat" \
      '{clean_files_checked: $checked, prettier_exit_code_with_misformat: $code}'
    ;;

  *)
    echo "usage: $(basename "$0") --full-run|--prettier-clean|--eslint-catches-error|--prettier-catches-misformat" >&2
    exit 64
    ;;
esac
