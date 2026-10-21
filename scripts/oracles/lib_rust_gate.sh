#!/usr/bin/env bash
# Shared setup for the Rust gate acceptance oracles: locates the repo, builds
# the gate binary once, and writes throwaway fixture workspaces. Each oracle
# entrypoint sources this file; it judges nothing itself, it only sets up
# the real crate and the real fixtures the oracle then observes.
set -uo pipefail

# The cargo/rustc toolchain (and bun, used by a sibling oracle) install under
# the user's home, not a system bin dir. Aspergillus's own acceptance gate runs
# each oracle in a hermetic child env whose HOME is exposed read-through to the
# real toolchain dirs but whose PATH carries only uv/git/bash + system dirs, so
# make cargo reachable by name here. In a real consumer's shell these dirs are
# already on PATH, so prepending them is a harmless no-op there.
export PATH="${HOME}/.cargo/bin:${HOME}/.bun/bin:${PATH}"

rust_gate_repo_root() {
    cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

REPO_ROOT="$(rust_gate_repo_root)"
GATE_MANIFEST="${REPO_ROOT}/rust/Cargo.toml"

# Builds the gate binary (debug profile) and prints its path on stdout.
rust_gate_build() {
    cargo build --manifest-path "${GATE_MANIFEST}" --offline -q 1>&2 || return 1
    echo "${REPO_ROOT}/rust/target/debug/aspergillus-rust-gate"
}

# Writes a minimal Cargo package at $1 with src/lib.rs contents $2.
rust_gate_write_fixture() {
    local dir="$1" lib_rs="$2"
    mkdir -p "${dir}/src"
    cat >"${dir}/Cargo.toml" <<'EOF'
[package]
name = "fixture"
version = "0.1.0"
edition = "2021"
EOF
    printf '%s' "${lib_rs}" >"${dir}/src/lib.rs"
}

# A source body with no rule violation.
rust_gate_clean_lib_rs() {
    cat <<'EOF'
pub fn add(a: i32, b: i32) -> i32 {
    a + b
}
EOF
}

# A source body that trips the blocking ast-grep rule ASP203 (a `static
# mut` declaration) and the blocking clippy-backed rule ASP301 (`.unwrap()`).
rust_gate_dirty_lib_rs() {
    cat <<'EOF'
static mut COUNTER: u32 = 0;

pub fn bad(x: Option<i32>) -> i32 {
    x.unwrap()
}
EOF
}

# A source body that trips only a clippy-backed rule (ASP301 via
# `.expect(...)`), with no ast-grep-matched construct.
rust_gate_clippy_only_lib_rs() {
    cat <<'EOF'
pub fn bad(x: Option<i32>) -> i32 {
    x.expect("missing value")
}
EOF
}
