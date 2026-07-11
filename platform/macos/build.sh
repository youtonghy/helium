#!/usr/bin/env bash

___helium_sourced() {
    if [ -n "${BASH_VERSION:-}" ]; then
        [ "${BASH_SOURCE[0]}" != "$0" ]
    elif [ -n "${ZSH_VERSION:-}" ]; then
        return 0
    else
        return 1
    fi
}

___helium_enable_strict() {
    set -e
    set -u
    set -o pipefail 2>/dev/null || true
}

___helium_script_path() {
    if [ -n "${BASH_VERSION:-}" ]; then
        printf '%s\n' "${BASH_SOURCE[0]}"
    elif [ -n "${ZSH_VERSION:-}" ]; then
        eval 'printf "%s\n" "${(%):-%x}"'
    else
        printf '%s\n' "$0"
    fi
}

if ! ___helium_sourced; then
    ___helium_enable_strict
fi

_platform_script="$(___helium_script_path)"
_platform_dir="$(cd "$(dirname "$_platform_script")" && pwd)"

source "$_platform_dir/env.sh"
source "$_platform_dir/devutils/set_quilt_vars.sh"
export QUILT_PATCHES="$_merged_patches_dir"
export QUILT_SERIES="series"

___helium_log() {
    printf '[macos] %s\n' "$*" >&2
}

___helium_target_cpu() {
    if [[ "$_arch" == "x86_64" ]]; then
        echo "x64"
    else
        echo "arm64"
    fi
}

___helium_setup_siso() {
    if [ -x "$_siso_path" ]; then
        return
    fi

    local siso_arch="mac-arm64"
    if [[ "$_arch" == "x86_64" ]]; then
        siso_arch="mac-amd64"
    fi

    local siso_package="build/siso/$siso_arch"
    local siso_version
    siso_version=$(sed -n "s/.*'siso_version': '\([^']*\)'.*/\1/p" "$_src_dir/DEPS" | head -1)
    if [ -z "$siso_version" ]; then
        echo "error: couldn't find siso_version in DEPS" >&2
        return 1
    fi

    mkdir -p "$_siso_dir"
    printf '%s\n' "$siso_package $siso_version" |
        "$_depot_tools_dir/cipd" ensure --root "$_siso_dir" --ensure-file -
}

___helium_setup_gn_args() {
    mkdir -p "$_out_dir"
    local args_file="$_out_dir/args.gn"
    cat "$_main_repo/flags.gn" "$_platform_dir/flags.macos.gn" > "$args_file"

    if command -v sccache >/dev/null 2>&1; then
        echo 'cc_wrapper="sccache"' >> "$args_file"
    elif command -v ccache >/dev/null 2>&1; then
        echo 'cc_wrapper="env CCACHE_COMPILERCHECK=content CCACHE_SLOPPINESS=time_macros ccache"' >> "$args_file"
    else
        echo "warn: sccache or ccache is not available" >&2
    fi

    echo "target_cpu = \"$(___helium_target_cpu)\"" >> "$args_file"
    echo 'devtools_skip_typecheck = false' >> "$args_file"
    echo 'use_siso = true' >> "$args_file"
    sed -i.bak 's/is_official_build/is_component_build/' "$args_file"
    rm -f "$args_file.bak"
}

___helium_download_and_unpack() {
    mkdir -p "$_download_cache" "$_src_dir"
    python3 "$_main_repo/utils/downloads.py" retrieve \
        -i "$_main_repo/downloads.ini" "$_main_repo/deps.ini" "$_platform_dir/downloads.ini" \
        -c "$_download_cache"
    python3 "$_main_repo/utils/downloads.py" unpack \
        -i "$_main_repo/downloads.ini" "$_main_repo/deps.ini" "$_platform_dir/downloads.ini" \
        -c "$_download_cache" "$_src_dir"
}

___helium_setup_toolchain() {
    pushd "$_src_dir" >/dev/null
    "$_src_dir/tools/rust/update_rust.py"
    for pkg in clang objdump clang-tidy libclang; do
        "$_src_dir/tools/clang/scripts/update.py" --package "$pkg"
    done
    "$_src_dir/third_party/node/update_node_binaries"

    local node_dir="$_src_dir/third_party/node"
    if [ -d "$node_dir/mac/node-darwin-arm64" ] && [ ! -d "$node_dir/mac_arm64/node-darwin-arm64" ]; then
        mkdir -p "$node_dir/mac_arm64"
        mv "$node_dir/mac/node-darwin-arm64" "$node_dir/mac_arm64/"
    fi
    popd >/dev/null
}

