# -*- coding: UTF-8 -*-
"""Tests for sync_component_dylibs.py."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sync_component_dylibs

sys.path.pop(0)


def test_sync_dylib_closure_copies_transitive_dependencies(tmp_path):
    """Copy every @rpath dylib needed by the bundled Mach-O files."""
    source_dir = tmp_path / 'out' / 'Default'
    frameworks_dir = tmp_path / 'Nitrous.app' / 'Contents' / 'Frameworks'
    source_dir.mkdir(parents=True)
    frameworks_dir.mkdir(parents=True)

    chrome_dll = frameworks_dir / 'libchrome_dll.dylib'
    base = source_dir / 'libbase.dylib'
    mojo = source_dir / 'libmojo_core_embedder.dylib'
    for path in (chrome_dll, base, mojo):
        path.write_bytes(path.name.encode())

    dependencies = {
        'libchrome_dll.dylib': ('@rpath/libbase.dylib', '/usr/lib/libSystem.B.dylib'),
        'libbase.dylib': ('@rpath/libmojo_core_embedder.dylib', ),
        'libmojo_core_embedder.dylib': (),
    }

    copied = sync_component_dylibs.sync_dylib_closure((chrome_dll, ), frameworks_dir, source_dir,
                                                      lambda path: dependencies[path.name])

    assert copied == (frameworks_dir / 'libbase.dylib',
                      frameworks_dir / 'libmojo_core_embedder.dylib')
    assert (frameworks_dir / 'libbase.dylib').read_bytes() == base.read_bytes()
    assert (frameworks_dir / 'libmojo_core_embedder.dylib').read_bytes() == mojo.read_bytes()


def test_sync_dylib_closure_fails_for_missing_source_dependency(tmp_path):
    """Report unresolved @rpath dependencies instead of making a broken app."""
    source_dir = tmp_path / 'out' / 'Default'
    frameworks_dir = tmp_path / 'Nitrous.app' / 'Contents' / 'Frameworks'
    source_dir.mkdir(parents=True)
    frameworks_dir.mkdir(parents=True)
    chrome_dll = frameworks_dir / 'libchrome_dll.dylib'
    chrome_dll.touch()

    with pytest.raises(FileNotFoundError, match='libbase.dylib'):
        sync_component_dylibs.sync_dylib_closure((chrome_dll, ), frameworks_dir, source_dir,
                                                 lambda _path: ('@rpath/libbase.dylib', ))


def test_sync_dylib_closure_refreshes_stale_framework_dylibs(tmp_path):
    """Replace Frameworks copies when out/Default has a newer build."""
    source_dir = tmp_path / 'out' / 'Default'
    frameworks_dir = tmp_path / 'Nitrous.app' / 'Contents' / 'Frameworks'
    source_dir.mkdir(parents=True)
    frameworks_dir.mkdir(parents=True)

    chrome_dll = frameworks_dir / 'libchrome_dll.dylib'
    stale_base = frameworks_dir / 'libbase.dylib'
    fresh_base = source_dir / 'libbase.dylib'
    chrome_dll.write_bytes(b'chrome')
    stale_base.write_bytes(b'stale-base')
    # Ensure source is newer than the stale app copy.
    time.sleep(0.02)
    fresh_base.write_bytes(b'fresh-base-with-fix')
    os.utime(stale_base, (time.time() - 10, time.time() - 10))

    dependencies = {
        'libchrome_dll.dylib': ('@rpath/libbase.dylib', ),
        'libbase.dylib': (),
    }

    copied = sync_component_dylibs.sync_dylib_closure((chrome_dll, ), frameworks_dir, source_dir,
                                                      lambda path: dependencies[path.name])

    assert stale_base in copied
    assert stale_base.read_bytes() == b'fresh-base-with-fix'


def test_sync_dylib_closure_visits_each_seed_once(tmp_path):
    """Read each initial Mach-O exactly once while walking dependencies."""
    source_dir = tmp_path / 'out' / 'Default'
    frameworks_dir = tmp_path / 'Nitrous.app' / 'Contents' / 'Frameworks'
    source_dir.mkdir(parents=True)
    frameworks_dir.mkdir(parents=True)

    chrome_dll = frameworks_dir / 'libchrome_dll.dylib'
    chrome_dll.write_bytes(b'chrome')
    visited = []

    def read_dependencies(path):
        visited.append(path)
        return ()

    sync_component_dylibs.sync_dylib_closure((chrome_dll, ), frameworks_dir, source_dir,
                                             read_dependencies)

    assert visited == [chrome_dll]


def test_sync_dylib_closure_reports_dependency_reader_errors(tmp_path):
    """Do not package an incomplete closure after dependency inspection fails."""
    source_dir = tmp_path / 'out' / 'Default'
    frameworks_dir = tmp_path / 'Nitrous.app' / 'Contents' / 'Frameworks'
    source_dir.mkdir(parents=True)
    frameworks_dir.mkdir(parents=True)

    chrome_dll = frameworks_dir / 'libchrome_dll.dylib'
    chrome_dll.write_bytes(b'chrome')

    def read_dependencies(_path):
        raise subprocess.CalledProcessError(1, ('dyld_info', ))

    with pytest.raises(subprocess.CalledProcessError):
        sync_component_dylibs.sync_dylib_closure((chrome_dll, ), frameworks_dir, source_dir,
                                                 read_dependencies)
