# Nitrous macOS libc++_chrome dyld Crash

## Root Cause

Nitrous macOS component builds link the app executable and framework against
component dylibs from the Chromium output directory. The app bundle already
contains `Nitrous Framework.framework` in `Contents/Frameworks`, but
the component dylib dependency closure was left in `out/Default` instead of
being copied into the app bundle. Copying only the first missing library moves
the failure to the next transitive dependency, such as `libbase.dylib`.

At runtime dyld resolves the component build rpath from the executable toward
`Contents/Frameworks`. When `libc++_chrome.dylib` is absent there, launch fails
before Chromium can initialize.

## Fix

Add a macOS component-build-only `bundle_data` target in `chrome/BUILD.gn` that
copies these launch-critical dylibs into `{{bundle_contents_dir}}/Frameworks`:

- `libc++_chrome.dylib` from `//buildtools/third_party/libc++`
- `libchrome_dll.dylib` from `:chrome_dll`
- `libsandbox_mac_seatbelt.dylib` from `//sandbox/mac:seatbelt`

The target is added as a dependency of `mac_app_bundle("chrome_app")` only when
`is_component_build` is true, immediately after the existing component-build
`data_deps = [ ":chrome_framework" ]` line.

Before signing, `devutils/sync_component_dylibs.py` scans the app's Mach-O files
with `dyld_info`, follows every top-level `@rpath/*.dylib` dependency, and
recursively copies missing libraries from `out/Default` into
`Contents/Frameworks`. Packaging fails if any required library is unavailable,
so it cannot silently emit an incomplete app. The signing script then signs all
top-level dylibs before signing the framework and final app bundle.
