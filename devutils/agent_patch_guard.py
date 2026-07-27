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

import hot_patch_export

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


def normalize_patch_artifacts(content):
    """Remove quilt Index metadata without modifying diff hunks."""
    lines = content.splitlines(keepends=True)
    normalized = []
    skip_separator = False
    for line in lines:
        if line.startswith('Index:'):
            skip_separator = True
            continue
        if skip_separator and line.startswith('==='):
            skip_separator = False
            continue
        skip_separator = False
        normalized.append(line)
    return ''.join(normalized)


def normalize_all_patch_artifacts():
    """Normalize patch metadata through the guard's explicit write mode."""
    changed = []
    for patch_path in sorted(PATCHES_DIR.rglob('*.patch')):
        content = patch_path.read_text(encoding='utf-8')
        normalized = normalize_patch_artifacts(content)
        if normalized == content:
            continue
        temp_path = patch_path.with_suffix(patch_path.suffix + '.tmp')
        temp_path.write_text(normalized, encoding='utf-8')
        os.replace(temp_path, patch_path)
        changed.append(str(patch_path.relative_to(ROOT)))
    return changed


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


def default_changed_from():
    """Pick a diff base that keeps committed-but-unpushed work in scope.

    Defaulting to HEAD makes an already committed change look like an empty
    diff, so the guard would scope itself down to nothing and pass without
    inspecting the very files it is gating.
    """
    for upstream in ('@{upstream}', 'origin/main'):
        merge_base = git_lines(['merge-base', upstream, 'HEAD'])
        if merge_base:
            return merge_base[0]
    return 'HEAD'


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
        args.changed_from, '--keep-going'
    ])
    if touches_code_dirs(files):
        run_yapf_dry_run(args.python)


def source_download_inputs(*, include_macos):
    """Return the manifests needed for a root or merged source baseline."""
    inputs = ['downloads.ini']
    if include_macos:
        inputs.extend(['deps.ini', 'platform/macos/downloads.ini'])
    return inputs


def unpack_source_tree(args, source_tree, *, include_macos=False):
    """Delete and unpack a disposable Chromium source tree."""
    shutil.rmtree(source_tree, ignore_errors=True)
    source_tree.parent.mkdir(parents=True, exist_ok=True)
    run([
        args.python,
        './utils/downloads.py',
        'unpack',
        '-i',
        *source_download_inputs(include_macos=include_macos),
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
        '--keep-going',
        '--require-checks',
    ])


def _env_path(primary, legacy, default):
    value = os.environ.get(primary) or os.environ.get(legacy)
    if not value:
        return default
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def hot_export_paths():
    """Return the configured hot tree, merged queue, and session directory."""
    hot_tree = _env_path('NITROUS_SRC_DIR', 'HELIUM_SRC_DIR', ROOT / 'build' / 'src')
    merged_queue = _env_path('NITROUS_MERGED_PATCHES_DIR', 'HELIUM_MERGED_PATCHES_DIR',
                             ROOT / 'build' / 'platform_macos_patches')
    session_dir = ROOT / 'codex_tmp' / 'hot-export'
    return hot_tree.resolve(), merged_queue.resolve(), session_dir


def hot_export_context():
    """Return the configured export context."""
    hot_tree, merged_queue, session_dir = hot_export_paths()
    return hot_patch_export.ExportContext(ROOT, hot_tree, merged_queue, session_dir)


def run_hot_start(args):
    """Capture the pre-edit state for a future top-patch export."""
    context = hot_export_context()
    manifest = hot_patch_export.start_session(context, args.patch, args.files)
    print(f'Hot export session started: {manifest.relative_to(ROOT)}')
    print('Edit only the declared files in build/src, then run export-hotfix.')


def run_hot_add(args):
    """Capture additional files before expanding an active hot-edit scope."""
    context = hot_export_context()
    added = hot_patch_export.add_session_files(context, args.files)
    print('Added hot export baselines:')
    for path in added:
        print(f'  - {path}')


