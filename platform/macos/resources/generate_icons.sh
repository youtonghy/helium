#!/usr/bin/env bash

__helium_realpath() {
    if command -v greadlink >/dev/null 2>&1; then
        greadlink -f "$1"
    else
        python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$1"
    fi
}

_platform_dir="$(dirname "$(dirname "$(__helium_realpath "$0")")")"
_main_repo="$(dirname "$(dirname "$_platform_dir")")"
_platform_resources="$_platform_dir/resources"

# if we already have pre-compiled files, then we shouldn't generate them.
# Assets.car requires a very specific environment, so we use a
# pre-compiled version for convenience
if [ -e "${_platform_resources}/assets/Assets.car" ] && \
    [ -e "${_platform_resources}/assets/app.icns" ]; then
    # we exit here because we expect the resource
    # script to copy these files for us
    echo "Assets.car and app.icns already exist, skipping"
    exit 0
fi

icon_sizes=(16 32 64 128 256 512)

generate_iconset() {
    # $1 - in; $2 - output path; $3 - cropped icon

    # output directory
    out="${2}"

    if [ ! -d "$out" ]; then
        mkdir "$out"
    fi

    # if the secondary icon format isn't defined, then we're generating
    # Icon.iconset which only has 256x256 sizes
    if [ -z "$3" ]; then
        sips -z 256 256 "$input_file" --out "$out/icon_256x256.png"
        sips -z 512 512 "$input_file" --out "$out/icon_256x256@2x.png"
    else
        # s - size
        for s in ${icon_sizes[@]}; do
            input_file="$1"

            # 16x16 and 32x32 icons use a cropped version
            if [ "$s" = 16 ] || [ "$s" = 32 ] || [ "$d" = 16 ] || [ "$d" = 32 ]; then
                if [ -n "$3" ] && [ -f "$3" ]; then
                    input_file="$3"
                fi
            fi

            sips -z $s $s "$input_file" --out "$out/appicon_${s}.png"
        done
    fi
}

if [ ! -d "${_platform_resources}/generated" ]; then
    mkdir "${_platform_resources}/generated/Assets.xcassets/AppIcon.appiconset"
    mkdir "${_platform_resources}/generated/Assets.xcassets/Icon.iconset"
    cp -R "${_platform_resources}/assets" "${_platform_resources}/generated"
fi

generate_iconset "${_platform_resources}/assets/legacy.png" \
    "${_platform_resources}/generated/Assets.xcassets/AppIcon.appiconset" \
    "${_platform_resources}/assets/legacy_crop.png"

generate_iconset "${_platform_resources}/assets/legacy_crop.png" \
    "${_platform_resources}/generated/Assets.xcassets/Icon.iconset"

rm -rf "${_main_repo}/build/src/chrome/app/theme/chromium/mac"

cp -R "${_platform_resources}/generated" "${_main_repo}/build/src/chrome/app/theme/chromium/mac"

python3 "${_main_repo}/build/src/tools/mac/icons/compile_car.py" --verbose \
    "${_main_repo}/build/src/chrome/app/theme/chromium/mac/Assets.xcassets"
