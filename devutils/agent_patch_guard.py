#!/usr/bin/env python3
"""Centralized guardrails for agent patch work.

This script keeps the cheap post-edit checks, fresh-source patch checks, and
hotfix write-back flow in one place so agents do not drift between workflows.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATCHES_DIR = ROOT / 'patches'
CODE_DIRS = ('devutils/', 'utils/')
FORBIDDEN_PATCH_TOKENS = (
    'codex_tmp/',
    'patchwork_src',
    '.pc/',
    '.rej',
    'Index:',
)


def quote_command(command):
    """Return a shell-like command string for display."""
    return ' '.join(str(part) for part in command)


def run(command, *, cwd=ROOT, env=None):
    """Run a command and stop the guard on failure."""
    print(f'\n$ {quote_command(command)}', flush=True)
    result = subprocess.run([str(part) for part in command], cwd=cwd, env=env, check=False)
    if result.returncode != 0:
        print(f'\nFAILED: {quote_command(command)}', file=sys.stderr)
        sys.exit(result.returncode)


def git_lines(args):
    """Return stdout lines for a git command, or an empty list if git fails."""
    result = subprocess.run(['git', *args],
                            cwd=ROOT,
                            check=False,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True)
    if result.returncode != 0:
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files(ref):
    """Return changed and untracked files relative to the repo root."""
    files = set(git_lines(['diff', '--name-only', '--diff-filter=ACMR', ref, '--']))
    files.update(git_lines(['ls-files', '--others', '--exclude-standard']))
    return sorted(path for path in files if path)


def print_changed(files):
    """Print the change set used for scoped guard decisions."""
    if not files:
        print('No changed or untracked files detected by git.', flush=True)
        return
    print('Changed/untracked files considered by agent patch guard:', flush=True)
    for path in files:
        print(f'  - {path}')


def parse_series(series_path):
    """Return normalized non-comment entries from patches/series."""
    entries = []
    with series_path.open(encoding='utf-8') as file_obj:
        for line_number, line in enumerate(file_obj, start=1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            entry = line.split('#', 1)[0].strip()
            if entry:
                entries.append((entry, line_number))
    return entries


def check_series(errors):
    """Check patches/series for missing, duplicate, and orphan patch files."""
    series_path = PATCHES_DIR / 'series'
    if not series_path.is_file():
        errors.append('patches/series is missing')
        return

    seen = set()
    duplicate_entries = set()
    entries = parse_series(series_path)
    for entry, line_number in entries:
        if entry in seen:
            duplicate_entries.add(entry)
            errors.append(f'patches/series:{line_number}: duplicate entry: {entry}')
        seen.add(entry)
        if not (PATCHES_DIR / entry).is_file():
            errors.append(f'patches/series:{line_number}: patch not found: {entry}')

    series_entries = {entry for entry, _line_number in entries}
    for patch_path in sorted(PATCHES_DIR.rglob('*.patch')):
        relative_path = str(patch_path.relative_to(PATCHES_DIR))
        if relative_path not in series_entries:
            errors.append(f'orphan patch not listed in patches/series: {relative_path}')

    if duplicate_entries:
        print('Duplicate series entries are not allowed.', file=sys.stderr)


def patch_files_to_scan(files, scan_all=False):
    """Return patch files selected for artifact checks."""
    if scan_all:
        return sorted(path for path in PATCHES_DIR.rglob('*.patch') if path.is_file())

    selected = []
    for path in files:
        if path.startswith('patches/') and path.endswith('.patch'):
            patch_path = ROOT / path
            if patch_path.is_file():
                selected.append(patch_path)
    return sorted(set(selected))


def _valid_diff_path(marker, path):
    """Return whether a patch ---/+++ path uses a stable prefix."""
    if path == '/dev/null':
        return True
    if marker == '---':
        return path.startswith('a/')
    return path.startswith('b/')


def check_patch_artifacts(files, errors, *, scan_all=False):
    """Check patch files for volatile artifacts and unstable diff paths."""
    for patch_path in patch_files_to_scan(files, scan_all=scan_all):
        relative_path = patch_path.relative_to(ROOT)
        try:
            lines = patch_path.read_text(encoding='utf-8', errors='ignore').splitlines()
        except OSError as error:
            errors.append(f'{relative_path}: could not read patch: {error}')
            continue

        for line_number, line in enumerate(lines, start=1):
            for token in FORBIDDEN_PATCH_TOKENS:
                if token in line:
                    errors.append(
                        f'{relative_path}:{line_number}: forbidden patch artifact: {token}')

            if line.startswith(('--- ', '+++ ')):
                marker, path = line.split(maxsplit=1)
                path = path.split('\t', 1)[0]
                if not _valid_diff_path(marker, path):
                    errors.append(
                        f'{relative_path}:{line_number}: unstable diff path for {marker}: {path}')


def preflight(files, *, scan_all_patches=False):
    """Run cheap repository consistency checks before heavier validation."""
    errors = []
    check_series(errors)
    check_patch_artifacts(files, errors, scan_all=scan_all_patches)
    if errors:
        print('Patch guard preflight failed:', file=sys.stderr)
        for error in errors:
            print(f'  - {error}', file=sys.stderr)
        sys.exit(1)
    print('Patch guard preflight passed.', flush=True)


def touches_code_dirs(files):
    """Return whether scoped changes touch devutils/ or utils/."""
    return any(path.startswith(CODE_DIRS) for path in files)


def run_yapf_dry_run(python):
    """Run the AGENTS.md yapf dry-run checks for local Python tooling."""
    for prefix in ('devutils', 'utils'):
        run([
            python, '-m', 'yapf', '--style', '.style.yapf', '-e', '*/third_party/*', '-rpd', prefix
        ])


def run_quick(args, files):
    """Run post-agent quick checks."""
    preflight(files)
    run([
        args.python, '.codex/skills/nitrous-validate/scripts/run_validation.py', '--changed-from',
        args.changed_from
    ])
    if touches_code_dirs(files):
        run_yapf_dry_run(args.python)


def unpack_source_tree(args, source_tree):
    """Delete and unpack a disposable Chromium source tree."""
    shutil.rmtree(source_tree, ignore_errors=True)
    source_tree.parent.mkdir(parents=True, exist_ok=True)
    run([
        args.python,
        './utils/downloads.py',
        'unpack',
        '-i',
        'downloads.ini',
        '-c',
        'chromium_download_cache',
        source_tree,
    ])


def run_patch_source(args, files):
    """Run fresh-source and source-backed patch validation."""
    preflight(files, scan_all_patches=True)
    chromium_src = ROOT / 'chromium_src'
    patchcheck_src = ROOT / 'codex_tmp' / 'patchcheck_src'

    run([args.python, './devutils/check_chromium_src_clean.py', '--source-tree', chromium_src])
    unpack_source_tree(args, patchcheck_src)
    run([args.python, './devutils/check_chromium_src_clean.py', '--source-tree', patchcheck_src])
    run(['./devutils/validate_patches.py', '-l', patchcheck_src, '-v'])
    run([
        args.python,
        '.codex/skills/nitrous-validate/scripts/run_validation.py',
        '--with-source',
        '--source-tree',
        'chromium_src',
        '--changed-from',
        args.changed_from,
    ])


def run_after_hotfix(args, files):
    """Refresh a patch from a disposable hotfix tree, then run both guards."""
    patchwork_src = ROOT / 'codex_tmp' / 'patchwork_src'
    unpack_source_tree(args, patchwork_src)

    env = os.environ.copy()
    env['NITROUS_QUILT_SRC'] = str(patchwork_src)
    env['HELIUM_QUILT_SRC'] = str(patchwork_src) # legacy alias
    run(['./devutils/quilt-fix.sh', args.patch], env=env)

    files = changed_files(args.changed_from)
    print_changed(files)
    run_quick(args, files)
    run_patch_source(args, files)


def main():
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',
                        required=True,
                        choices=('quick', 'patch-source', 'pre-build', 'after-hotfix'),
                        help='Guard mode to run.')
    parser.add_argument('--patch', help='Patch name for --mode after-hotfix.')
    parser.add_argument('--changed-from', default='HEAD', help='Git ref used for scoped changes.')
    parser.add_argument('--python', default=sys.executable, help='Python executable to use.')
    args = parser.parse_args()

    if args.mode == 'after-hotfix' and not args.patch:
        parser.error('--mode after-hotfix requires --patch <patch-name>')
    if args.patch and (Path(args.patch).is_absolute() or '..' in Path(args.patch).parts):
        parser.error('--patch must be a path relative to patches/')

    files = changed_files(args.changed_from)
    print_changed(files)

    if args.mode == 'quick':
        run_quick(args, files)
    elif args.mode == 'patch-source':
        run_patch_source(args, files)
    elif args.mode == 'pre-build':
        run_patch_source(args, files)
    elif args.mode == 'after-hotfix':
        run_after_hotfix(args, files)

    print('\nAgent patch guard completed successfully.')


if __name__ == '__main__':
    main()
