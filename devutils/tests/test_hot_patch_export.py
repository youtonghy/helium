# -*- coding: UTF-8 -*-
"""Tests for transaction-safe hot-tree patch export."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hot_patch_export

sys.path.pop(0)


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def _make_repo(tmp_path):
    root = tmp_path / 'repo'
    hot_tree = root / 'build' / 'src'
    merged_queue = root / 'build' / 'platform_macos_patches'
    _write(root / 'patches' / 'series', 'base.patch\n')
    _write(root / 'patches' / 'base.patch', '--- a/source.txt\n+++ b/source.txt\n')
    _write(merged_queue / 'series', 'base.patch\nplatform.patch\n')
    _write(merged_queue / 'base.patch', '--- a/source.txt\n+++ b/source.txt\n')
    _write(merged_queue / 'platform.patch', '--- a/platform.txt\n+++ b/platform.txt\n')
    _write(hot_tree / '.pc' / '.quilt_patches', f'{merged_queue}\n')
    _write(hot_tree / '.pc' / '.quilt_series', 'series\n')
    _write(hot_tree / '.pc' / 'applied-patches', 'base.patch\nplatform.patch\n')
    _write(hot_tree / 'source.txt', 'before\n')
    return root, hot_tree, merged_queue


def _context(root, hot_tree, merged_queue, session_dir):
    return hot_patch_export.ExportContext(root, hot_tree, merged_queue, session_dir)


def test_validate_hot_tree_rejects_stale_quilt_queue(tmp_path):
    """A moved checkout must rebuild instead of trusting stale quilt metadata."""
    root, hot_tree, merged_queue = _make_repo(tmp_path)
    _write(hot_tree / '.pc' / '.quilt_patches', f'{root / "old" / "patches"}\n')

    with pytest.raises(hot_patch_export.ExportError, match='quilt patch path'):
        hot_patch_export.validate_hot_tree(hot_tree, merged_queue)


def test_validate_hot_tree_requires_complete_applied_stack(tmp_path):
    """Export starts only when every merged patch is applied in order."""
    _root, hot_tree, merged_queue = _make_repo(tmp_path)
    _write(hot_tree / '.pc' / 'applied-patches', 'base.patch\n')

    with pytest.raises(hot_patch_export.ExportError, match='fully applied'):
        hot_patch_export.validate_hot_tree(hot_tree, merged_queue)


def test_start_session_snapshots_declared_files_and_queue(tmp_path):
    """The pre-edit session records both file content and queue identity."""
    root, hot_tree, merged_queue = _make_repo(tmp_path)
    session_dir = root / 'codex_tmp' / 'hot-export'

    manifest_path = hot_patch_export.start_session(
        _context(root, hot_tree, merged_queue, session_dir), 'helium/core/hot-fix.patch',
        ('source.txt', 'new-file.txt'))

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest['patch'] == 'helium/core/hot-fix.patch'
    assert manifest['files'][0]['path'] == 'new-file.txt'
    assert manifest['files'][0]['kind'] == 'missing'
    assert manifest['files'][1]['path'] == 'source.txt'
    assert manifest['files'][1]['kind'] == 'file'
    assert (session_dir / 'baseline' / 'source.txt').read_text(encoding='utf-8') == 'before\n'
    assert manifest['queue_sha256'] == hot_patch_export.queue_fingerprint(merged_queue)


def test_start_session_refuses_existing_patch(tmp_path):
    """Hot-tree export only creates a new root-stack patch."""
    root, hot_tree, merged_queue = _make_repo(tmp_path)

    with pytest.raises(hot_patch_export.ExportError, match='already exists'):
        hot_patch_export.start_session(
            _context(root, hot_tree, merged_queue, root / 'codex_tmp' / 'hot-export'), 'base.patch',
            ('source.txt', ))


def test_verify_session_rejects_queue_drift(tmp_path):
    """Changing the queue after hot-start invalidates the captured baseline."""
    root, hot_tree, merged_queue = _make_repo(tmp_path)
    session_dir = root / 'codex_tmp' / 'hot-export'
    context = _context(root, hot_tree, merged_queue, session_dir)
    hot_patch_export.start_session(context, 'hot-fix.patch', ('source.txt', ))
    _write(merged_queue / 'platform.patch', 'changed\n')

    with pytest.raises(hot_patch_export.ExportError, match='queue changed'):
        hot_patch_export.verify_session(context)


def test_verify_session_requires_at_least_one_hot_tree_change(tmp_path):
    """An unchanged session cannot create an empty success-looking patch."""
    root, hot_tree, merged_queue = _make_repo(tmp_path)
    session_dir = root / 'codex_tmp' / 'hot-export'
    context = _context(root, hot_tree, merged_queue, session_dir)
    hot_patch_export.start_session(context, 'hot-fix.patch', ('source.txt', ))

    with pytest.raises(hot_patch_export.ExportError, match='no declared files changed'):
        hot_patch_export.verify_session(context)


def test_add_session_files_snapshots_new_declared_path(tmp_path):
    """A scope expansion captures its own pre-edit baseline."""
    root, hot_tree, merged_queue = _make_repo(tmp_path)
    session_dir = root / 'codex_tmp' / 'hot-export'
    _write(hot_tree / 'second.txt', 'second-before\n')
    context = _context(root, hot_tree, merged_queue, session_dir)
    hot_patch_export.start_session(context, 'hot-fix.patch', ('source.txt', ))

    hot_patch_export.add_session_files(context, ('second.txt', ))

    manifest = json.loads((session_dir / 'manifest.json').read_text(encoding='utf-8'))
    assert [entry['path'] for entry in manifest['files']] == ['second.txt', 'source.txt']
    assert (session_dir / 'baseline' /
            'second.txt').read_text(encoding='utf-8') == 'second-before\n'


def _make_export_repo(tmp_path):
    root = tmp_path / 'export-repo'
    hot_tree = root / 'build' / 'src'
    merged_queue = root / 'build' / 'platform_macos_patches'
    patchwork_tree = root / 'codex_tmp' / 'hot-export' / 'patchwork-src'
    base_patch = """--- a/source.txt
