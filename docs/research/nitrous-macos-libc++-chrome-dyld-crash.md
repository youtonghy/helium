# Nitrous macOS libc++_chrome dyld Crash

## Root Cause

Nitrous macOS component builds link the app executable and framework against
component dylibs from the Chromium output directory. The app bundle already
contains `Nitrous Framework.framework` in `Contents/Frameworks`, but
`libc++_chrome.dylib` and a small set of component dylibs required at launch
were left in `out/Default` instead of being copied into the app bundle.

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

The signing script also signs any top-level dylibs copied into
`Contents/Frameworks` before signing the framework and final app bundle, so the
packaged app satisfies macOS code-signing requirements.
