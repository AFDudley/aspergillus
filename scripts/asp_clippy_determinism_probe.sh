#!/usr/bin/env bash
# Prove the clippy-backed rules report a DETERMINISTIC, COMPLETE count across
# a cold and a warm cargo target dir (asp-b33).
#
# Runs the real gate over the two-crate `fixtures/ASP303-determinism` workspace
# TWICE against the SAME target dir: run1 is cold (the dir is freshly created),
# run2 is warm (run1's artifacts are cached). It counts the clippy-backed
# findings (ASP201/301/303/403/413) each run and prints them as JSON:
#
#   {"run1": N, "run2": M, "expected": K}
#
# and exits 0 iff N == M == K. The fixture has `app` depend on `leaf`, each
# with one ASP303 discard, so under the old `deny` behaviour `leaf`'s error
# aborted the build, `app` went unchecked, and the cold count (1) differed from
# expected (2). At `warn` both crates always compile and report, so cold, warm
# and repeated runs all count 2 — the equality this oracle pins.
#
# Usage: scripts/asp_clippy_determinism_probe.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/rust" || { echo '{"error":"no rust/ dir"}'; exit 3; }
FIX="fixtures/ASP303-determinism"
EXPECTED=2
[ -d "$FIX" ] || { echo '{"error":"missing determinism fixture"}'; exit 3; }

# Resolve cargo (see asp_rule_probe.sh for why the HOME-relative path first).
CARGO="$HOME/.cargo/bin/cargo"
[ -x "$CARGO" ] || CARGO=cargo

# One shared target dir for BOTH runs: run1 is cold (freshly created), run2 is
# warm (run1's artifacts cached). The gate is invoked through `cargo run` — the
# same path asp_rule_probe.sh uses — so the toolchain the gate then spawns for
# `cargo clippy` is resolved exactly as it is for every other Rust oracle.
TD="$(mktemp -d)"
trap 'rm -rf "$TD"' EXIT

countrun() {
  CARGO_TARGET_DIR="$TD" "$CARGO" run --quiet --bin aspergillus-rust-gate -- \
    "$FIX" --rules ast-grep-rules 2>/dev/null \
    | grep -cE ': ASP(201|301|303|403|413)$'
}

run1="$(countrun)"   # cold: $TD freshly created
run2="$(countrun)"   # warm: $TD now populated

printf '{"run1": %s, "run2": %s, "expected": %s}\n' "$run1" "$run2" "$EXPECTED"

[ "$run1" -eq "$run2" ] && [ "$run1" -eq "$EXPECTED" ]