+++ b/source.txt
@@ -1 +1 @@
-raw
+before
"""
    _write(root / 'patches' / 'series', 'base.patch\n')
    _write(root / 'patches' / 'base.patch', base_patch)
    _write(merged_queue / 'series', 'base.patch\n')
    _write(merged_queue / 'base.patch', base_patch)
    _write(hot_tree / '.pc' / '.quilt_patches', f'{merged_queue}\n')
    _write(hot_tree / '.pc' / '.quilt_series', 'series\n')
    _write(hot_tree / '.pc' / 'applied-patches', 'base.patch\n')
    _write(hot_tree / 'source.txt', 'before\n')
    return root, hot_tree, merged_queue, patchwork_tree


def test_stage_session_creates_replayable_patch_without_writing_live_queue(tmp_path):
    """A staged top patch reproduces modified and newly added hot-tree files."""
    root, hot_tree, merged_queue, patchwork_tree = _make_export_repo(tmp_path)
    session_dir = root / 'codex_tmp' / 'hot-export'
    context = _context(root, hot_tree, merged_queue, session_dir)
    hot_patch_export.start_session(context, 'hot-fix.patch', ('source.txt', 'new.txt'))
    _write(hot_tree / 'source.txt', 'after\n')
    _write(hot_tree / 'new.txt', 'new\n')
    _write(patchwork_tree / 'source.txt', 'raw\n')

    staged_queue = hot_patch_export.stage_session(context, patchwork_tree)

    assert not (root / 'patches' / 'hot-fix.patch').exists()
    assert (root / 'patches' / 'series').read_text(encoding='utf-8') == 'base.patch\n'
    assert (staged_queue / 'series').read_text(encoding='utf-8') == ('base.patch\nhot-fix.patch\n')
    patch = (staged_queue / 'hot-fix.patch').read_text(encoding='utf-8')
    assert 'Index:' not in patch
    assert '--- a/source.txt' in patch
    assert '+++ b/source.txt' in patch
    assert '--- /dev/null' in patch
    assert '+++ b/new.txt' in patch
    assert (patchwork_tree / 'source.txt').read_text(encoding='utf-8') == 'after\n'
    assert (patchwork_tree / 'new.txt').read_text(encoding='utf-8') == 'new\n'


def test_stage_session_rejects_patchwork_that_does_not_match_hot_baseline(tmp_path):
    """Later-layer or preprocessing differences cannot be folded into a root patch."""
    root, hot_tree, merged_queue, patchwork_tree = _make_export_repo(tmp_path)
    session_dir = root / 'codex_tmp' / 'hot-export'
    context = _context(root, hot_tree, merged_queue, session_dir)
    hot_patch_export.start_session(context, 'hot-fix.patch', ('source.txt', ))
    _write(hot_tree / 'source.txt', 'after\n')
    _write(patchwork_tree / 'source.txt', 'raw\nplatform-layer\n')

    with pytest.raises(hot_patch_export.ExportError, match='baseline does not match'):
        hot_patch_export.stage_session(context, patchwork_tree)


def test_publish_staged_patch_updates_patch_and_series_then_removes_session(tmp_path):
    """Publishing occurs only after staging and leaves no reusable stale session."""
    root, hot_tree, merged_queue, patchwork_tree = _make_export_repo(tmp_path)
    session_dir = root / 'codex_tmp' / 'hot-export'
    context = _context(root, hot_tree, merged_queue, session_dir)
    hot_patch_export.start_session(context, 'hot-fix.patch', ('source.txt', ))
    _write(hot_tree / 'source.txt', 'after\n')
    _write(patchwork_tree / 'source.txt', 'raw\n')
    staged_queue = hot_patch_export.stage_session(context, patchwork_tree)

    hot_patch_export.publish_staged_patch(context, staged_queue)

    assert (root / 'patches' / 'hot-fix.patch').is_file()
    assert (root / 'patches' / 'series').read_text(encoding='utf-8').endswith('hot-fix.patch\n')
    assert not session_dir.exists()
