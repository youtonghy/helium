# -*- coding: UTF-8 -*-
"""Tests for sync_component_dylibs.py."""

import sys
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
