#!/usr/bin/env bash

__helium_realpath() {
    if command -v greadlink >/dev/null 2>&1; then
        greadlink -f "$1"
    else
        python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$1"
    fi
}

__helium_source_path() {
    if [ -n "${BASH_VERSION:-}" ]; then
        printf '%s\n' "${BASH_SOURCE[0]}"
    elif [ -n "${ZSH_VERSION:-}" ]; then
        eval 'printf "%s\n" "${(%):-%x}"'
    else
        printf '%s\n' "$0"
    fi
}

# The architecture of the running shell; also used as the default target arch.
# Prefer NITROUS_*; fall back to HELIUM_* for compatibility.
_arch="${NITROUS_TARGET_ARCH:-${HELIUM_TARGET_ARCH:-$(/usr/bin/uname -m)}}"

_platform_dir="$(dirname "$(__helium_realpath "$(__helium_source_path)")")"
_main_repo="$(dirname "$(dirname "$_platform_dir")")"
_build_dir="${NITROUS_BUILD_DIR:-${HELIUM_BUILD_DIR:-$_main_repo/build}}"
_download_cache="${NITROUS_DOWNLOAD_CACHE:-${HELIUM_DOWNLOAD_CACHE:-$_build_dir/download_cache}}"
_src_dir="${NITROUS_SRC_DIR:-${HELIUM_SRC_DIR:-$_build_dir/src}}"
_out_dir="${NITROUS_OUT_DIR:-${HELIUM_OUT_DIR:-$_src_dir/out/Default}}"
_platform_patches_dir="$_platform_dir/patches"
_merged_patches_dir="${NITROUS_MERGED_PATCHES_DIR:-${HELIUM_MERGED_PATCHES_DIR:-$_build_dir/platform_macos_patches}}"
_subs_cache="$_build_dir/subs.tar.gz"
_namesubs_cache="$_build_dir/namesubs.tar"

_depot_tools_dir="$_src_dir/third_party/depot_tools"
_siso_dir="$_src_dir/third_party/siso/cipd"
_siso_path="$_siso_dir/siso"
