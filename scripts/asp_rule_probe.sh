#!/usr/bin/env bash
# Grade one Aspergillus Rust rule against its committed fixture pair.
#
# Builds and runs the real gate (or the dedicated dup binary) over
# rust/fixtures/<RULE>/<KIND> and asserts the operator contract:
#   violating   -> the rule fires (`path:line: ASPnnn`) AND the run exits 1
#   satisfying  -> the rule is silent for ASPnnn AND the run exits 0
# Exits 0 iff the expectation holds, so it drops straight into a spec_oracle
# `command` acceptance_test. Resolves everything relative to the repo root, so
# the same invocation reproduces under any checkout of `integrated`.
#
# Usage: scripts/asp_rule_probe.sh ASPnnn violating|satisfying
set -u
RULE="${1:?usage: asp_rule_probe.sh ASPnnn violating|satisfying}"
KIND="${2:?usage: asp_rule_probe.sh ASPnnn violating|satisfying}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/rust" || { echo "no rust/ under $ROOT"; exit 3; }
FIX="fixtures/$RULE/$KIND"
[ -d "$FIX" ] || { echo "missing fixture $FIX"; exit 3; }
# Resolve cargo. The spec_oracle child env sanitizes PATH (cargo is not on it)
# but symlinks `.cargo`/`.rustup` into a scratch HOME via
# EXOPHIAL_ORACLE_DATA_DIRS, so the toolchain is reachable by its HOME-relative
# absolute path; fall back to a bare `cargo` on PATH for a plain shell.
CARGO="$HOME/.cargo/bin/cargo"
[ -x "$CARGO" ] || CARGO=cargo

case "$RULE" in
  ASP501) BIN=aspergillus-rust-dup-check;      ARGS=("$FIX");;
  ASP502) BIN=aspergillus-rust-dup-type-check; ARGS=("$FIX");;
  *)      BIN=aspergillus-rust-gate;           ARGS=("$FIX" --rules ast-grep-rules);;
esac

out="$("$CARGO" run --quiet --bin "$BIN" -- "${ARGS[@]}" 2>/dev/null)"
ec=$?
hits="$(printf '%s\n' "$out" | grep -cE ": ${RULE}\$")"

if [ "$KIND" = violating ]; then
  if [ "$ec" -eq 1 ] && [ "$hits" -ge 1 ]; then exit 0; fi
  echo "$RULE/violating: expected fire+exit1, got exit=$ec ${RULE}_hits=$hits"; exit 1
else
  if [ "$ec" -eq 0 ] && [ "$hits" -eq 0 ]; then exit 0; fi
  echo "$RULE/satisfying: expected silent+exit0, got exit=$ec ${RULE}_hits=$hits"; exit 1
fi