def run_export_hotfix(args):
    """Stage, validate, and publish a new root-stack patch from hot-tree edits."""
    context = hot_export_context()
    patchwork_src = context.session_dir / 'patchwork-src'
    unpack_source_tree(args, patchwork_src)
    staged_queue = hot_patch_export.stage_session(context, patchwork_src)

    chromium_src = ROOT / 'chromium_src'
    run([args.python, './devutils/check_chromium_src_clean.py', '--source-tree', chromium_src])
    run([
        args.python, './devutils/validate_patches.py', '-l', chromium_src, '-p', staged_queue, '-s',
        staged_queue / 'series', '-v'
    ])

    staged_merged = context.session_dir / 'staged-merged-patches'
    run([
        args.python, './utils/patches.py', 'merge', staged_merged, staged_queue,
        ROOT / 'platform' / 'macos' / 'patches'
    ])
    merged_source = context.session_dir / 'merged-validation-src'
    unpack_source_tree(args, merged_source, include_macos=True)
    run([
        args.python, './devutils/validate_patches.py', '-l', merged_source, '-p', staged_merged,
        '-s', staged_merged / 'series', '-v'
    ])

    hot_patch_export.publish_staged_patch(context, staged_queue)
    files = changed_files(args.changed_from)
    print_changed(files)
    run_quick(args, files)
    run_patch_source(args, files)


def run_hot_abort():
    """Discard an incomplete hot export session without touching source files."""
    _hot_tree, _merged_queue, session_dir = hot_export_paths()
    if session_dir.exists():
        shutil.rmtree(session_dir)
        print(f'Removed hot export session: {session_dir.relative_to(ROOT)}')
    else:
        print('No hot export session exists.')


def run_normalize_artifacts():
    """Remove forbidden quilt metadata, then verify the full patch queue."""
    changed = normalize_all_patch_artifacts()
    if changed:
        print('Normalized patch metadata:')
        for path in changed:
            print(f'  - {path}')
    else:
        print('No patch metadata needed normalization.')
    preflight([], scan_all_patches=True)


def validate_mode_arguments(parser, args):
    """Validate mode-specific CLI arguments."""
    if args.mode == 'hot-start' and (not args.patch or not args.files):
        parser.error('--mode hot-start requires --patch <new.patch> and at least one --file')
    if args.mode == 'hot-add' and not args.files:
        parser.error('--mode hot-add requires at least one --file')
    if args.mode not in ('hot-start', 'hot-add') and args.files:
        parser.error('--file is only valid with --mode hot-start or hot-add')
    if args.mode != 'hot-start' and args.patch:
        parser.error('--patch is only valid with --mode hot-start')
    if args.patch and (Path(args.patch).is_absolute() or '..' in Path(args.patch).parts):
        parser.error('--patch must be a path relative to patches/')


def dispatch_mode(args, files):
    """Dispatch a validated guard mode."""
    handlers = {
        'quick': lambda: run_quick(args, files),
        'patch-source': lambda: run_patch_source(args, files),
        'pre-build': lambda: run_patch_source(args, files),
        'hot-start': lambda: run_hot_start(args),
        'hot-add': lambda: run_hot_add(args),
        'export-hotfix': lambda: run_export_hotfix(args),
        'hot-abort': run_hot_abort,
        'normalize-artifacts': run_normalize_artifacts,
    }
    handlers[args.mode]()


def main():
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',
                        required=True,
                        choices=('quick', 'patch-source', 'pre-build', 'hot-start', 'hot-add',
                                 'export-hotfix', 'hot-abort', 'normalize-artifacts'),
                        help='Guard mode to run.')
    parser.add_argument('--patch', help='New root-stack patch name for --mode hot-start.')
    parser.add_argument('--file',
                        action='append',
                        dest='files',
                        default=[],
                        help='Chromium source path for --mode hot-start/hot-add. Repeatable.')
    parser.add_argument('--changed-from',
                        help='Git ref used for scoped changes. Defaults to the merge-base with '
                        'the upstream branch so committed work stays in scope.')
    parser.add_argument('--python', default=sys.executable, help='Python executable to use.')
    args = parser.parse_args()

    validate_mode_arguments(parser, args)

    if not args.changed_from:
        args.changed_from = default_changed_from()
    print(f'Scoped change diff base: {args.changed_from}', flush=True)

    files = changed_files(args.changed_from)
    print_changed(files)

    try:
        dispatch_mode(args, files)
    except hot_patch_export.ExportError as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)

    print('\nAgent patch guard completed successfully.')


if __name__ == '__main__':
    main()
