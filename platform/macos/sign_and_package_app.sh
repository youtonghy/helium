#!/usr/bin/env bash

set -euo pipefail

__helium_realpath() {
    if command -v greadlink >/dev/null 2>&1; then
        greadlink -f "$1"
    else
        python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$1"
    fi
}

_platform_dir="$(dirname "$(__helium_realpath "$0")")"
_main_repo="$(dirname "$(dirname "$_platform_dir")")"

_chromium_version="$(cat "$_main_repo/chromium_version.txt")"
_ungoogled_revision="$(cat "$_main_repo/revision.txt")"
_package_revision="$(cat "$_platform_dir/revision.txt")"

_app_name="${HELIUM_APP_NAME:-}"
if [ -z "$_app_name" ]; then
    for candidate in Nitrous Helium Chromium; do
        if [ -d "out/Default/$candidate.app" ]; then
            _app_name="$candidate"
            break
        fi
    done
fi

if [ -z "$_app_name" ] || [ ! -d "out/Default/$_app_name.app" ]; then
    echo "error: could not find an app bundle in out/Default" >&2
    exit 1
fi

_app_path="out/Default/$_app_name.app"
_framework_path="$_app_path/Contents/Frameworks/$_app_name Framework.framework"

xattr -cs "$_app_path" || true

___helium_codesign_if_exists() {
    local identifier="$1"
    local path="$2"
    shift 2

    if [ ! -e "$path" ]; then
        echo "warn: skipping missing signing target: $path" >&2
        return
    fi

    codesign --sign "$MACOS_CERTIFICATE_NAME" --force --timestamp \
        --identifier "$identifier" "$@" "$path"
}

if [ -n "${MACOS_CERTIFICATE_NAME:-}" ]; then
    APP_ENTITLEMENTS="$_platform_dir/entitlements/app-entitlements.plist"

    if [ -n "${PROD_MACOS_SPECIAL_ENTITLEMENTS_PROFILE_PATH:-}" ]; then
        APP_ENTITLEMENTS="$(mktemp)"
        sed 's/${CHROMIUM_TEAM_ID}/'"${PROD_MACOS_NOTARIZATION_TEAM_ID:-}/" \
            "$_platform_dir/entitlements/app-entitlements-all.plist" > "$APP_ENTITLEMENTS"
        cp "$PROD_MACOS_SPECIAL_ENTITLEMENTS_PROFILE_PATH" \
            "$_app_path/Contents/embedded.provisionprofile"
    fi

    ___helium_codesign_if_exists chrome_crashpad_handler \
        "$_framework_path/Helpers/chrome_crashpad_handler" \
        --options=restrict,library,runtime,kill
    ___helium_codesign_if_exists net.imput.helium.helper \
        "$_framework_path/Helpers/$_app_name Helper.app" \
        --options restrict,library,runtime,kill \
        --entitlements "$_platform_dir/entitlements/helper-entitlements.plist"
    ___helium_codesign_if_exists net.imput.helium.helper.renderer \
        "$_framework_path/Helpers/$_app_name Helper (Renderer).app" \
        --options restrict,kill,runtime \
        --entitlements "$_platform_dir/entitlements/helper-renderer-entitlements.plist"
    ___helium_codesign_if_exists net.imput.helium.helper \
        "$_framework_path/Helpers/$_app_name Helper (GPU).app" \
        --options restrict,kill,runtime \
        --entitlements "$_platform_dir/entitlements/helper-gpu-entitlements.plist"
    ___helium_codesign_if_exists net.imput.helium.framework.AlertNotificationService \
        "$_framework_path/Helpers/$_app_name Helper (Alerts).app" \
        --options restrict,library,runtime,kill
    ___helium_codesign_if_exists app_mode_loader \
        "$_framework_path/Helpers/app_mode_loader" \
        --options restrict,library,runtime,kill
    ___helium_codesign_if_exists web_app_shortcut_copier \
        "$_framework_path/Helpers/web_app_shortcut_copier" \
        --options restrict,library,runtime,kill
    ___helium_codesign_if_exists libEGL \
        "$_framework_path/Libraries/libEGL.dylib"
    ___helium_codesign_if_exists libGLESv2 \
        "$_framework_path/Libraries/libGLESv2.dylib"
    ___helium_codesign_if_exists libvk_swiftshader \
        "$_framework_path/Libraries/libvk_swiftshader.dylib"

    _app_frameworks_dir="$_app_path/Contents/Frameworks"
    if [ -d "$_app_frameworks_dir" ]; then
        shopt -s nullglob
        for dylib_path in "$_app_frameworks_dir"/*.dylib; do
            dylib_name="$(basename "$dylib_path" .dylib)"
            dylib_identifier="$(printf '%s' "$dylib_name" | tr -c '[:alnum:]._-' '_')"
            ___helium_codesign_if_exists "net.imput.helium.$dylib_identifier" \
                "$dylib_path"
        done
        shopt -u nullglob
    fi

    if [ -d "$_framework_path/Frameworks/Sparkle.framework" ]; then
        codesign --sign "$MACOS_CERTIFICATE_NAME" --force --deep --timestamp \
            --options restrict,library,runtime,kill "$_framework_path/Frameworks/Sparkle.framework"
    fi

    ___helium_codesign_if_exists net.imput.helium.framework "$_framework_path" \
        --entitlements "$_platform_dir/entitlements/helper-entitlements.plist"

    app_sign_args=(--options restrict,library,runtime,kill --entitlements "$APP_ENTITLEMENTS")
    if [ -n "${PROD_MACOS_NOTARIZATION_TEAM_ID:-}" ]; then
        app_sign_args+=(
            --requirements
            '=designated => identifier "net.imput.helium" and anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] /* exists */ and certificate leaf[field.1.2.840.113635.100.6.1.13] /* exists */ and certificate leaf[subject.OU] = '"$PROD_MACOS_NOTARIZATION_TEAM_ID"
        )
    fi
    ___helium_codesign_if_exists net.imput.helium "$_app_path" "${app_sign_args[@]}"

    codesign --verify --deep --verbose=4 "$_app_path"

    if [ -n "${PROD_MACOS_NOTARIZATION_APPLE_ID:-}" ] &&
       [ -n "${PROD_MACOS_NOTARIZATION_TEAM_ID:-}" ] &&
       [ -n "${PROD_MACOS_NOTARIZATION_PWD:-}" ]; then
        ditto -c -k --keepParent "$_app_path" "$TMPDIR/notarize.zip"

        CUSTOM_KEYCHAIN_ARG=()
        if [ -n "${CI:-}" ]; then
            CUSTOM_KEYCHAIN_ARG=(--keychain=~/Library/Keychains/build.keychain-db)
        fi

        xcrun notarytool store-credentials "notarytool-profile" \
            --apple-id "$PROD_MACOS_NOTARIZATION_APPLE_ID" \
            --team-id "$PROD_MACOS_NOTARIZATION_TEAM_ID" \
            --password "$PROD_MACOS_NOTARIZATION_PWD" \
            "${CUSTOM_KEYCHAIN_ARG[@]}"

        xcrun notarytool submit "$TMPDIR/notarize.zip" \
            --keychain-profile "notarytool-profile" \
            --wait \
            "${CUSTOM_KEYCHAIN_ARG[@]}"

        xcrun stapler staple "$_app_path"
        rm "$TMPDIR/notarize.zip"
    else
        echo "warn: notarization credentials are incomplete; skipping notarization" >&2
    fi

    if [ -n "${PROD_MACOS_SPECIAL_ENTITLEMENTS_PROFILE_PATH:-}" ]; then
        rm -f "$APP_ENTITLEMENTS"
    fi