___helium_resources() {
    python3 "$_main_repo/utils/generate_resources.py" \
        "$_main_repo/resources/generate_resources.txt" "$_main_repo/resources"
    python3 "$_main_repo/utils/replace_resources.py" \
        "$_platform_dir/resources/platform_resources.txt" "$_platform_dir/resources" "$_src_dir"
    python3 "$_main_repo/utils/replace_resources.py" \
        "$_main_repo/resources/helium_resources.txt" "$_main_repo/resources" "$_src_dir"
}

___helium_presetup() {
    if [ -d "$_src_dir/out" ]; then
        echo "$_src_dir/out already exists" >&2
        return
    fi

    rm -rf "$_src_dir"
    ___helium_download_and_unpack
    python3 "$_main_repo/utils/prune_binaries.py" "$_src_dir" "$_main_repo/pruning.list"
    ___helium_setup_toolchain
    ___helium_resources
    ___helium_setup_gn_args
    python3 "$_main_repo/utils/helium_version.py" \
        --tree "$_main_repo" \
        --platform-tree "$_platform_dir" \
        --chromium-tree "$_src_dir"
}

___helium_source_ready() {
    [ -f "$_src_dir/DEPS" ] && [ -d "$_src_dir/tools" ]
}

___helium_out_ready() {
    [ -f "$_out_dir/args.gn" ]
}

___helium_config_ready() {
    [ -x "$_out_dir/gn" ] && [ -f "$_out_dir/build.ninja" ]
}

___helium_merged_queue_ready() {
    [ -f "$_merged_patches_dir/series" ]
}

___helium_merged_queue_matches_sources() {
    ___helium_merged_queue_ready || return 1

    local expected_parent
    expected_parent="$(mktemp -d "${TMPDIR:-/tmp}/helium-merged-patches.XXXXXX")"
    local expected_dir="$expected_parent/patches"

    local queue_diff_status=0
    if ! python3 "$_main_repo/utils/patches.py" merge \
        "$expected_dir" \
        "$_main_repo/patches" \
        "$_platform_patches_dir"; then
        rm -rf "$expected_parent"
        return 1
    fi

    if ! diff -qr "$expected_dir" "$_merged_patches_dir" >/dev/null; then
        ___helium_log "merged patch queue differs from source patch queues"
        diff -qr "$expected_dir" "$_merged_patches_dir" >&2 || true
        queue_diff_status=1
    fi

    rm -rf "$expected_parent"
    return "$queue_diff_status"
}

___helium_merged_queue_stale() {
    if ! ___helium_merged_queue_ready; then
        _merged_queue_stale_reason="missing"
        return 0
    fi

    if [ -n "$(find "$_main_repo/patches" "$_platform_patches_dir" -type f \
        -newer "$_merged_patches_dir/series" -print -quit)" ]; then
        _merged_queue_stale_reason="source patch queue is newer"
        return 0
    fi

    if ! ___helium_merged_queue_matches_sources; then
        _merged_queue_stale_reason="content differs from source patch queues"
        return 0
    fi

    _merged_queue_stale_reason=""
    return 1
}

___helium_has_applied_patches() {
    ___helium_source_ready || return 1
    (cd "$_src_dir" && quilt applied >/dev/null 2>&1)
}

___helium_has_unapplied_patches() {
    ___helium_source_ready || return 1
    [ -n "$(cd "$_src_dir" && quilt unapplied 2>/dev/null || true)" ]
}

___helium_app_ready() {
    for app_name in Nitrous Helium Chromium; do
        if [ -x "$_out_dir/$app_name.app/Contents/MacOS/$app_name" ]; then
            return 0
        fi
    done
    return 1
}

___helium_ensure_source() {
    if ___helium_source_ready; then
        ___helium_log "source tree ready: $_src_dir"
        return
    fi

    if [ -e "$_src_dir" ]; then
        ___helium_log "removing incomplete source tree: $_src_dir"
        rm -rf "$_src_dir"
    fi

    ___helium_log "preparing source tree"
    ___helium_presetup
}

___helium_ensure_merged_queue() {
    if ___helium_merged_queue_stale; then
        ___helium_log "merged patch queue stale: $_merged_queue_stale_reason"
        if ___helium_has_applied_patches; then
            ___helium_log "patch queue changed; popping applied patches before re-merge"
            (cd "$_src_dir" && quilt pop -a)
        fi
        ___helium_log "merging root and macOS patch queues"
        ___helium_merge
    else
        ___helium_log "merged patch queue ready: $_merged_patches_dir"
    fi
}

___helium_ensure_patches_applied() {
    ___helium_ensure_source
    ___helium_ensure_merged_queue

    if ___helium_has_unapplied_patches; then
        ___helium_log "applying unapplied patches"
        ___helium_push
    else
        ___helium_log "all merged patches are already applied"
    fi
}

