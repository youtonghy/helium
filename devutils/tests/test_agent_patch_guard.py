# -*- coding: UTF-8 -*-
"""Tests for agent_patch_guard.py patch hygiene helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agent_patch_guard

sys.path.pop(0)


def test_normalize_patch_artifacts_removes_only_quilt_metadata():
    """Index headers are removed without changing diff hunks."""
    content = """Index: source.txt
===================================================================
--- a/source.txt
+++ b/source.txt
@@ -1 +1 @@
-before
+after
"""

    normalized = agent_patch_guard.normalize_patch_artifacts(content)

    assert normalized == """--- a/source.txt
+++ b/source.txt
@@ -1 +1 @@
-before
+after
"""


def test_normalize_patch_artifacts_preserves_unrelated_separator():
    """A separator not immediately following Index metadata is patch content."""
    content = 'note\n===================================================================\n'

    assert agent_patch_guard.normalize_patch_artifacts(content) == content


def test_source_download_inputs_include_platform_dependencies_when_requested():
    """Merged macOS validation includes every platform download baseline."""
    assert agent_patch_guard.source_download_inputs(include_macos=True) == [
        'downloads.ini',
        'deps.ini',
        'platform/macos/downloads.ini',
    ]


def test_source_download_inputs_keep_root_validation_minimal():
    """Root patch validation avoids unrelated platform-only downloads."""
    assert agent_patch_guard.source_download_inputs(include_macos=False) == [
        'downloads.ini',
    ]


def test_format_size_scales_units_for_reporting():
    """Cleanup reporting stays readable across magnitudes."""
    assert agent_patch_guard.format_size(0) == '0.0 B'
    assert agent_patch_guard.format_size(2048) == '2.0 KiB'
    assert agent_patch_guard.format_size(5 * 1024**3) == '5.0 GiB'


def test_tree_size_is_zero_for_missing_tree(tmp_path):
    """A cleanup target that does not exist contributes nothing."""
    assert agent_patch_guard.tree_size(tmp_path / 'absent') == 0


def test_tree_size_reports_existing_tree(tmp_path):
    """An existing tree reports a non-zero size."""
    (tmp_path / 'file.txt').write_text('payload', encoding='utf-8')

    assert agent_patch_guard.tree_size(tmp_path) > 0


def test_cleanup_targets_cover_disposable_trees_only():
    """Cleanup never proposes the patch SoT or the baseline validation tree."""
    paths = [path for path, _description in agent_patch_guard.cleanup_targets()]
    names = {path.name for path in paths}

    assert 'patchcheck_src' in names
    assert 'patchwork_src' in names
    assert agent_patch_guard.ROOT / 'patches' not in paths
    assert agent_patch_guard.ROOT / 'chromium_src' not in paths
    assert agent_patch_guard.ROOT / 'chromium_download_cache' not in paths


def test_cleanup_targets_have_no_duplicates():
    """Discovered codex_tmp trees never repeat an explicit target."""
    paths = [path for path, _description in agent_patch_guard.cleanup_targets()]

    assert len(paths) == len(set(paths))


def test_cleanup_is_dispatchable_without_scoped_files():
    """Cleanup is disk hygiene, so it takes no change scope."""
    assert agent_patch_guard.run_cleanup.__code__.co_argcount == 0
