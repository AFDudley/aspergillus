#!/usr/bin/env bash
# Shared setup for the Rust duplicate-function check's acceptance oracles:
# locates the repo, builds the check binary once, and writes throwaway
# fixture crates/workspaces. Each oracle entrypoint sources this file; it
# judges nothing itself, it only sets up the real crate and the real
# fixtures the oracle then observes.
set -uo pipefail

# The cargo/rustc toolchain installs under the user's home, not a system
# bin dir. Aspergillus's own acceptance gate runs each oracle in a hermetic
# child env whose HOME is exposed read-through to the real toolchain dirs
# but whose PATH carries only uv/git/bash + system dirs, so make cargo
# reachable by name here. In a real consumer's shell this dir is already
# on PATH, so prepending it is a harmless no-op there.
export PATH="${HOME}/.cargo/bin:${PATH}"

rust_dup_repo_root() {
    cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

REPO_ROOT="$(rust_dup_repo_root)"
DUP_MANIFEST="${REPO_ROOT}/rust/Cargo.toml"

# Builds the duplicate-function check binary (debug profile) and prints
# its path on stdout.
rust_dup_build() {
    cargo build --manifest-path "${DUP_MANIFEST}" --offline -q --bin aspergillus-rust-dup-check 1>&2 || return 1
    echo "${REPO_ROOT}/rust/target/debug/aspergillus-rust-dup-check"
}

# Writes a minimal Cargo package at $1 with src/lib.rs contents $2.
rust_dup_write_crate() {
    local dir="$1" lib_rs="$2"
    mkdir -p "${dir}/src"
    cat >"${dir}/Cargo.toml" <<EOF
[package]
name = "$(basename "${dir}")"
version = "0.1.0"
edition = "2021"
EOF
    printf '%s' "${lib_rs}" >"${dir}/src/lib.rs"
}

# One function's source, parameterized so two calls can vary its name, its
# variable names, and one literal independently while keeping the same
# body shape (5-line span, past the check's min-lines floor).
rust_dup_shaped_fn() {
    local fn_name="$1" a="$2" b="$3" literal="${4:-2}"
    cat <<EOF
pub fn ${fn_name}(${a}: i32, ${b}: i32) -> i32 {
    let sum = ${a} + ${b};
    let scaled = sum * ${literal};
    let result = scaled + 1;
    result
}
EOF
}

# A crate holding one copy of a shaped function, for the cross-crate and
# read-only/format oracles. Literal 7 is distinct from the literals
# `rust_dup_shaped_fn`'s other callers use, so this pair never accidentally
# joins a different fixture's duplicate group.
rust_dup_one_copy_lib_rs() {
    rust_dup_shaped_fn "compute_one" "first" "second" "7"
}

# A crate holding a SECOND, independently-named/variabled copy of the same
# shaped function - a duplicate pair with `rust_dup_one_copy_lib_rs`.
rust_dup_other_copy_lib_rs() {
    rust_dup_shaped_fn "compute_two" "left" "right" "7"
}

# A crate whose functions all have distinct bodies (a differing literal
# each time), so the check reports nothing.
rust_dup_clean_lib_rs() {
    cat <<'EOF'
pub fn compute_first(a: i32, b: i32) -> i32 {
    let sum = a + b;
    let scaled = sum * 2;
    let result = scaled + 1;
    result
}

pub fn compute_second(a: i32, b: i32) -> i32 {
    let sum = a + b;
    let scaled = sum * 3;
    let result = scaled + 5;
    result
}
EOF
}
