#!/usr/bin/env python3
"""
check_chromium_src_clean.py — Verify chromium_src is a pristine (unpatched) tree.

Detects common contamination markers that indicate patches have been applied
to the tree, which would make validate_patches.py give false results.

Usage:
    python3 devutils/check_chromium_src_clean.py [--source-tree chromium_src]
"""
import argparse
import sys
from pathlib import Path


def _safe_read(path):
    """Read a text file defensively and return an empty string on failure."""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, IOError):
        return ""


def _has_unexpected_orig_files(source_tree):
    """Return the first unexpected .orig file outside known upstream vendor paths."""
    allowed_prefixes = (
        Path("third_party/rust/chromium_crates_io/vendor"),
        Path("third_party/rust-toolchain/lib/rustlib/src/rust/library/vendor"),
    )
    for orig_path in source_tree.rglob("*.orig"):
        relative_path = orig_path.relative_to(source_tree)
        if any(relative_path.is_relative_to(prefix) for prefix in allowed_prefixes):
            continue
        return True, str(relative_path)
    return False, ""


# Markers: files or content that should NOT exist in a clean tree.
# Each marker is (description, check_function).
# check_function receives the source tree Path and returns (bool is_dirty, str detail).

CONTAMINATION_MARKERS = [
    # Files created by helium patches
    ("persona_handler.h (helium/core/persona-settings-ui.patch)", lambda p:
     (p / "chrome/browser/ui/webui/settings/persona_handler.h").exists()),
    ("persona_handler.cc (helium/core/persona-settings-ui.patch)", lambda p:
     (p / "chrome/browser/ui/webui/settings/persona_handler.cc").exists()),
    ("persona_page.ts (helium/core/persona-settings-ui.patch)", lambda p:
     (p / "chrome/browser/resources/settings/privacy_page/persona_page.ts").exists()),
    ("persona_service.h (helium/core/persona-state-management.patch)", lambda p:
     (p / "chrome/browser/helium_persona/persona_service.h").exists()),
    ("trk_protocol_handler.cc (ungoogled-chromium/block-trk-and-subdomains.patch)", lambda p:
     (p / "net/url_request/trk_protocol_handler.cc").exists()),
    ("ungoogled_flag_choices.h (ungoogled-chromium/add-ungoogled-flag-headers.patch)", lambda p:
     (p / "chrome/browser/ungoogled_flag_choices.h").exists()),

    # Content markers: strings that should NOT exist in clean upstream
    ("break_stuff_google in prepopulated_engines.json (restore-google.patch)",
     lambda p: "break_stuff_google" in _safe_read(
         p / "third_party/search_engines_data/resources/definitions/prepopulated_engines.json")),
    ("helium_services in chrome/browser/BUILD.gn (persona patches)",
     lambda p: "helium_services" in _safe_read(p / "chrome/browser/BUILD.gn")),

    # quilt artifacts
    (".pc/ directory (quilt metadata)", lambda p: (p / ".pc").is_dir()),
    ("unexpected *.orig files (quilt pop leftovers)", _has_unexpected_orig_files),
]


def main():
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-tree",
                        default="chromium_src",
                        help="Path to Chromium source tree (default: chromium_src)")
    args = parser.parse_args()

    source_tree = Path(args.source_tree)
    if not source_tree.is_dir():
        print(f"ERROR: Source tree not found: {source_tree}", file=sys.stderr)
        return 2

    dirty_markers = []
    for description, check in CONTAMINATION_MARKERS:
        try:
            result = check(source_tree)
            # Some checks return bool, some return a value
            if isinstance(result, tuple):
                is_dirty, detail = result
            else:
                is_dirty = result
                detail = ""
            if is_dirty:
                dirty_markers.append(f"  ✗ {description}" + (f" — {detail}" if detail else ""))
        except (OSError, RuntimeError, ValueError) as error:
            dirty_markers.append(f"  ⚠ Error checking: {description} — {error}")

    if dirty_markers:
        print("❌ chromium_src is NOT clean — patches appear to have been applied!", file=sys.stderr)
        print(file=sys.stderr)
        print("Contamination markers found:", file=sys.stderr)
        for marker in dirty_markers:
            print(marker, file=sys.stderr)
        print(file=sys.stderr)
        print("To fix: re-unpack from the official tarball:", file=sys.stderr)
        print(f"  rm -rf {args.source_tree}", file=sys.stderr)
        unpack_command = ("  python3 ./utils/downloads.py unpack -i downloads.ini "
                          f"-c chromium_download_cache {args.source_tree}")
        print(unpack_command, file=sys.stderr)
        return 1
    print("✓ chromium_src is clean (no contamination markers detected).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
