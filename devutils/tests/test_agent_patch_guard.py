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
