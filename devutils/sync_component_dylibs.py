#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Bundle the recursive @rpath dylib closure needed by a macOS app."""

import argparse
import functools
import shutil
import subprocess
from collections import deque
from pathlib import Path

_MACHO_MAGICS = {
    b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe',
    b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'
}
_RPATH_PREFIX = '@rpath/'


@functools.lru_cache(maxsize=1)
def _dyld_info_path():
    result = subprocess.run(('xcrun', '--find', 'dyld_info'),
                            check=True,
                            capture_output=True,
                            encoding='utf-8')
    return result.stdout.strip()


def _read_dyld_info_dependencies(path):
    result = subprocess.run((_dyld_info_path(), '-dependents', path),
                            check=True,
                            capture_output=True,
                            encoding='utf-8')
    return tuple(line.strip() for line in result.stdout.splitlines()
                 if line.lstrip().startswith(('@rpath/', '@loader_path/', '@executable_path/',
                                              '/')))


def _is_macho(path):
    try:
        with path.open('rb') as file_handle:
            return file_handle.read(4) in _MACHO_MAGICS
    except OSError:
        return False


def _find_macho_files(app_path):
    return tuple(path for path in app_path.rglob('*') if path.is_file() and _is_macho(path))


def _rpath_dylib_name(dependency):
    if not dependency.startswith(_RPATH_PREFIX):
        return None
    name = dependency[len(_RPATH_PREFIX):]
    if '/' in name or not name.endswith('.dylib'):
        return None
    return name


def sync_dylib_closure(seed_paths,
                       frameworks_dir,
                       source_dir,
                       dependency_reader=_read_dyld_info_dependencies,
                       check_only=False):
    """Copy or verify the recursive component dylib closure for seed_paths."""
    frameworks_dir = Path(frameworks_dir)
    source_dir = Path(source_dir)
    pending = deque(Path(path) for path in seed_paths)
    queued = {path.name for path in pending}
    copied = []

    while pending:
        current = pending.popleft()
        for dependency in dependency_reader(current):
            name = _rpath_dylib_name(dependency)
            if name is None or name in queued:
                continue

            destination = frameworks_dir / name
            if not destination.is_file():
                if check_only:
                    raise FileNotFoundError(
                        f'{current} requires {dependency}, but {destination} is missing')
                source = source_dir / name
                if not source.is_file():
                    raise FileNotFoundError(
                        f'{current} requires {dependency}, but {source} is missing')
                shutil.copy2(source, destination)
                copied.append(destination)

            queued.add(name)
            pending.append(destination)

    return tuple(copied)


def main():
    """Synchronize or verify one app bundle from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app_path', type=Path)
    parser.add_argument('source_dir', type=Path)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()

    frameworks_dir = args.app_path / 'Contents' / 'Frameworks'
    seed_paths = _find_macho_files(args.app_path)
    if not seed_paths:
        parser.error(f'no Mach-O files found under {args.app_path}')

    copied = sync_dylib_closure(seed_paths,
                                frameworks_dir,
                                args.source_dir,
                                check_only=args.check_only)
    action = 'verified' if args.check_only else 'synchronized'
    print(f'{action} component dylib closure ({len(copied)} copied)')


if __name__ == '__main__':
    main()