___helium_ensure_configured() {
    ___helium_ensure_patches_applied

    if ! ___helium_out_ready; then
        ___helium_log "writing GN args"
        ___helium_setup_gn_args
    fi

    if ___helium_config_ready; then
        ___helium_log "GN output ready: $_out_dir"
    else
        ___helium_log "configuring GN"
        ___helium_configure
    fi
}

___helium_auto_prepare() {
    ___helium_ensure_source
    ___helium_ensure_merged_queue
    ___helium_check
    ___helium_check_format
    ___helium_ensure_patches_applied
    ___helium_ensure_configured
}

___helium_check_format() {
    ___helium_log "running full format validation"
    (cd "$_main_repo" && python3 "$_main_repo/.codex/skills/nitrous-validate/scripts/run_validation.py" --full)
}

___helium_configure() {
    cd "$_src_dir"
    ___helium_setup_siso
    python3 ./tools/gn/bootstrap/bootstrap.py -o "$_out_dir/gn" --skip-generate-buildfiles
    "$_out_dir/gn" gen "$_out_dir" --fail-on-unused-args --export-compile-commands
}

___helium_merge() {
    rm -rf "$_merged_patches_dir"
    mkdir -p "$(dirname "$_merged_patches_dir")"
    python3 "$_main_repo/utils/patches.py" merge \
        "$_merged_patches_dir" \
        "$_main_repo/patches" \
        "$_platform_patches_dir"
}

___helium_unmerge() {
    rm -rf "$_merged_patches_dir"
}

___helium_push() {
    if [ ! -f "$_merged_patches_dir/series" ]; then
        ___helium_merge
    fi
    cd "$_src_dir"
    # Build flows must not refresh the generated queue; source patches are authoritative.
    quilt push -a
}

___helium_pop() {
    cd "$_src_dir"
    quilt pop -a
}

___helium_substitution() {
    if [ "$1" = "unsub" ]; then
        python3 "$_main_repo/utils/domain_substitution.py" revert \
            -c "$_subs_cache" "$_src_dir"
        python3 "$_main_repo/utils/name_substitution.py" --unsub \
            -t "$_src_dir" --backup-path "$_namesubs_cache"
    elif [ "$1" = "sub" ]; then
        if [ -f "$_subs_cache" ] || [ -f "$_namesubs_cache" ]; then
            echo "substitution cache exists; run he unsub or remove the cache files first" >&2
            return 1
        fi
        python3 "$_main_repo/utils/name_substitution.py" --sub \
            -t "$_src_dir" --backup-path "$_namesubs_cache"
        python3 "$_main_repo/utils/domain_substitution.py" apply \
            -r "$_main_repo/domain_regex.list" \
            -f "$_main_repo/domain_substitution.list" \
            -c "$_subs_cache" \
            "$_src_dir"
    else
        echo "unknown substitution action: $1" >&2
        return 1
    fi
}

___helium_check() {
    if [ ! -f "$_merged_patches_dir/series" ]; then
        ___helium_merge
    fi
    if ! ___helium_merged_queue_matches_sources; then
        echo "error: generated merged patch queue is not identical to source queues" >&2
        echo "run he merge after popping applied patches, then retry" >&2
        return 1
    fi
    python3 "$_main_repo/devutils/validate_config.py"
    "$_platform_dir/devutils/check_patch_files.sh"

    if ___helium_source_ready && ! ___helium_has_applied_patches; then
        python3 "$_main_repo/devutils/validate_patches.py" \
            -l "$_src_dir" \
            -p "$_merged_patches_dir" \
            -s "$_merged_patches_dir/series" \
            -v
    elif ___helium_has_applied_patches; then
        echo "warn: skipped patch apply validation; build/src already has applied patches" >&2
    elif [ -d "$_main_repo/chromium_src" ]; then
        python3 "$_main_repo/devutils/validate_patches.py" \
            -l "$_main_repo/chromium_src" \
            -p "$_main_repo/patches" \
            -s "$_main_repo/patches/series" \
            -v
        echo "warn: skipped macOS platform patch apply validation; build/src is not prepared" >&2
    else
        echo "warn: no Chromium source tree available; skipped patch apply validation" >&2
    fi
}

___helium_syntax_smoke() {
    local smoke_file="third_party/blink/common/navigation/navigation_params.cc"
    if [ ! -f "$_out_dir/compile_commands.json" ]; then
        ___helium_log "skipping syntax smoke; compile_commands.json is not ready"
        return
    fi
    if [ ! -f "$_src_dir/$smoke_file" ]; then
        ___helium_log "skipping syntax smoke; missing $smoke_file"
        return
    fi

    python3 "$_main_repo/devutils/syntax_check.py" -o "$_out_dir" "$smoke_file"
}

___helium_setup() {
    ___helium_ensure_configured
}

