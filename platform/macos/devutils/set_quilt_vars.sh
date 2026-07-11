# Sets quilt variables for updating the merged macOS patch queue.
# Source this file so the variables and shell function are available to quilt.

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

quilt() {
    command quilt --quiltrc - "$@"
}

PLATFORM_ROOT="$(dirname "$(dirname "$(__helium_realpath "$(__helium_source_path)")")")"

export QUILT_PATCHES="$PLATFORM_ROOT/patches"
export QUILT_SERIES="series"

export QUILT_PUSH_ARGS="--color=auto"
export QUILT_DIFF_OPTS="--show-c-function"
export QUILT_PATCH_OPTS="--unified --reject-format=unified"
export QUILT_DIFF_ARGS="-p ab --no-timestamps --no-index --color=auto"
export QUILT_REFRESH_ARGS="-p ab --no-timestamps --no-index --strip-trailing-whitespace"
export QUILT_COLORS="diff_hdr=1;32:diff_add=1;34:diff_rem=1;31:diff_hunk=1;33:diff_ctx=35:diff_cctx=33"
export QUILT_SERIES_ARGS="--color=auto"
export QUILT_PATCHES_ARGS="--color=auto"
export LC_ALL=C

if [ -n "${LESS-}" ] && [ -z "${QUILT_PAGER+x}" ]; then
    export QUILT_PAGER="less -FRX"
fi
