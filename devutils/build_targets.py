#!/usr/bin/env python3
"""Incremental single-target build against the warm helium-macos build tree.

`he build` runs `autoninja -k 0 chrome chromedriver` -- the full product. When
you are iterating on a compile/link/TS failure, you rarely need the whole
product; you need the one library or action that failed to rebuild. This
wrapper invokes autoninja on just the targets you name, reusing the warm siso
state, so a rebuild is minutes instead of ~2 hours.

Use this for failures that -fsyntax-only (see syntax_check.py) can NOT catch:
    - SOLINK / LINK failures (need real object files linked)
    - ts_library.py / TypeScript build actions
    - any generated/action step

Usage:
    python3 devutils/build_targets.py TARGET [TARGET ...]
    python3 devutils/build_targets.py --from-failed   # parse failed cmds
    python3 devutils/build_targets.py content chrome/browser

Targets are ninja target names or output paths, e.g.:
    content                         (a component dylib)
    obj/content/browser/browser/critical_client_hints_throttle.o
    gen/chrome/browser/resources/persona_picker/tsc/...

Environment (autodetected, override with flags/env):
    HELIUM_MACOS_ROOT  default: /Users/youtonghy/github/Project/Nitrous/helium-macos
"""

import argparse
import glob
import os
import re
import subprocess
import sys

_DEFAULT_MACOS_ROOT = os.environ.get("HELIUM_MACOS_ROOT",
                                     "/Users/youtonghy/github/Project/Nitrous/helium-macos")


def resolve_paths(macos_root):
    """Return key paths inside a helium-macos warm build tree."""
    src_dir = os.path.join(macos_root, "build", "src")
    out_dir = os.path.join(src_dir, "out", "Default")
    depot = os.path.join(src_dir, "third_party", "depot_tools")
    siso = os.path.join(src_dir, "third_party", "siso", "cipd", "siso")
    autoninja = os.path.join(depot, "autoninja.py")
    for path, what in ((src_dir, "build/src"), (out_dir, "out/Default"), (autoninja,
                                                                          "autoninja.py")):
        if not os.path.exists(path):
            sys.exit(f"error: {what} not found at {path}\n"
                     "Is the helium-macos build tree present? "
                     "Set HELIUM_MACOS_ROOT.")
    return src_dir, out_dir, siso, autoninja


def targets_from_failed(out_dir):
    """Extract target output paths from siso_failed_commands*.sh annotations."""
    targets = []
    pattern = re.compile(r"^#\s+(?:CXX|CC|OBJCXX|SOLINK|SOLINK_MODULE|LINK|ACTION)\s+(\S+)")
    for script_path in sorted(glob.glob(os.path.join(out_dir, "siso_failed_commands*.sh"))):
        with open(script_path, encoding="utf-8") as failed_commands:
            for line in failed_commands:
                match = pattern.match(line)
                if match:
                    tok = match.group(1)
                    # ACTION lines look like //path:target(toolchain); take label.
                    if tok.startswith("//"):
                        tok = tok.split("(")[0]
                    targets.append(tok)
    # De-dup, preserve order.
    seen = set()
    uniq = []
    for target in targets:
        if target not in seen:
            seen.add(target)
            uniq.append(target)
    return uniq


def main():
    """Parse args, resolve targets, and invoke autoninja incrementally."""
    parser = argparse.ArgumentParser(description="Incremental single-target build via autoninja")
    parser.add_argument("targets", nargs="*", help="ninja targets / output paths")
    parser.add_argument("--macos-root", default=_DEFAULT_MACOS_ROOT)
    parser.add_argument("--from-failed",
                        action="store_true",
                        help="Derive targets from siso_failed_commands*.sh")
    parser.add_argument("-k",
                        "--keep-going",
                        type=int,
                        default=0,
                        help="autoninja -k value (0 = keep going forever)")
    parser.add_argument("-n",
                        "--dry-run",
                        action="store_true",
                        help="Print the autoninja command without running it")
    args = parser.parse_args()

    src_dir, out_dir, siso, autoninja = resolve_paths(args.macos_root)

    targets = list(args.targets)
    if args.from_failed:
        found = targets_from_failed(out_dir)
        if not found:
            print("[build_targets] no targets found in failed command files", file=sys.stderr)
        targets.extend(found)

    if not targets:
        sys.exit("[build_targets] no targets given. Pass names or --from-failed.")

    argv = ["python3", autoninja, "-k", str(args.keep_going), "-C", out_dir]
    argv.extend(targets)

    print(f"[build_targets] {' '.join(targets)}", file=sys.stderr)
    if args.dry_run:
        print(" ".join(argv))
        return

    env = dict(os.environ)
    if os.path.exists(siso):
        env["SISO_PATH"] = siso
    proc = subprocess.run(argv, cwd=src_dir, env=env, check=False)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
