#!/usr/bin/env bash
# Shared setup for the Rust duplicate-type check's acceptance oracles:
# locates the repo, builds the check binary once, and prepares the
# committed real-lobaria fixture or a throwaway synthetic workspace. Each
# oracle entrypoint sources this file; it judges nothing itself, it only
# sets up the real crate and the real fixtures the oracle then observes.
set -uo pipefail

# The cargo/rustc toolchain installs under the user's home, not a system
# bin dir. Aspergillus's own acceptance gate runs each oracle in a hermetic
# child env whose HOME is exposed read-through to the real toolchain dirs
# but whose PATH carries only uv/git/bash + system dirs, so make cargo
# reachable by name here. In a real consumer's shell this dir is already
# on PATH, so prepending it is a harmless no-op there.
export PATH="${HOME}/.cargo/bin:${PATH}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DUP_TYPE_MANIFEST="${REPO_ROOT}/rust/Cargo.toml"

# The commit the request names as the reference corpus: lobaria's Nanos
# and Receipt duplication, and its non-duplicate Refused/Carried/Hit/
# Finding names. A grading sandbox cannot be relied on to reach the real
# lobaria repository over the network or the filesystem, so
# rust/fixtures/lobaria-a027fb9/ holds a verbatim, committed copy of the
# exact real files this reference needs (see its PROVENANCE.md).
LOBARIA_REFERENCE_SHA="a027fb9"

# Builds the duplicate-type check binary (debug profile) and prints its
# path on stdout.
rust_dup_type_build() {
    cargo build --manifest-path "${DUP_TYPE_MANIFEST}" --offline -q --bin aspergillus-rust-dup-type-check 1>&2 || return 1
    echo "${REPO_ROOT}/rust/target/debug/aspergillus-rust-dup-type-check"
}

# The committed real-lobaria fixture workspace for the reference commit
# named by $1 (default: the pebble's reference commit).
rust_dup_type_lobaria_fixture() {
    local sha="${1:-${LOBARIA_REFERENCE_SHA}}"
    echo "${REPO_ROOT}/rust/fixtures/lobaria-${sha}"
}

# Copies the committed real-lobaria fixture for $1 into a fresh throwaway
# directory and prints the copy's path — for an oracle that must prove the
# check never edits what it scans.
rust_dup_type_lobaria_copy() {
    local sha="${1:-${LOBARIA_REFERENCE_SHA}}"
    local src
    src="$(rust_dup_type_lobaria_fixture "${sha}")"
    local dest
    dest="$(mktemp -d)/lobaria"
    cp -R "${src}" "${dest}"
    echo "${dest}"
}

# Writes a minimal Cargo package at $1 with src/lib.rs contents $2.
rust_dup_type_write_crate() {
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

# Prints a PATH string with every directory holding one of $2.. rebuilt as
# a proxy directory that symlinks every OTHER entry — so coreutils, bash,
# git and cargo stay reachable by name while the named binaries (e.g.
# python3, node) resolve nowhere on the printed PATH. $1 is a scratch
# directory this function may write proxy directories under.
rust_dup_type_path_without() {
    local work="$1"
    shift
    local names=("$@")
    local proxy_root="${work}/path_without_proxy"
    mkdir -p "${proxy_root}"
    local new_path=""
    local old_ifs="${IFS}"
    IFS=':'
    read -r -a dirs <<<"${PATH}"
    IFS="${old_ifs}"
    local index=0
    for dir in "${dirs[@]}"; do
        [ -d "${dir}" ] || continue
        local excluded=0
        local name
        for name in "${names[@]}"; do
            if [ -e "${dir}/${name}" ]; then
                excluded=1
                break
            fi
        done
        if [ "${excluded}" -eq 0 ]; then
            new_path="${new_path:+${new_path}:}${dir}"
            continue
        fi
        index=$((index + 1))
        local proxy="${proxy_root}/${index}"
        mkdir -p "${proxy}"
        local entry base skip
        for entry in "${dir}"/*; do
            [ -e "${entry}" ] || continue
            base="$(basename "${entry}")"
            skip=0
            for name in "${names[@]}"; do
                if [ "${base}" = "${name}" ]; then
                    skip=1
                    break
                fi
            done
            [ "${skip}" -eq 1 ] && continue
            ln -s "${entry}" "${proxy}/${base}" 2>/dev/null || true
        done
        new_path="${new_path:+${new_path}:}${proxy}"
    done
    echo "${new_path}"
}