___helium_build_products() {
    cd "$_src_dir"
    SISO_PATH="$_siso_path" python3 "$_depot_tools_dir/autoninja.py" \
        -k 0 -C "$_out_dir" chrome chromedriver
    ___helium_sync_ublock_resources
}

___helium_build() {
    ___helium_ensure_configured
    ___helium_check
    ___helium_syntax_smoke
    ___helium_build_products
}

___helium_sync_ublock_resources() {
    local ublock_src="$_src_dir/third_party/ublock"
    local app_resources=""
    for app_name in Nitrous Helium Chromium; do
        local candidate="$_out_dir/$app_name.app/Contents/Frameworks/$app_name Framework.framework/Resources"
        if [ -d "$candidate" ]; then
            app_resources="$candidate"
            break
        fi
    done

    if [ ! -d "$ublock_src" ]; then
        echo "error: missing uBlock resources at $ublock_src" >&2
        return 1
    fi
    if [ -z "$app_resources" ]; then
        echo "error: missing app resources directory in $_out_dir" >&2
        return 1
    fi

    rm -rf "$app_resources/ublock"
    ditto "$ublock_src" "$app_resources/ublock"
}

___helium_package_product() {
    cd "$_src_dir"
    "$_platform_dir/sign_and_package_app.sh"
}

___helium_package() {
    ___helium_ensure_configured
    ___helium_check
    if ! ___helium_app_ready; then
        ___helium_log "app bundle missing; building before packaging"
        ___helium_syntax_smoke
        ___helium_build_products
    fi
    ___helium_package_product
}

___helium_auto_build() {
    ___helium_auto_prepare
    ___helium_syntax_smoke
    ___helium_build_products
}

___helium_auto_package() {
    ___helium_auto_prepare
    ___helium_syntax_smoke
    ___helium_build_products
    ___helium_package_product
}

___helium_run() {
    local app_binary=""
    for app_name in Nitrous Helium Chromium; do
        local candidate="$_out_dir/$app_name.app/Contents/MacOS/$app_name"
        if [ -x "$candidate" ]; then
            app_binary="$candidate"
            break
        fi
    done

    if [ -z "$app_binary" ]; then
        echo "error: couldn't find a runnable app in $_out_dir" >&2
        return 1
    fi

    "$app_binary" \
        --user-data-dir="$HOME/Library/Application Support/net.imput.helium.dev" \
        --enable-ui-devtools \
        --use-mock-keychain \
        --disable-features=DialMediaRouteProvider
}

___helium_reset() {
    ___helium_unmerge || true
    rm -f "$_subs_cache" "$_namesubs_cache"
    if [ -d "$_src_dir" ]; then
        mv "$_src_dir" "${_src_dir}.old"
        rm -rf "${_src_dir}.old" &
    fi
}

__helium_usage() {
    cat >&2 <<'EOF'
usage:
  source platform/macos/build.sh
  he <command>

commands:
  setup       presetup, merge, push, configure
  presetup    download/unpack sources, dependencies, resources, and GN args
  check       validate config, patch series, and patch application when a source tree exists
  merge       merge root and platform patches into build/platform_macos_patches
  unmerge     remove the generated merged patch queue
  push        apply merged patches to build/src with quilt
  pop         pop all quilt patches from build/src
  configure   bootstrap GN and generate out/Default
  build       run check, then build chrome and chromedriver
  package     run check, then sign/notarize/package the app DMG
  auto-build  automatically prepare, merge, patch, configure, and build
  auto-package automatically prepare, merge, patch, configure, build, and package
  run         run the local development app
  sub|unsub   apply or revert domain/name substitutions in build/src
  reset       remove build/src and merge/substitution caches
EOF
}

__helium_menu() {
    case "${1:-}" in
        setup) ___helium_setup ;;
        presetup) ___helium_presetup ;;
        check) ___helium_check ;;
        merge) ___helium_merge ;;
        unmerge) ___helium_unmerge ;;
        push) ___helium_push ;;
        pop) ___helium_pop ;;
        configure) ___helium_configure ;;
        resources) ___helium_resources ;;
        build) ___helium_build ;;
        package) ___helium_package ;;
        auto-build|autobuild) ___helium_auto_build ;;
        auto-package|autopackage|dist) ___helium_auto_package ;;
        run) ___helium_run ;;
        sub|unsub) ___helium_substitution "$1" ;;
        reset) ___helium_reset ;;
        ""|-h|--help|help) __helium_usage ;;
        *)
            echo "unknown command: $1" >&2
            __helium_usage
            return 1
            ;;
    esac
}

he() {
    (___helium_enable_strict; __helium_menu "$@")
}

if ! ___helium_sourced; then
    __helium_menu "$@"
else
    if [ "${__helium_loaded:-}" = "" ]; then
        __helium_loaded=1
    fi
fi