else
    echo "warn: MACOS_CERTIFICATE_NAME is missing; using ad-hoc signing" >&2
    codesign --force --deep --sign - "$_app_path"
fi

if [ -z "${OUT_DMG_PATH:-}" ]; then
    OUT_DMG_PATH="$_main_repo/build/nitrous_${_chromium_version}-${_ungoogled_revision}.${_package_revision}_macos.dmg"
fi

if command -v appdmg >/dev/null 2>&1 || [ -n "${NEEDS_APPDMG:-}" ]; then
    dmg_json="$(mktemp)"
    python3 - "$_platform_dir/resources/dmg.json" "$dmg_json" "$_app_name" <<'PY'
import json
import sys

template, output, app_name = sys.argv[1:]
with open(template, encoding="utf-8") as source:
    data = json.load(source)
data["title"] = app_name
data["icon"] = f"{app_name}.app/Contents/Resources/app.icns"
for item in data.get("contents", []):
    if item.get("type") == "file":
        item["path"] = f"{app_name}.app"
with open(output, "w", encoding="utf-8") as target:
    json.dump(data, target, indent=4)
    target.write("\n")
PY
    ln -sf "$dmg_json" "out/Default/dmg.json"
    appdmg "out/Default/dmg.json" "$OUT_DMG_PATH"
    rm -f "$dmg_json"
else
    echo "no appdmg, falling back to stock .dmg" >&2
    chrome/installer/mac/pkg-dmg \
        --sourcefile --source "$_app_path" \
        --target "$OUT_DMG_PATH" \
        --volname "$_app_name" --symlink /Applications:/Applications \
        --format ULMO --verbosity 2
fi

if [ -n "${MACOS_CERTIFICATE_NAME:-}" ]; then
    codesign --sign "$MACOS_CERTIFICATE_NAME" \
        --identifier net.imput.helium --force "$OUT_DMG_PATH"
fi
