#!/usr/bin/env python3
"""Fast C++ syntax/type precheck using the build's compile_commands.json.

Runs clang with -fsyntax-only on one or more changed source files, using the
exact compile command recorded for each translation unit. This surfaces
compile-time errors (syntax, types, headers, template instantiation) in
seconds, without launching siso/ninja or linking.

Scope: compile-time errors only. Link errors (SOLINK/LINK) and TypeScript
build failures are NOT covered here -- use an incremental single-target build
for those (see build_targets.py).

Usage:
    python3 devutils/syntax_check.py [options] FILE [FILE ...]

    FILE may be absolute or relative to the build source tree. Paths are
    matched against the "file" field in compile_commands.json.

Options:
    -o, --out-dir DIR   Build output dir holding compile_commands.json
                        (default: autodetect a warm tree, see below).
    -j, --jobs N        Parallel jobs (default: CPU count).
    -q, --quiet         Only print failures.
    --list-unmatched    List files with no compile entry and exit non-zero.

Autodetected out dirs (first existing wins):
    $HELIUM_OUT_DIR
    ../helium-macos/build/src/out/Default   (relative to repo root)
    /Users/youtonghy/github/Project/Nitrous/helium-macos/build/src/out/Default
"""

import argparse
import concurrent.futures
import json
import os
import shlex
import subprocess
import sys

_DEFAULT_OUT_DIRS = [
    os.environ.get("HELIUM_OUT_DIR", ""),
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                 "helium-macos", "build", "src", "out", "Default"),
    "/Users/youtonghy/github/Project/Nitrous/helium-macos/build/src/out/Default",
]


def find_out_dir(explicit):
    """Find a build output directory that has compile_commands.json."""
    candidates = [explicit] if explicit else _DEFAULT_OUT_DIRS
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(candidate, "compile_commands.json")):
            return os.path.abspath(candidate)
    tried = [candidate for candidate in candidates if candidate]
    sys.exit("error: no compile_commands.json found. Tried:\n  " + "\n  ".join(tried) +
             "\nPass --out-dir or set HELIUM_OUT_DIR.")


def iter_entries(cc_path):
    """Stream compile_commands.json one object at a time (file can be >400MB)."""
    decoder = json.JSONDecoder()
    with open(cc_path, encoding="utf-8") as compile_commands:
        buf = compile_commands.read()
    idx = buf.find("[")
    if idx < 0:
        return
    idx += 1
    buffer_len = len(buf)
    while idx < buffer_len:
        while idx < buffer_len and buf[idx] in " \t\r\n,":
            idx += 1
        if idx >= buffer_len or buf[idx] == "]":
            break
        obj, end = decoder.raw_decode(buf, idx)
        yield obj
        idx = end


def norm(path, base):
    """Normalize a path relative to base into a real absolute path."""
    if not os.path.isabs(path):
        path = os.path.join(base, path)
    return os.path.normpath(os.path.realpath(path))


def build_index(cc_path, wanted_basenames=None):
    """Map normalized absolute source path -> entry.

    If wanted_basenames is given, only entries whose file basename is in that
    set are decoded/kept. The 425MB DB is still streamed, but we skip building
    the full index, which keeps memory and time down for small change sets.
    """
    index = {}
    for entry in iter_entries(cc_path):
        file_path = entry.get("file", "")
        if not file_path:
            continue
        if wanted_basenames is not None and os.path.basename(file_path) not in wanted_basenames:
            continue
        directory = entry.get("directory", "")
        key = norm(file_path, directory)
        index[key] = entry
    return index


def to_syntax_only(command):
    """Rewrite a compile command into an -fsyntax-only invocation."""
    tokens = shlex.split(command)
    out = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("-c", ):
            i += 1
            continue
        if tok in ("-o", "-MF", "-MT", "-MQ"):
            i += 2
            continue
        if tok in ("-MD", "-MMD", "-MP"):
            i += 1
            continue
        if tok.startswith("-o") and len(tok) > 2:
            i += 1
            continue
        out.append(tok)
        i += 1
    out.append("-fsyntax-only")
    return out


def check_one(entry, out_dir):
    """Run one compile command in -fsyntax-only mode."""
    directory = entry.get("directory", out_dir)
    argv = to_syntax_only(entry["command"])
    proc = subprocess.run(argv, cwd=directory, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def source_root_for_out_dir(out_dir):
    """Return the Chromium source root for an out/<config> directory."""
    return os.path.abspath(os.path.join(out_dir, os.pardir, os.pardir))


def find_entry(index, requested_file, source_root):
    """Find a compile_commands entry for a user-provided path."""
    bases = [os.getcwd(), source_root]
    for base in bases:
        entry = index.get(norm(requested_file, base))
        if entry is not None:
            return entry

    base_name = os.path.basename(requested_file)
    hits = [entry for key, entry in index.items() if os.path.basename(key) == base_name]
    if len(hits) == 1:
        return hits[0]
    return None


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Fast -fsyntax-only precheck via compile_commands.json")
    parser.add_argument("files", nargs="+", help="Source files to check")
    parser.add_argument("-o", "--out-dir", default="")
    parser.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 4)
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("--list-unmatched", action="store_true")
    return parser.parse_args()


def match_entries(index, files, source_root):
    """Split requested files into matched compile entries and unmatched paths."""
    matched = []
    unmatched = []
    for file_path in files:
        entry = find_entry(index, file_path, source_root)
        if entry is None:
            unmatched.append(file_path)
        else:
            matched.append((file_path, entry))
    return matched, unmatched


def print_unmatched(unmatched):
    """Print unmatched source file diagnostics."""
    print("[syntax_check] no compile entry for:", file=sys.stderr)
    for file_path in unmatched:
        print(f"  - {file_path}", file=sys.stderr)
    print(
        "  (header-only, generated, TypeScript, or not a compiled TU; "
        "use an incremental single-target build instead)",
        file=sys.stderr)


def run_checks(matched, out_dir, jobs, quiet):
    """Run syntax-only checks and return the number of failed files."""
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {
            executor.submit(check_one, entry, out_dir): file_path
            for file_path, entry in matched
        }
        for future in concurrent.futures.as_completed(futures):
            file_path = futures[future]
            returncode, stdout, stderr = future.result()
            if returncode == 0:
                if not quiet:
                    print(f"[ok]   {file_path}")
            else:
                failures += 1
                print(f"[FAIL] {file_path}")
                sys.stdout.write(stdout)
                sys.stderr.write(stderr)
    return failures


def main():
    """CLI entrypoint."""
    args = parse_args()

    out_dir = find_out_dir(args.out_dir)
    source_root = source_root_for_out_dir(out_dir)
    cc_path = os.path.join(out_dir, "compile_commands.json")
    if not args.quiet:
        print(f"[syntax_check] using {cc_path}", file=sys.stderr)

    index = build_index(cc_path, {os.path.basename(file_path) for file_path in args.files})
    matched, unmatched = match_entries(index, args.files, source_root)

    if unmatched:
        print_unmatched(unmatched)

    if args.list_unmatched:
        sys.exit(1 if unmatched else 0)

    if not matched:
        sys.exit("[syntax_check] nothing to check" if not unmatched else 2)

    failures = run_checks(matched, out_dir, args.jobs, args.quiet)

    if failures:
        print(f"\n[syntax_check] {failures} file(s) failed, "
              f"{len(matched) - failures} ok",
              file=sys.stderr)
        sys.exit(1)
    if not args.quiet:
        print(f"\n[syntax_check] all {len(matched)} file(s) passed")


if __name__ == "__main__":
    main()
