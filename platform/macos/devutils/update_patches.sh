#!/usr/bin/env bash

set -euo pipefail

__helium_realpath() {
    if command -v greadlink >/dev/null 2>&1; then
        greadlink -f "$1"
    else
        python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$1"
    fi
}

PLATFORM_ROOT="$(dirname "$(dirname "$(__helium_realpath "${BASH_SOURCE[0]}")")")"
MAIN_REPO="$(dirname "$(dirname "$PLATFORM_ROOT")")"

python3 "$MAIN_REPO/devutils/update_platform_patches.py" "$1" "$PLATFORM_ROOT/patches"
