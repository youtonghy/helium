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

SERIES_FILE="$PLATFORM_ROOT/patches/series"
if [ -f "$PLATFORM_ROOT/patches/series.merged" ]; then
    SERIES_FILE="$PLATFORM_ROOT/patches/series.merged"
fi

while IFS= read -r patch_path; do
    patch_path="${patch_path%% #*}"
    if [ -z "$patch_path" ] || [[ "$patch_path" == \#* ]]; then
        continue
    fi
    if [ ! -f "$PLATFORM_ROOT/patches/$patch_path" ]; then
        echo "missing platform patch: $patch_path" >&2
        exit 1
    fi
done < "$SERIES_FILE"
