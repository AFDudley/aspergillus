#!/usr/bin/env bash
# Shared setup for the Rust `--exclude` acceptance oracles (pebble asp-f4c):
# locates the repo, builds all three check binaries, and writes the
# throwaway multi-crate fixture the c1/c2/c3/c6/c8 oracles share. Each
# oracle entrypoint sources this file; it judges nothing itself, it only
# sets up the real binaries and the real fixture the oracle then observes.
set -uo pipefail

# The cargo/rustc toolchain installs under the user's home, not a system
# bin dir. Aspergillus's own acceptance gate runs each oracle in a hermetic
# child env whose HOME is exposed read-through to the real toolchain dirs
# but whose PATH carries only uv/git/bash + system dirs, so make cargo
# reachable by name here. In a real consumer's shell this dir is already
# on PATH, so prepending it is a harmless no-op there.
export PATH="${HOME}/.cargo/bin:${PATH}"

rust_exclude_repo_root() {
    cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

REPO_ROOT="$(rust_exclude_repo_root)"
EXCLUDE_MANIFEST="${REPO_ROOT}/rust/Cargo.toml"

# Builds all three check binaries (debug profile) and prints their paths,
# one per line, in the order gate, dup-check, dup-type-check.
rust_exclude_build_all() {
    cargo build --manifest-path "${EXCLUDE_MANIFEST}" --offline -q \
        --bin aspergillus-rust-gate \
        --bin aspergillus-rust-dup-check \
        --bin aspergillus-rust-dup-type-check 1>&2 || return 1
    local bin_dir="${REPO_ROOT}/rust/target/debug"
    echo "${bin_dir}/aspergillus-rust-gate"
    echo "${bin_dir}/aspergillus-rust-dup-check"
    echo "${bin_dir}/aspergillus-rust-dup-type-check"
}

# Writes one crate at `$1/Cargo.toml` + `$1/src/lib.rs`, with `$2` naming
# the package (must be unique within a workspace) and `$3` the lib body.
rust_exclude_write_crate() {
    local dir="$1" name="$2" lib_rs="$3"
    mkdir -p "${dir}/src"
    cat >"${dir}/Cargo.toml" <<EOF
[package]
name = "${name}"
version = "0.1.0"
edition = "2021"
EOF
    printf '%s' "${lib_rs}" >"${dir}/src/lib.rs"
}

# One crate's body: a duplicated `Marker` tuple struct, a duplicated
# `AllowMe` enum (present only in kept-a/kept-b, for the allowlist-coexist
# oracle), a blocking ASP203 `static mut`, and a type-2-duplicate function
# body. `$1` a per-crate suffix (for distinct static/fn names), `$2`/`$3`
# the function's two parameter names, `$4` whether to also declare
# `AllowMe` (`true`/`false`).
rust_exclude_marker_lib_rs() {
    local suffix="$1" a="$2" b="$3" with_allow_me="$4"
    local allow_me=""
    if [ "${with_allow_me}" = "true" ]; then
        allow_me='
pub enum AllowMe {
    A,
    B,
}
'
    fi
    cat <<EOF
pub struct Marker(pub i64);
${allow_me}
static mut COUNTER_${suffix}: u32 = 0;

pub fn shaped_${suffix}(${a}: i32, ${b}: i32) -> i32 {
    let sum = ${a} + ${b};
    let scaled = sum * 9;
    let result = scaled + 1;
    result
}
EOF
}

# Writes the shared four-crate fixture at `$1`:
# - kept-a/, kept-b/: declare `Marker` and `AllowMe`, never excluded by
#   any oracle here.
# - alpha/dup/, beta/dup/: declare `Marker` only, each under its own
#   glob-excludable subtree (`alpha/**`, `beta/**`).
# `Marker` is a cross-crate duplicate across all four crates; `AllowMe` is
# a cross-crate duplicate confined to kept-a/kept-b. Every crate's
# `shaped_*` function is a type-2 duplicate of every other, and every
# crate's `static mut` trips the blocking ASP203 ast-grep rule — so all
# three check binaries have a genuine finding to report per crate.
rust_exclude_write_layered_fixture() {
    local root="$1"
    rust_exclude_write_crate "${root}/kept-a" "kept-a" \
        "$(rust_exclude_marker_lib_rs A first second true)"
    rust_exclude_write_crate "${root}/kept-b" "kept-b" \
        "$(rust_exclude_marker_lib_rs B left right true)"
    rust_exclude_write_crate "${root}/alpha/dup" "alpha-dup" \
        "$(rust_exclude_marker_lib_rs ALPHA m n false)"
    rust_exclude_write_crate "${root}/beta/dup" "beta-dup" \
        "$(rust_exclude_marker_lib_rs BETA p q false)"
    cat >"${root}/Cargo.toml" <<EOF
[workspace]
members = ["kept-a", "kept-b", "alpha/dup", "beta/dup"]
resolver = "2"
EOF
}
